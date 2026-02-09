#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compute evaluation metrics for LiveMedBench.

This script aggregates rubric-based evaluation results produced by
`evaluate_model.py` and computes:
  - Per‑case normalized scores for each model
  - Monthly (YYYY‑MM) average scores per model
  - Overall average score per model
  
Output
------
The script writes a tab‑separated summary table to `--output-file`:
  Date (YYYY‑MM) | <model_1> | <model_2> | ... | # case
followed by:
  - One row per month
  - A final "Overall" row with global averages for each model
"""

import argparse
import glob
import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute rubric-based metrics for LiveMedBench models."
    )
    parser.add_argument(
        "--rubric-file",
        type=str,
        required=True,
        help="Path to rubric JSON file (list of cases with rubric_items).",
    )
    parser.add_argument(
        "--evaluation-dir",
        type=str,
        required=True,
        help=(
            "Directory containing evaluation_results_*.json files produced by "
            "evaluate_model.py."
        ),
    )
    parser.add_argument(
        "--output-file",
        type=str,
        default="metric_results.txt",
        help="Path to write aggregated metric results (TSV).",
    )
    return parser.parse_args()


def load_json_file(file_path: Path) -> List[Dict[str, Any]]:
    """Load a JSON file expected to contain a list."""
    with file_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise TypeError(f"Expected list at root of {file_path}, got {type(data)}")
    return data


def load_model_files(evaluation_dir: Path) -> Dict[str, Path]:
    """
    Scan directory for `evaluation_results_*.json` files.

    Returns:
        dict: {model_name: file_path}
    """
    model_files: Dict[str, Path] = {}
    pattern = str(evaluation_dir / "evaluation_results_*.json")

    for file_path in glob.glob(pattern):
        p = Path(file_path)
        filename = p.name
        if filename.startswith("evaluation_results_") and filename.endswith(".json"):
            model_name = filename[len("evaluation_results_") : -len(".json")]
            model_files[model_name] = p

    return model_files


def calculate_max_possible_score(rubric_items: List[Dict[str, Any]]) -> float:
    """
    Compute the maximum possible positive score for a case.

    This follows the MedOnline logic:
      - Sum only positive `points` values in the rubric (negative ones are
        handled in weighted_score already).
    """
    if not rubric_items:
        return 0.0

    max_score = 0.0
    for item in rubric_items:
        points = item.get("points", 0)
        if isinstance(points, (int, float)) and points > 0:
            max_score += float(points)

    return max_score


def calculate_case_total_score(
    evaluations: Dict[str, Any],
    rubric_items: List[Dict[str, Any]],
) -> float:
    """
    Compute the total weighted_score for a single case.

    We:
      - Build a set of valid criteria from the rubric file.
      - Sum weighted_score for evaluation entries whose criterion appears in
        the rubric (to stay aligned with the reference rubric).
    """
    if not evaluations or not rubric_items:
        return 0.0

    rubric_criteria = {}
    for item in rubric_items:
        criterion = item.get("criterion", "")
        if criterion:
            rubric_criteria[criterion] = item.get("points", 0)

    total_score = 0.0

    for _, rubric_data in evaluations.items():
        if not isinstance(rubric_data, dict):
            continue
        criterion = rubric_data.get("criterion", "")
        weighted_score = rubric_data.get("weighted_score", 0)

        if not criterion or criterion not in rubric_criteria:
            continue

        if isinstance(weighted_score, (int, float)):
            total_score += float(weighted_score)

    return total_score


def extract_year_month(post_time: str) -> str:
    """Extract YYYY-MM from an ISO-like datetime string."""
    try:
        # Handles formats like "2025-04-08T00:00:00"
        dt = datetime.fromisoformat(post_time.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m")
    except Exception:
        return "Unknown"


def calculate_model_scores(
    model_name: str,
    evaluation_data: List[Dict[str, Any]],
    rubric_mapping: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """
    Compute per-case normalized scores for one model.

    Returns:
        dict: {case_id: {"score": float, "post_time": str, "year_month": str}}
    """
    case_scores: Dict[str, Dict[str, Any]] = {}

    for case_eval in evaluation_data:
        case_id = case_eval.get("case_id")
        evaluations = case_eval.get("evaluations", {})
        if not case_id or not isinstance(evaluations, dict):
            continue

        rubric_info = rubric_mapping.get(case_id, {})
        rubric_items = rubric_info.get("rubric_items", [])
        post_time = rubric_info.get("post_time", "")

        total_score = calculate_case_total_score(evaluations, rubric_items)
        max_possible_score = calculate_max_possible_score(rubric_items)

        if max_possible_score > 0:
            per_example_score = total_score / max_possible_score
        else:
            per_example_score = 0.0

        case_scores[case_id] = {
            "score": per_example_score,
            "post_time": post_time,
            "year_month": extract_year_month(post_time) if post_time else "Unknown",
        }

    return case_scores


def main() -> None:
    args = parse_args()

    rubric_path = Path(args.rubric_file)
    eval_dir = Path(args.evaluation_dir)
    output_path = Path(args.output_file)

    print("=" * 60)
    print("LiveMedBench: metric_calc")
    print("=" * 60)
    print(f"Rubric file        : {rubric_path}")
    print(f"Evaluation dir     : {eval_dir}")
    print(f"Output file (TSV)  : {output_path}")
    print("=" * 60)

    # Load model evaluation files
    model_files = load_model_files(eval_dir)
    print(f"\nFound {len(model_files)} evaluation result file(s):")
    for model_name in sorted(model_files.keys()):
        print(f"  - {model_name}")

    if not model_files:
        print("No evaluation_results_*.json files found. Exiting.")
        return

    # Load rubric data and build mapping by case_id
    print("\nLoading rubric data...")
    rubric_data = load_json_file(rubric_path)
    rubric_mapping: Dict[str, Dict[str, Any]] = {}
    for case in rubric_data:
        if not isinstance(case, dict):
            continue
        cid = case.get("case_id")
        if cid is None:
            continue
        rubric_mapping[str(cid)] = {
            "post_time": case.get("post_time", ""),
            "rubric_items": case.get("rubric_items", []),
        }
    print(f"Loaded rubric for {len(rubric_mapping)} cases.")

    # Load evaluations and compute per-model case scores
    print("\nLoading evaluation results and computing per-case scores...")
    all_model_scores: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for model_name, file_path in model_files.items():
        print(f"  Processing {model_name}...")
        evaluation_data = load_json_file(file_path)
        case_scores = calculate_model_scores(model_name, evaluation_data, rubric_mapping)
        all_model_scores[model_name] = case_scores
        print(f"    ✓ {len(case_scores)} cases with scores.")

    # Group by year-month
    print("\nAggregating scores by year-month...")
    monthly_scores: Dict[str, Dict[str, List[float]]] = defaultdict(
        lambda: defaultdict(list)
    )  # year_month -> model_name -> [scores]
    monthly_case_counts: Dict[str, int] = defaultdict(int)  # year_month -> count

    all_months = set()
    for model_scores in all_model_scores.values():
        for _, score_info in model_scores.items():
            year_month = score_info["year_month"]
            if year_month != "Unknown":
                all_months.add(year_month)

    # Use the first model as reference for counting cases per month
    first_model_name = next(iter(all_model_scores.keys()))

    for model_name, case_scores in all_model_scores.items():
        for case_id, score_info in case_scores.items():
            year_month = score_info["year_month"]
            if year_month == "Unknown":
                continue
            monthly_scores[year_month][model_name].append(score_info["score"])
            if model_name == first_model_name:
                monthly_case_counts[year_month] += 1

    # Compute monthly averages (clipped to [0, 1])
    monthly_avg: Dict[str, Dict[str, float]] = defaultdict(dict)
    for year_month in sorted(all_months):
        for model_name in model_files.keys():
            scores = monthly_scores[year_month][model_name]
            if scores:
                avg_score = sum(scores) / len(scores)
                monthly_avg[year_month][model_name] = max(0.0, min(1.0, avg_score))
            else:
                monthly_avg[year_month][model_name] = 0.0

    # Compute overall averages per model
    overall_avgs: Dict[str, float] = {}
    for model_name, case_scores in all_model_scores.items():
        all_scores = [info["score"] for info in case_scores.values()]
        if all_scores:
            avg = sum(all_scores) / len(all_scores)
            overall_avgs[model_name] = max(0.0, min(1.0, avg))
        else:
            overall_avgs[model_name] = 0.0

    # Write results to TSV
    print(f"\nWriting results to {output_path} ...")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    all_model_names = sorted(model_files.keys())

    with output_path.open("w", encoding="utf-8") as f:
        # Header
        header = "Date\t" + "\t".join(all_model_names) + "\t# case\n"
        f.write(header)

        # Monthly rows
        for year_month in sorted(monthly_avg.keys()):
            model_scores = monthly_avg[year_month]
            case_count = monthly_case_counts[year_month]

            score_values = [
                f"{model_scores.get(model_name, 0.0):.4f}"
                for model_name in all_model_names
            ]
            f.write(f"{year_month}\t" + "\t".join(score_values) + f"\t{case_count}\n")

        # Overall row
        total_cases = sum(monthly_case_counts.values())
        overall_values = [
            f"{overall_avgs.get(model_name, 0.0):.4f}"
            for model_name in all_model_names
        ]
        f.write(f"Overall\t" + "\t".join(overall_values) + f"\t{total_cases}\n")

    # Print summary
    print("\n[Overall statistics]")
    for model_name, avg in overall_avgs.items():
        case_count = len(all_model_scores[model_name])
        print(f"{model_name}: {avg:.4f} ({case_count} cases)")

    print(f"\n✓ Results saved to: {output_path}")
    print(f"Months covered: {len(monthly_avg)}")


if __name__ == "__main__":
    main()

