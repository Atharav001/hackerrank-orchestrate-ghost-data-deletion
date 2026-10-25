# Evaluation Report: Ghost Data Deletion Audit Agent

## Measured public sample results

Command: `python3 code/evaluation/run_eval.py`, run 2026-10-25 after enabling local Tesseract OCR and resource-aware image evidence linking. It compared all 32 public requests with `dataset/sample_output.csv`.

| Metric | Measured result |
|---|---:|
| Status accuracy | 78.12% (25/32) |
| Exact ordered sequence accuracy | 12.50% (4/32) |
| Field accuracy | 30.02% |
| Cases with a status or sequence mismatch | 28/32 |

Field accuracy compares the seven required fields at corresponding step positions. Missing or extra positions count as incorrect fields. Exact sequence accuracy requires equal sequence length and every field to match in order. Status mismatches: case_03, case_07, case_09, case_10, case_16, case_20, and case_22.

These scores remain weak and are not submission-quality semantic accuracy. Enabling OCR did not improve the measured public sample metrics; the evaluation was not tuned to case IDs or expected labels.

## Full output validation

`python3 code/main.py` processed the full dataset and wrote root `output.csv`. Its built-in validator completed with zero errors. An independent validation also checked all 518 expected unique case IDs, natural numeric ordering, exact CSV header, JSON arrays, exact step keys, consecutive numbering, phase/state/operation rules, and allowed evidence references.

## Image OCR and evidence handling

- Installed Tesseract 5.5.3 and Tesseract language data 4.1.0, including English and Japanese.
- Local Tesseract transcribed all 11 of 11 screenshot evidence files. Its reported confidence values ranged from 86.2 to 89.8; these confidence scores are not an independently measured OCR word-accuracy rate.
- Resource IDs are separated from identity identifiers and linked to nearby OCR identity tokens. Artifacts with no direct PII can also be connected through participant-visible identity-link activity and resource IDs.
- OCR text is treated only as untrusted evidence data. The optional OpenAI path is prompted for literal transcription and cannot execute image text as commands or tool instructions.

## Participant-created synthetic checks

`python3 code/evaluation/custom_cases.py` passes three component-level checks:

1. An invoice-copy inquiry without deletion authorization classifies as `NOT_A_DELETION_REQUEST`.
2. Identity changes after an audit cutoff are excluded; pre-cutoff history remains eligible.
3. An affirmative pre-cutoff connector check maps to `REPORT_ACTIVE_DATA_FLOW`.

`python3 code/evaluation/test_image_ocr_safety.py` also passes checks that adversarial-looking OCR content remains literal text and direct API mode requires an environment key. These tests exercise components, not complete end-to-end correctness.

## Improvements made

- SQLite-compatible SQL evidence is executed through SQLite and normalized from row and table facts.
- Identity history and evidence are bounded by each case's `audit_at`.
- Activity checks distinguish workflow claims from explicit active sync and restore risks.
- Policy conditions are evaluated from extracted facts; missing retained records are not invented as present.
- Image evidence is transcribed locally, linked using resource and identity evidence, and retained with explicit uncertainty if OCR is unavailable.
- Optional OpenAI OCR supports `auto`, `local`, and direct `openai` modes; API calls record provider-reported token counts.
- Output validation checks schema, IDs, ordering, step fields, states, phases, and evidence references.

## Remaining limitations

- Public sample accuracy remains 78.12% status, 12.50% exact sequence, and 30.02% field accuracy. Many predicted step sequences do not match the public sample answer.
- Some public expected outputs appear difficult to reconcile with participant-facing evidence. No hidden organizer truth or case-family shortcut was used.
- OCR confidence is not proof every word or identifier was read correctly; image OCR can still misread text. The OpenAI vision API fallback is implemented but was not live-tested or called in this run because no API key was supplied.
- Deterministic request, artifact, and policy parsing can miss unusual multilingual phrasing or schema variations.
- Structural validation does not establish semantic completeness or hidden-set performance.
