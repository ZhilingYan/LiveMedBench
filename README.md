## LiveMedBench: A Live Medical QA Benchmark for LLMs

LiveMedBench is a benchmark for evaluating large language models (LLMs) on **real‑world, temporally evolving medical consultation data**.  
It is designed to measure not only overall medical quality, but also **robustness over time** under a rubric‑based evaluation framework.

This repository contains:
- **Data schemas & loaders** for LiveMedBench cases and rubrics  
- **Inference scripts** for running LLMs on the benchmark  
- **Evaluation scripts** for rubric‑based grading with GPT‑4.1  
- **Metric scripts** for aggregating scores over time

If you use LiveMedBench in your research, please consider citing and acknowledging this project (see the end of this document).

---

## 1. Repository Structure

```text
LiveMedBench/
  evaluate/
    run_model.py        # Run an LLM on LiveMedBench cases
    evaluate_model.py   # Use GPT‑4.1 as a rubric-based grader
    metric_calc.py      # Aggregate scores and compute metrics
  data/                 # (Expected) benchmark data folder – see below
  outputs/              # (Recommended) folder for model outputs and evaluations
```

This repo is intentionally **minimal and model‑agnostic**.  
You can plug in any OpenAI‑compatible chat model via its model name.

---

## 2. Benchmark Challenges at a Glance

To better illustrate the design of LiveMedBench, we provide an overview figure:

![LiveMedBench Overview and Challenges](fig/livemedbench_fig_1.pdf)

This figure highlights the **core challenges** LiveMedBench aims to capture:
- **Live, time‑stamped medical consultations** rather than static exam‑style questions.  
- **Distribution shift over time** (new diseases, guidelines, and drug safety alerts).  
- **Rubric‑based multi‑axis evaluation** (e.g., Accuracy, Safety, Communication Quality) rather than single‑number correctness.  
- **Joint reasoning over narrative + core request**, which tests models’ ability to understand noisy, real patient descriptions in free text.

Together, these aspects make LiveMedBench a realistic and challenging benchmark for modern medical LLMs.

---

## 3. Data Format and Location

LiveMedBench assumes the following data layout (you may adapt paths as needed):

- **Raw / preprocessed cases**

  ```text
  data/merged_data.json
  ```

  Each entry is a single medical consultation case:

  ```json
  {
    "post_time": "2023-04-16T00:00:00",
    "narrative": "... patient description ...",
    "core_request": "... key question from the patient ...",
    "doctor_advice": "... ground‑truth doctor answer (optional) ..."
  }
  ```

- **Rubric‑augmented cases**

  ```text
  data/merged_data_rubric.json
  ```

  Each entry augments a case with rubric items:

  ```json
  {
    "case_id": "109002500",
    "post_time": "2023-04-16T00:00:00",
    "narrative": "...",
    "core_request": "...",
    "doctor_advice": "...",
    "rubric_items": [
      {
        "criterion": "Does the model identify the likely cause as Norovirus?",
        "points": 10,
        "axe": "Accuracy"
      },
      {
        "criterion": "Does the model recommend antibiotics?",
        "points": -5,
        "axe": "Safety"
      }
    ]
  }
  ```

> **Note**: This repository does not ship clinical data by default.  
> Place your own LiveMedBench JSON files under `data/` following the schemas above.

---

## 4. Environment Setup

We use the official `openai` Python client with **environment‑based credentials**.

```bash
conda create -n livemedbench python=3.10 -y
conda activate livemedbench

pip install openai
```

Set your OpenAI API key (no keys are stored in this repo):

```bash
export OPENAI_API_KEY="sk-..."  # DO NOT hard-code this in code
```

---

## 5. Running Models on LiveMedBench

The script `evaluate/run_model.py` runs a chat model on all cases and saves the responses.

### 4.1 Basic Usage

```bash
cd /data2/zhiling/Code/llm/LiveMedBench

python evaluate/run_model.py \
  --data-file data/merged_data.json \
  --output-file outputs/gpt_4_1_results.json \
  --model gpt-4.1
```

Key arguments:
- **`--data-file`**: path to a JSON list of cases (`merged_data.json`).  
- **`--output-file`**: where to save model outputs.  
- **`--model`**: any OpenAI chat model name (e.g., `gpt-4.1`, `gpt-4.1-mini`, `gpt-5.2-*`).  
- **`--max-cases`** (optional): limit the number of processed cases (for debugging).  
- **`--resume`** (optional): resume from an existing output file by `case_id`.

### 4.2 Model Prompting

For each case, we build the prompt as:

```text
instruction  +  narrative  +  core_request
```

- If the content contains Chinese, we ask the model to answer **in Chinese** without intermediate reasoning.
- Otherwise we use an English instruction:  
  “Provide ONLY the final answer to the following question, without any explanation or reasoning steps.”

The resulting JSON output contains per‑case fields:

```json
{
  "post_time": "...",
  "narrative": "...",
  "core_request": "...",
  "model_response": "...",
  "finish_reason": "...",
  "doctor_advice": "..."
}
```

