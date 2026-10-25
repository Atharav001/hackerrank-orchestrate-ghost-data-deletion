# Evaluation Report: Ghost Data Deletion Audit Agent

## Measured public sample results

Command: `python3 code/evaluation/run_eval.py`, run 2026-10-25 against the 32 public requests and `dataset/sample_output.csv`.

| Metric | Measured result |
|---|---:|
| Status accuracy | 78.12% (25/32) |
| Exact ordered sequence accuracy | 12.50% (4/32) |
| Field accuracy | 30.02% |
| Cases with a status or sequence mismatch | 28/32 |

Field accuracy compares the seven required fields at each corresponding step position. Missing or extra positions each count as seven incorrect fields. Exact sequence accuracy requires equal sequence length and all fields to match in order. The seven status mismatches were case_03, case_07, case_09, case_10, case_16, case_20, and case_22.

These figures are substantially below a reliable submission quality bar. The public sample score has not been improved substantially; this report states the measured result without tuning to case IDs or expected labels.

## Improvements implemented

- Execute SQLite-compatible evidence snapshots through SQLite and derive category, state, identifiers, and record timestamps from rows.
- Resolve current and historical identifiers, with historical identity changes bounded by each request's `audit_at`.
- Match typed identifiers at token boundaries and restrict evidence observations to the audit cutoff.
- Treat affirmative sync and restore checks as recreation risks, independently from workflow success claims.
- Apply policy conditions to extracted record facts; avoid reporting a missing required-retention record as if it were present.
- Validate case IDs, row ordering, exact output schema, JSON arrays, step fields, enums, phase/state compatibility, and evidence citations.
- Remove fake model/token usage logging.
- Preserve images as explicitly unverified artifacts when no OCR backend successfully extracts their content.

## Three participant-created synthetic checks

`python3 code/evaluation/custom_cases.py` contains three synthetic checks, without real participant identities:

1. An invoice-copy inquiry without deletion authorization classifies as `NOT_A_DELETION_REQUEST`.
2. Identity changes after the audit cutoff do not enter the eligible identifier set; pre-cutoff changes do.
3. A pre-cutoff active connector observation reconstructs a `DATA_FLOW` risk and maps to `REPORT_ACTIVE_DATA_FLOW`.

These checks validate isolated components; they do not establish complete end-to-end correctness.

## Failures and remaining limitations

- Public sample sequence accuracy is 12.50%; field accuracy is 30.02%. Correct status does not imply correct evidence references or action sequences.
- Some sample expected outputs appear difficult to reconcile with the corresponding participant-facing evidence. Predictions remain evidence-based; organizer-only truth and case-family shortcuts were not used.
- OCR did not work in this execution environment: macOS Vision returns `nilError`, and Tesseract is unavailable. The 11 PNG files are represented with `IMAGE_CONTENT_UNVERIFIED`; image-only identifiers and statuses can be missed.
- The classifier and artifact parsers use deterministic rules and can miss unusual multilingual phrasing or schema variants.
- Structural validation checks format and citation membership; it cannot prove semantic validity or complete artifact coverage.
