#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Evaluate model responses on LiveMedBench using a rubric and GPT‑4.1 as the evaluator.

Basic usage:
    python evaluate_model.py \\
        --rubric-file data/merged_data_rubric.json \\
        --model-result-file outputs/gpt_results.json \\
        --output-file outputs/evaluation_results_gpt_4_1.json \\
        --response-field model_response

Environment:
    - Set your OpenAI API key via:
        export OPENAI_API_KEY="sk-..."

Output file:
    - JSON list, each item:
        {
            "case_id": "...",
            "evaluations": {
                "rubric_1": {
                    "criterion": "...",
                    "points": 10,
                    "score": 1,               # 0 or 1
                    "weighted_score": 10      # points * score
                },
                ...
            }
        }
"""

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Union

from openai import OpenAI


# Fixed evaluator model for LiveMedBench
EVALUATOR_MODEL = "gpt-4.1-2025-04-14"
EVALUATOR_MODEL_DISPLAY = "gpt-4.1"


EVALUATION_PROMPT = """
Role: You are an Objective Grader.
Task: Evaluate the Model Response (M_out) against the provided Rubric (R).

Instructions:
- Objective Verification: For each criterion in the Rubric, determine if the Model Response satisfies it.
- Binary Judgment: Return true (Met) or false (Not Met).
- Positive Criteria Logic: true if the model includes the required information.
- Negative Criteria Logic: true if the model commits the error (e.g., if the rubric asks "Does model suggest antibiotics?" and the model suggests them, return true). Note: The scoring formula handles the negative sign; you simply detect presence.
- Evidence: Quote the specific sentence from the model output that supports your decision.

Input:
- User Query (Q): This is the original question from the patient, built as:
    Q = \"\"\"{user_query}\"\"\"
- Model Response (M_out):
{model_response}

- Rubric (R): JSON list of criteria from Phase 1. In this call you will receive exactly one criterion:
[
  {{"question": "{criterion}"}}
]

Output Format (JSON):
[
  {{
    "question": "Does the model identify the likely cause as Norovirus?",
    "met": true,
    "reasoning": "Model explicitly states 'symptoms suggest Norovirus'."
  }},
  {{
    "question": "Does the model recommend antibiotics?",
    "met": false,
    "reasoning": "Model correctly states 'antibiotics are not effective'."
  }}
]

Now, given the User Query (Q), the Model Response (M_out) and the Rubric (R) with one criterion, output a JSON list with a single object in the exact format above, where:
- "question" is the criterion string you evaluated,
- "met" is true or false,
- "reasoning" briefly quotes or summarizes the evidence from the model response (and, if relevant, the user query) that supports your decision.
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate model responses on LiveMedBench using GPT‑4.1 as an automatic evaluator."
    )
    parser.add_argument(
        "--rubric-file",
        type=str,
        required=True,
        help="Path to rubric JSON file (list of cases with rubric_items).",
    )
    parser.add_argument(
        "--model-result-file",
        type=str,
        required=True,
        help="Path to model result JSON file (list/dict, indexed by case_id).",
    )
    parser.add_argument(
        "--output-file",
        type=str,
        required=True,
        help="Path to write evaluation results JSON.",
    )
    parser.add_argument(
        "--response-field",
        type=str,
        default="model_response",
        help="Field name in model results that contains the model's response.",
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=None,
        help="If set, only evaluate the first N cases (for debugging).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="If set, resume from an existing output file (by case_id).",
    )
    return parser.parse_args()