---

## 6. Rubric‑based Evaluation with GPT‑4.1

The script `evaluate/evaluate_model.py` uses **GPT‑4.1 (version `gpt-4.1-2025-04-14`)** as an **objective rubric‑based grader**.

### 5.1 System Prompt

We follow the *Rubric‑based Grader* design:

- **Role**: Objective Grader  
- **Task**: Evaluate the model response against the provided rubric \(R\).  
- **Binary decision**: for each criterion, return **Met** or **Not Met**.  
- **Positive criteria**: Met if the required information is present.  
- **Negative criteria**: Met if the model commits the specified error.  
- **Evidence**: briefly quote the sentence from the model output (and user query) that supports your decision.

The grader sees:
- **User Query (Q)** = `narrative + "\n\n" + core_request`  
- **Model Response (M_out)`** = the model output from `run_model.py`  
- **Rubric (R)** = one criterion at a time, as a short JSON list  
and returns a JSON list with one object:

```json
[
  {
    "question": "... criterion ...",
    "met": true,
    "reasoning": "..."
  }
]
```

Internally we convert `met` to a binary score (1 or 0), then multiply by `points` to obtain `weighted_score`.

### 5.2 Running the Evaluator

```bash
python evaluate/evaluate_model.py \
  --rubric-file data/merged_data_rubric.json \
  --model-result-file outputs/gpt_4_1_results.json \
  --output-file outputs/evaluation_results_gpt_4_1.json \
  --response-field model_response \
  --resume
```

Arguments:
- **`--rubric-file`**: rubric‑augmented cases (`merged_data_rubric.json`).  
- **`--model-result-file`**: outputs from `run_model.py`.  
- **`--output-file`**: where to save evaluation results.  
- **`--response-field`**: field name for the model’s answer (default `model_response`).  
- **`--max-cases`**, **`--resume`**: optional debugging / recovery flags.

Each evaluation file `evaluation_results_<model>.json` is a list of:

```json
{
  "case_id": "...",
  "evaluations": {
    "rubric_1": {
      "criterion": "...",
      "points": 10,
      "axe": "Accuracy",
      "score": 1,
      "weighted_score": 10
    },
    ...
  }
}
```

---

## 7. Benchmark Results and Metrics

We summarize benchmark results and trends in the following figure:

![LiveMedBench Benchmark Results](fig/livemedbench_fig_2.pdf)

The figure illustrates:
- **Per‑month performance trajectories** of different LLMs on LiveMedBench.  
- **Performance gaps across axes** (e.g., some models are strong in Accuracy but weaker in Safety or Communication).  
- **Temporal generalization**: how quickly models adapt to newly emerging medical knowledge and guidelines.

These visualizations are generated from the rubric‑based scores produced by `evaluate_model.py` and aggregated by `metric_calc.py`.

---

## 8. Metric Computation

`evaluate/metric_calc.py` aggregates rubric‑based scores and reports **per‑month** and **overall** metrics.

### 6.1 Usage

```bash
python evaluate/metric_calc.py \
  --rubric-file data/merged_data_rubric.json \
  --evaluation-dir outputs \
  --output-file outputs/metric_results.txt
```

The script:
1. Scans `--evaluation-dir` for files named `evaluation_results_*.json`.  
2. For each case:
   - `max_possible_score` = sum of all **positive** `points` in its rubric.  
   - `total_score` = sum of `weighted_score` over rubric items present in the rubric file.  
   - `per_example_score` = `total_score / max_possible_score` (clipped to \[0,1\]).  
3. Groups scores by `post_time` (year‑month, `YYYY-MM`) and computes:
   - Monthly average score per model.  
   - Global average score per model.

The output file is a TSV table:

```text
Date    model_A   model_B   ...   # case
2023-01 0.8123    0.7654    ...   42
2023-02 0.8350    0.7810    ...   38
...
Overall 0.8240    0.7730    ...   500
```

---

## 9. Reproducibility Notes

- **Deterministic evaluation**:  
  - All evaluator calls in `evaluate_model.py` use **`temperature = 0.0`**.  
  - `run_model.py` also defaults to `temperature = 0.0` for fair comparison.
- **Checkpoints & resume**:  
  - Both `run_model.py` and `evaluate_model.py` support checkpointing and `--resume` to safely handle long‑running experiments.
- **Model names**:  
  - You can plug in any OpenAI chat model; we recommend logging the exact version (e.g., `gpt-4.1-2025-04-14`) when reporting results.

---

## 10. Acknowledgements

LiveMedBench builds upon real‑world online medical consultation data and rubric‑based evaluation methodology.  
We thank the clinicians, annotators, and open‑source community members who made this benchmark possible, as well as the maintainers of related projects (such as MedOnline and Medical‑SAM‑Bench) for inspiration on data processing and evaluation design.  
If you extend or adapt LiveMedBench, please acknowledge this repository and the underlying work in your publications.  

