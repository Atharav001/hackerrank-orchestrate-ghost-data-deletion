# Ghost Data Deletion Audit Agent — HackerRank Orchestrate (October 2026)

## Overview
This solution implements an AI-powered data deletion audit agent for Northstar Shop. For every deletion request, the agent resolves current and historical identity identifiers, searches global operational activity and evidence files, applies retention policies, reconstructs the true deletion state at `audit_at`, and generates strictly ordered findings, remediation steps, and verification checks.

## Architecture
- **Stage 1 (Ingestion):** Loads participant CSVs (`deletion_requests.csv`, `user_identities.csv`, `user_audit_log.csv`, `system_activity.csv`, `deletion_rules.csv`, `evidence_files.csv`).
- **Stage 2 (Identity Resolution):** Reconstructs complete identifier sets (current + historical emails, phones, hashes, names) with case-insensitive normalization.
- **Stage 3 (Request Classification):** Distinguishes deletion authorizations from non-deletion inquiries (`NOT_APPLICABLE`).
- **Stage 4 & 5 (Evidence Retrieval & Extraction):** Indexes and extracts facts across 94 evidence files (JSON, SQL replicas, logs, text handovers, PDFs).
- **Stage 6 (State Reconstruction):** Fuses evidence proof over activity claims at cutoff time `audit_at`.
- **Stage 7 (Policy Engine):** Applies `deletion_rules.csv` mapping categories to required treatments (`DELETE`, `REDACT`, `ANONYMIZE`, `RETAIN`).
- **Stage 8 & 9 (Status & Step Generation):** Derives `COMPLETE`, `INCOMPLETE`, or `NOT_APPLICABLE` and generates phase-grouped steps.
- **Stage 10 (Deterministic Ordering):** Enforces strict phase ordering (`FINDING` -> `REMEDIATION` -> `VERIFICATION`) and operation-priority sorting.
- **Stage 11 (Validation):** Verifies all schema, enum, array consecutive numbering, and evidence rules.

## Installation & Requirements
- Python 3.10+
- Python packages: `pandas`, `pypdf`; optional `openai` SDK for cloud OCR fallback.
- Local image OCR: Tesseract 5.5+ with `eng` and `jpn` language data. Other Tesseract language packs are used automatically when installed.

macOS:
```bash
brew install tesseract tesseract-lang
python3 -m pip install -r code/requirements.txt
```

Debian/Ubuntu:
```bash
sudo apt-get install tesseract-ocr tesseract-ocr-eng tesseract-ocr-jpn
python3 -m pip install -r code/requirements.txt
```

### OCR configuration

OCR runs locally by default. The default `OPENAI_OCR_MODE=auto` uses Tesseract when confidence is adequate and calls OpenAI only for low-confidence images when `OPENAI_API_KEY` is set. To send every image directly for transcription, set `OPENAI_OCR_MODE=openai`; to stay local regardless of key, set `OPENAI_OCR_MODE=local`.

```bash
# Optional cloud OCR. Keep the key in the environment; never commit it or paste it into source/logs.
export OPENAI_API_KEY="..."
export OPENAI_OCR_MODE="auto" # auto | local | openai
export OPENAI_OCR_MODEL="gpt-4.1-mini"
python3 code/main.py
```

OpenAI is asked to transcribe visible text only. Image text is untrusted evidence: embedded instructions are transcribed as data and are never followed or executed. OCR output only feeds the existing identifier/resource/policy parsers; it cannot invoke tools or change program logic. Calls, model, and provider-reported token counts are appended to `code/evaluation/ocr_usage.jsonl` for usage accounting. Review the model's current image input limits and pricing before enabling direct API mode.

## How to Run

### Run the full pipeline
From the repository root:
```bash
python3 code/main.py
```
This generates `output.csv` with exactly 518 data rows at the repository root.

### Run evaluation
```bash
python3 code/evaluation/run_eval.py
```

### Run schema validation standalone
```bash
python3 code/validator.py
```

### Sample evaluation and known evidence behavior

Run `python3 code/evaluation/run_eval.py` for the public 32-case comparison. The evaluation report records the measured metrics from the latest run. When no OCR backend is available, image artifacts remain represented with an `IMAGE_CONTENT_UNVERIFIED` marker. The run never counts heuristic word estimates as provider tokens.
