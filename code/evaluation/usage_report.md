# Usage and Cost Report

## Final full-dataset execution

The final full run used `python3 code/main.py` on 2026-10-25, processed all 518 requests, and generated the root `output.csv`. The built-in validator completed with zero contract errors.

| Measure | Recorded result |
|---|---:|
| Provider | None |
| Model name | None; deterministic local Python implementation |
| Model calls | 0 |
| Input tokens | 0 |
| Output tokens | 0 |
| Total tokens | 0 |
| Average tokens per request | 0 / 518 = 0 |
| Estimated API cost | $0.00 |
| Estimated API cost per request | $0.00 / 518 = $0.00 |

There are no per-model subtotals because no model provider was called. Classification, parsing, identity resolution, policy evaluation, and serialization are local deterministic code. PDF extraction uses `pypdf`. Local image OCR was attempted, but Vision failed with `nilError` and Tesseract was not installed; no paid vision model was used. The 11 image artifacts are flagged unverified. Fake word-count token logs were removed and are not treated as usage.