def init_client() -> OpenAI:
    """Initialize OpenAI client from environment variable."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Please export your key before running:\n"
            "  export OPENAI_API_KEY='sk-...'"
        )
    return OpenAI(api_key=api_key)


def load_json_file(file_path: Path) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    with file_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_model_results(
    model_result_file: Path,
    response_field: str,
) -> Dict[str, Any]:
    """
    Load model results and index them by case_id.

    Supports both list and dict formats.
    """
    if not model_result_file.exists():
        print(f"⚠️ Model result file does not exist: {model_result_file}")
        return {}

    print(f"Loading model results from: {model_result_file}")
    try:
        data = load_json_file(model_result_file)
        model_dict: Dict[str, Any] = {}

        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                case_id = item.get("case_id")
                if case_id is not None:
                    model_dict[str(case_id)] = item

        elif isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, dict):
                    case_id = v.get("case_id") or k
                    model_dict[str(case_id)] = v

        else:
            raise TypeError(f"Unsupported JSON root type: {type(data)}")

        print(f"  ✓ Loaded {len(model_dict)} cases from model results.")
        return model_dict

    except Exception as e:  # noqa: BLE001
        print(f"  ✗ Failed to load model results: {e}")
        return {}


def create_evaluation_prompt(
    criterion: str,
    model_response: str,
    user_query: str,
) -> str:
    """Fill the evaluation prompt template."""
    return EVALUATION_PROMPT.format(
        criterion=criterion.strip(),
        model_response=(model_response or "").strip(),
        user_query=(user_query or "").strip(),
    )


def call_gpt_evaluator(
    client: OpenAI,
    prompt: str,
    max_retries: int = 3,
) -> str:
    """
    Call GPT‑4.1 evaluator and return '0' or '1'.

    The prompt asks for a JSON list with objects of the form
    {"question": "...", "met": true/false, "reasoning": "..."}.
    We parse the first object's "met" field and convert it to 1/0.
    """
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=EVALUATOR_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                temperature=0.0,
                max_completion_tokens=64,
            )

            choice = response.choices[0]
            text = (choice.message.content or "").strip()

            # First try to parse JSON as specified in the prompt.
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list) and parsed:
                    first = parsed[0]
                    if isinstance(first, dict) and "met" in first:
                        met = first["met"]
                        # Accept booleans or string "true"/"false"
                        if isinstance(met, bool):
                            return "1" if met else "0"
                        if isinstance(met, str):
                            lowered = met.strip().lower()
                            if lowered == "true":
                                return "1"
                            if lowered == "false":
                                return "0"
            except Exception:
                # Fall back to heuristic parsing below.
                pass

            # Fallback: check for 'met' in a non‑JSON answer, or generic true/false.
            lowered_text = text.lower()
            if '"met"' in lowered_text:
                if "true" in lowered_text:
                    return "1"
                if "false" in lowered_text:
                    return "0"

            # Final fallback heuristics similar to yes/no.
            if "yes" in lowered_text or "satisf" in lowered_text:
                return "1"
            if "no" in lowered_text or "not satisf" in lowered_text:
                return "0"

            print(
                f"⚠️ Could not parse evaluator output, defaulting to 0. "
                f"Raw output: {text[:160]!r}"
            )
            return "0"

        except Exception as e:  # noqa: BLE001
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"Evaluator call failed, retrying in {wait_time}s... Error: {e}")
                time.sleep(wait_time)
            else:
                print(
                    f"Evaluator call failed after {max_retries} attempts, "
                    f"defaulting to 0. Error: {e}"
                )
                return "0"

    return "0"


def evaluate_rubric_item(
    client: OpenAI,
    criterion: str,
    model_response: str,
    user_query: str,
) -> int:
    """Evaluate a single rubric item and return 0 or 1."""
    if not model_response or not str(model_response).strip():
        return 0
    prompt = create_evaluation_prompt(
        criterion,
        str(model_response),
        user_query,
    )
    result = call_gpt_evaluator(client, prompt)
    return int(result)


def process_evaluations(
    client: OpenAI,
    rubric_file: Path,
    model_result_file: Path,
    output_file: Path,
    response_field: str,
    max_cases: int | None = None,
    resume: bool = False,
) -> None:
    """Main evaluation loop."""
    print("=" * 60)
    print(f"LiveMedBench evaluator ({EVALUATOR_MODEL_DISPLAY})")
    print("=" * 60)

    print("\nLoading rubric data...")
    rubric_data = load_json_file(rubric_file)
    if not isinstance(rubric_data, list):
        raise TypeError(f"Rubric file must be a list of cases, got {type(rubric_data)}")
    print(f"Loaded {len(rubric_data)} cases with rubric.")

    print("\nLoading model results...")
    model_results = load_model_results(model_result_file, response_field)

    existing_evaluations: Dict[str, Dict[str, Any]] = {}
    if resume and output_file.exists():
        try:
            existing_list = load_json_file(output_file)
            if isinstance(existing_list, list):
                existing_evaluations = {
                    str(e.get("case_id")): e
                    for e in existing_list
                    if isinstance(e, dict) and e.get("case_id") is not None
                }
            print(f"✓ Resume: loaded {len(existing_evaluations)} existing evaluations.")
        except Exception as e:  # noqa: BLE001
            print(f"⚠ Failed to load existing evaluations, starting fresh: {e}")

    output_file.parent.mkdir(parents=True, exist_ok=True)

    results: List[Dict[str, Any]] = []
    total_cases = len(rubric_data)
    processed_count = 0

    for idx, case in enumerate(rubric_data):
        if max_cases is not None and processed_count >= max_cases:
            print(f"Reached max_cases={max_cases}, stopping early.")
            break

        if not isinstance(case, dict):
            continue

        case_id = case.get("case_id")
        if case_id is None:
            continue
        case_id_str = str(case_id)
        rubric_items = case.get("rubric_items", [])

        if not rubric_items:
            print(f"[{idx+1}/{total_cases}] ⚠️ Skip case {case_id_str}: no rubric_items")
            if case_id_str not in existing_evaluations:
                results.append({"case_id": case_id, "evaluations": {}})
            continue

        if case_id_str in existing_evaluations:
            print(f"[{idx+1}/{total_cases}] ⏭ Skip already evaluated case: {case_id_str}")
            results.append(existing_evaluations[case_id_str])
            continue

        processed_count += 1
        print(
            f"\n[{idx+1}/{total_cases}] 🔄 Evaluating case: {case_id_str} "
            f"(new processed: {processed_count})"
        )
        print(f"    Rubric items: {len(rubric_items)}")

        if case_id_str not in model_results:
            print(f"    ⚠️ Model result missing for case_id={case_id_str}")
            results.append({"case_id": case_id, "evaluations": {}})
            continue

        model_case = model_results[case_id_str]
        model_response = ""
        if isinstance(model_case, dict):
            model_response = model_case.get(response_field, "") or ""
            if not model_response and response_field != "response":
                # Fallback to 'response' if needed
                model_response = model_case.get("response", "") or ""

        if not model_response:
            print(f"    ⚠️ Model response empty for case_id={case_id_str}")
            results.append({"case_id": case_id, "evaluations": {}})
            continue

        # Build the user query as narrative + two newlines + core_request,
        # so the grader can see both parts of the original question.
        narrative = case.get("narrative", "") or ""
        core_request = case.get("core_request", "") or ""
        user_query = f"{narrative}\n\n{core_request}".strip()

        print(f"    📊 Evaluating {EVALUATOR_MODEL_DISPLAY} on {len(rubric_items)} criteria...")
        model_evaluations: Dict[str, Any] = {}

        for rubric_idx, rubric_item in enumerate(rubric_items, 1):
            if not isinstance(rubric_item, dict):
                continue
            criterion = rubric_item.get("criterion", "")
            points = rubric_item.get("points", 0)
            axe = rubric_item.get("axe", "")

            if not criterion:
                continue

            score = evaluate_rubric_item(
                client,
                criterion,
                model_response,
                user_query,
            )

            model_evaluations[f"rubric_{rubric_idx}"] = {
                "criterion": criterion,
                "points": points,
                "axe": axe,
                "score": score,
                "weighted_score": points * score,
            }

            # Light rate‑limiting on evaluator calls
            time.sleep(0.2)

        print("      ✓ Evaluation completed.")

        result = {"case_id": case_id, "evaluations": model_evaluations}
        results.append(result)

        if processed_count % 5 == 0:
            combined = list(existing_evaluations.values()) + results
            with output_file.open("w", encoding="utf-8") as f:
                json.dump(combined, f, ensure_ascii=False, indent=2)
            print(
                f"\n💾 Saved intermediate results, "
                f"current progress: {len(combined)}/{total_cases}"
            )

    print("\nSaving final results...")
    final_results = list(existing_evaluations.values()) + results
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(final_results, f, ensure_ascii=False, indent=2)

    print(f"\nDone! Total evaluated cases: {len(final_results)}")
    print(f"Results saved to: {output_file}")


def main() -> None:
    args = parse_args()

    rubric_path = Path(args.rubric_file)
    model_result_path = Path(args.model_result_file)
    output_path = Path(args.output_file)

    print("=" * 60)
    print("LiveMedBench: evaluate_model")
    print("=" * 60)
    print(f"Rubric file       : {rubric_path}")
    print(f"Model result file : {model_result_path}")
    print(f"Output file       : {output_path}")
    print(f"Evaluator model   : {EVALUATOR_MODEL} ({EVALUATOR_MODEL_DISPLAY})")
    print(f"Response field    : {args.response_field}")
    if args.max_cases is not None:
        print(f"Max cases         : {args.max_cases} (for debugging)")
    print(f"Resume            : {args.resume}")
    print("=" * 60)

    print("\nInitializing OpenAI evaluator client...")
    client = init_client()

    process_evaluations(
        client=client,
        rubric_file=rubric_path,
        model_result_file=model_result_path,
        output_file=output_path,
        response_field=args.response_field,
        max_cases=args.max_cases,
        resume=args.resume,
    )


if __name__ == "__main__":
    main()

