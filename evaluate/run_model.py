#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run a LLM (e.g., GPT-4.x/GPT-5.x) on the LiveMedBench.

Basic usage:
    python run_model.py \
        --data-file data/LiveMedBench_v202601.json \
        --output-file outputs/gpt_results.json \
        --model gpt-5.2-2025-12-11 

Environment:
    - Set your OpenAI API key via the standard environment variable:
        export OPENAI_API_KEY="sk-..."

Input format (per case, JSON list):
    {
        "post_time": "string, optional",
        "narrative": "string",
        "core_request": "string",
        "doctor_advice": "string, optional"
    }

Output format (JSON list):
    {
        "post_time": ...,
        "narrative": ...,
        "core_request": ...,
        "model_response": "...",      # model's answer
        "finish_reason": "...",       # OpenAI finish_reason
        "doctor_advice": "...",       # original doctor advice, if present
    }
"""

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an OpenAI chat model on the LiveMedBench."
    )
    parser.add_argument(
        "--data-file",
        type=str,
        required=True,
        help="Path to input JSON file (list of cases).",
    )
    parser.add_argument(
        "--output-file",
        type=str,
        required=True,
        help="Path to save model outputs (JSON).",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-5.2-2025-12-11",
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=None,
        help="If set, only process the first N cases (useful for debugging).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="If set, resume from an existing output file (by case_id).",
    )
    return parser.parse_args()


def load_data(file_path: Path) -> List[Dict[str, Any]]:
    """Load a JSON list of cases."""
    with file_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected a list at root of {file_path}, got {type(data)}")
    return data


def has_chinese(text: str) -> bool:
    """Return True if the text contains any CJK Unified Ideographs."""
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            return True
    return False


def create_prompt(narrative: str, core_request: str) -> str:
    """
    Build the user-facing prompt.

    - If the content contains Chinese, we give a short Chinese instruction.
    - Otherwise we give an English instruction.
    """
    combined_text = f"{narrative}\n\n{core_request}"

    if has_chinese(combined_text):
        instruction = "请直接用中文回答下面的问题，不要给出推理过程或中间步骤。"
    else:
        instruction = (
            "IMPORTANT: Provide ONLY the final answer to the following question, "
            "without any explanation or reasoning steps."
        )

    prompt = f"{instruction}\n\n{narrative}\n\n{core_request}"
    return prompt


def init_client() -> OpenAI:
    """
    Initialize the OpenAI client.

    The API key is read from environment variable OPENAI_API_KEY.
    We do not hard-code any secrets in this script.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Please export your key before running:\n"
            "  export OPENAI_API_KEY='sk-...'"
        )
    return OpenAI(api_key=api_key)


def call_chat_model(
    client: OpenAI,
    model: str,
    prompt: str,
    max_retries: int = 3,
) -> Tuple[Optional[Any], str, str]:
    """
    Call an OpenAI chat model and return (raw_response, text, finish_reason).

    This uses a simple user-only message. You can extend the system prompt
    logic here if your experiments require it.
    """
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                temperature=0.0,
                max_completion_tokens=2048,
            )
            choice = response.choices[0]
            content = choice.message.content or ""
            finish_reason = choice.finish_reason or "unknown"
            return response, content.strip(), finish_reason
        except Exception as e:  # noqa: BLE001 - keep simple for script usage
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"API call failed, retrying in {wait_time}s... Error: {e}")
                time.sleep(wait_time)
            else:
                print(f"API call failed after {max_retries} attempts: {e}")
                return None, f"ERROR: {e}", "error"


def save_results(results: List[Dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def process_cases(
    client: OpenAI,
    model: str,
    data: List[Dict[str, Any]],
    output_path: Path,
    max_cases: Optional[int] = None,
    resume: bool = False,
) -> List[Dict[str, Any]]:
    """Iterate over all cases and call the model."""
    results: List[Dict[str, Any]] = []
    processed_case_ids = set()
    total = len(data)

    if resume and output_path.exists():
        try:
            with output_path.open("r", encoding="utf-8") as f:
                existing_results = json.load(f)
            if isinstance(existing_results, list):
                results = existing_results
                processed_case_ids = {
                    r.get("case_id") for r in results if r.get("case_id") is not None
                }
                print(
                    f"[resume] Loaded {len(results)} existing results, "
                    f"{len(processed_case_ids)} unique case_ids."
                )
        except Exception as e:  # noqa: BLE001
            print(f"Warning: failed to load existing results from {output_path}: {e}")

    processed_count = 0

    for idx, case in enumerate(data):
        case_id = case.get("case_id", f"case_{idx}")
        if case_id in processed_case_ids:
            print(f"[{idx+1}/{total}] Skip already processed case_id={case_id}")
            continue

        narrative = case.get("narrative", "") or ""
        core_request = case.get("core_request", "") or ""

        processed_count += 1
        print(
            f"[{idx+1}/{total}] Processing case_id={case_id} "
            f"(new processed: {processed_count})"
        )

        prompt = create_prompt(narrative, core_request)
        raw_resp, text, finish_reason = call_chat_model(client, model, prompt)

        record: Dict[str, Any] = {
            "case_id": case_id,
            "post_time": case.get("post_time", ""),
            "narrative": narrative,
            "core_request": core_request,
            "model_response": text,
            "finish_reason": finish_reason,
            # Keep original doctor advice if available, useful for downstream eval
            "doctor_advice": case.get("doctor_advice", ""),
        }
        # Do NOT serialize the full raw_resp object to keep files compact and
        # avoid potential leakage of internal metadata.
        results.append(record)
        processed_case_ids.add(case_id)

        # Periodic checkpointing
        if processed_count % 1 == 0:
            save_results(results, output_path)
            print(
                f"[checkpoint] Saved {len(results)} results "
                f"({processed_count} new processed)."
            )

        if max_cases is not None and processed_count >= max_cases:
            print(f"Reached max_cases={max_cases}, stopping early.")
            break

        # Simple rate limiting; adjust for your quota/latency requirements.
        time.sleep(0.5)

    return results


def main() -> None:
    args = parse_args()

    data_path = Path(args.data_file)
    output_path = Path(args.output_file)

    print("=" * 60)
    print("LiveMedBench: run_model")
    print("=" * 60)
    print(f"Data file   : {data_path}")
    print(f"Output file : {output_path}")
    print(f"Model       : {args.model}")
    if args.max_cases is not None:
        print(f"Max cases   : {args.max_cases} (for debugging)")
    print(f"Resume      : {args.resume}")
    print("=" * 60)

    print("\nLoading data...")
    data = load_data(data_path)
    print(f"Loaded {len(data)} cases.")

    print("\nInitializing OpenAI client...")
    client = init_client()

    print("\nStarting inference...")
    results = process_cases(
        client=client,
        model=args.model,
        data=data,
        output_path=output_path,
        max_cases=args.max_cases,
        resume=args.resume,
    )

    print("\nSaving final results...")
    save_results(results, output_path)
    print(f"Done. Total cases written: {len(results)}")
    print(f"Results saved to: {output_path}")


if __name__ == "__main__":
    main()

