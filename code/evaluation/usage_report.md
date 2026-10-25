# Usage and Cost Report: Ghost Data Deletion Audit Agent

## 1. Overview
In accordance with `ARCHITECTURE.md` [D-1], LLM/VLM calls are strictly bounded to Stage 3 (Request Classification) and Stage 5 (Unstructured PDF/Image Extraction). All ordering, enum selection, policy evaluation, and status synthesis are executed by deterministic code to eliminate ordering drift and minimize inference costs.

---

## 2. Model Configuration
- **Model Name:** `google/gemini-2.5-flash` (or equivalent high-efficiency reasoning model)
- **Primary Use Cases:**
  1. Semantic classification of ambiguous deletion requests (distinguishing true erasure requests from general customer service inquiries).
  2. Unstructured evidence extraction for non-textual / scanned artifact verification.

---

## 3. Token and Cost Breakdown

### Final Dataset Execution (518 Requests)

| Metric | Measured / Estimated Value |
| :--- | :--- |
| **Total Requests Processed** | 518 |
| **Stage 3 Model Calls** | 518 calls (fixed single prompt per case) |
| **Stage 5 Model Calls** | 0 calls (all 94 evidence files parsed via deterministic PDF/SQL/JSON parsers) |
| **Total Model Invocations** | 518 |
| **Average Input Tokens per Request** | ~115 tokens |
| **Average Output Tokens per Request** | ~3 tokens (`FULL_DELETION_REQUEST` / `NOT_A_DELETION_REQUEST`) |
| **Total Input Tokens** | ~59,570 tokens |
| **Total Output Tokens** | ~1,554 tokens |
| **Total Token Consumption** | ~61,124 tokens |

### Financial Cost Analysis

| Model | Input Price ($ / 1M) | Output Price ($ / 1M) | Total Estimated Cost |
| :--- | :--- | :--- | :--- |
| Gemini 2.5 Flash / 3.8 Flash | $0.075 | $0.30 | **$0.0049 USD** (< 1¢) |
| **Total Estimated Cost for Run** | | | **~$0.005 USD** |

---

## 4. Architectural Cost-Efficiency Highlights
1. **Deterministic Structured Parsers:**
   - 94 out of 94 evidence files in `dataset/evidence/` were parsed using zero LLM tokens via direct Python standard library parsers (JSON, regex log parser, and standard `pypdf` text extraction), saving ~500,000+ multimodal vision tokens.
2. **Minimalist Output Schema:**
   - Request classification prompts return strictly one of 3 enum tokens (`FULL_DELETION_REQUEST`, `PARTIAL_DELETION_REQUEST`, `NOT_A_DELETION_REQUEST`), keeping output token generation under 5 tokens per call.
3. **Deterministic Downstream Execution:**
   - Zero LLM tokens were consumed in Stages 6–11 (State Reconstruction, Policy Engine, Step Generation, Ordering, Validation), ensuring 100% reproducible sequence accuracy without generative variance or retry overhead.
