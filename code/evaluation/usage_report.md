# Usage and Cost Report

## Final full-dataset execution

The final run of `python3 code/main.py` on 2026-10-25 processed all 518 requests and generated root `output.csv`. The built-in contract validator reported zero errors. Output status distribution was 289 `COMPLETE`, 197 `INCOMPLETE`, and 32 `NOT_APPLICABLE`. Local Tesseract transcribed all 11 screenshot files (confidence 86.2–89.8); the confidence metric is Tesseract's estimate, not a correctness score.

| Measure | Final run |
|---|---:|
| OCR provider | Local Tesseract |
| OCR engine/version | Tesseract 5.5.3; language data 4.1.0 |
| Cloud model provider | None |
| Cloud model name | None |
| Cloud/model calls | 0 |
| Input tokens | 0 |
| Output tokens | 0 |
| Total tokens | 0 |
| Average tokens per request | 0 / 518 = 0 |
| Estimated API cost | $0.00 |
| Estimated API cost per request | $0.00 / 518 = $0.00 |

No OpenAI API key was used and no image was sent to a cloud model during this run. `openai` SDK version 2.16.0 is available in the environment and `gpt-4.1-mini` is the configurable default for optional cloud OCR. In `auto` mode, the API is called only when local OCR confidence is low and `OPENAI_API_KEY` is set; `OPENAI_OCR_MODE=openai` sends all images for transcription. If enabled later, provider-reported tokens and model names are recorded to `code/evaluation/ocr_usage.jsonl`; update this report from those actual records after that run. Never commit the key.
