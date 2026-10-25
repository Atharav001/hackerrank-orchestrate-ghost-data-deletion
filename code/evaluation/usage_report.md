# Usage and Cost Report: Ghost Data Deletion Audit Agent

## 1. Overview
This report describes **what the running code actually did**, not the original design intent. Design still says LLM/VLM may be used for Stage 3 and unstructured Stage 5. The current implementation does **not** call any paid model API.

---

## 2. Model Configuration
- **LLM / VLM APIs used in the last local run:** none
- **What ran instead:**
  1. Stage 3: keyword heuristic in `request_classifier.py` (`heuristic-classifier` / `classification-engine` log labels). The `OPENAI_API_KEY` / `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` branch is a no-op `pass`.
  2. Stage 5: deterministic parsers for `.json`, `.sql`, `.log`, `.txt`, `.pdf`. **11 `.png` files are not parsed.** `vlm_client.py` is not used for those images.

Logged “token” numbers in `usage_log.jsonl` are **word counts / placeholders**, not provider billing tokens.

---

## 3. Token and Cost Breakdown

### Last local evaluation run (sample 32 + classifier tests)

| Metric | Value |
| :--- | :--- |
| **Paid model providers** | none |
| **Paid model calls** | **0** |
| **Stage 3 real API calls** | 0 |
| **Stage 5 real VLM calls** | 0 |
| **Billed input tokens** | 0 |
| **Billed output tokens** | 0 |
| **Estimated API cost** | **$0.00** |

A full 518-row production run has **not** been completed yet, so there is no final full-dataset usage row.

If an LLM is wired later, this file must be regenerated from real provider logs (model name, call count, input/output tokens, price).

---

## 4. Notes
1. Evidence mix in `evidence_files.csv`: 28 json, 26 log, 24 sql, 11 png, 4 pdf, 1 txt.
2. Deterministic parsers cover the non-image files. Image coverage is an open gap (see DECISIONS.md [D-19]).
3. Stages 6–11 remain code-only (no model), which is still the right split for ordering and enums.
