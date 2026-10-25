# AGENT_INSTRUCTIONS.md — Complete Blind Build Guide

## How to use this file
You are a coding agent. Follow these steps IN ORDER. Do not skip steps. Do not combine steps. Do not improvise logic beyond what is written here or in `ARCHITECTURE.md` / `DESIGN.md` — if something is unclear or not covered, STOP and write an entry under "Open Questions Log" in `DECISIONS.md` instead of guessing, then ask the human before proceeding on that specific point. Every step below tells you exactly what file to create/edit, what it must do, and what DECISIONS.md entry to write afterward.

Read `ARCHITECTURE.md` and `DESIGN.md` fully before Step 1. They define what each module must do. This file defines the ORDER and PROCESS of building it.

---

## PHASE 0 — Repo setup

**Step 0.1.** Clone the repo if not already done:
```
git clone git@github.com:interviewstreet/hackerrank-orchestrate-october26.git
cd hackerrank-orchestrate-october26
```

**Step 0.2.** Open `README.md` (repo root) and `AGENTS.md` (repo root). Read fully. Confirm:
- the exact chat-transcript log file path for this platform (macOS/Linux and Windows paths)
- any additional rules not already captured in this instruction set
If anything in `README.md`/`AGENTS.md` conflicts with anything in `ARCHITECTURE.md`, `DESIGN.md`, or this file — the repo's own `README.md`/`AGENTS.md`/`problem_statement.md` wins. Write a DECISIONS.md entry under Phase 1 noting the conflict and resolution.

**Step 0.3.** Create the folder structure exactly as listed in `ARCHITECTURE.md` §3 under `code/`. Empty files are fine for now, just create them.

**Step 0.4.** Create `code/evaluation/` subfolder.

**Step 0.5.** Set up a Python virtual environment (or language of choice per README). Install: pandas (or equivalent dataframe lib), a PDF text extraction library, an SQLite reader, an LLM/VLM API client library, python-dotenv or equivalent for API keys. Do NOT commit API keys anywhere in the repo. Use environment variables only.

---

## PHASE 1 — Schema confirmation (MANDATORY before any logic code)

**Step 1.1.** Write `code/schema_dump.py`. It must, for every CSV under `dataset/`, print: filename, full column list, and the first 3 rows.

**Step 1.2.** Run it. Copy its full output somewhere you can refer back to.

**Step 1.3.** Compare the real column names against what `DESIGN.md` §0 assumes for `deletion_requests.csv` and `output.csv` (these were given exactly in `problem_statement.md`, should match). For `user_identities.csv`, `user_audit_log.csv`, `system_activity.csv`, `deletion_rules.csv`, `evidence_files.csv` — these were NOT given exact column names in the problem statement, only general purpose. Use the real column names from Step 1.2 output everywhere in your code going forward.

**Step 1.4.** Write a DECISIONS.md entry under "Phase 1 — Ingestion & Schema Confirmation" listing the real column names found for each file. This entry is required even if everything matched assumptions exactly — write "confirmed as expected" if so.

**Step 1.5.** Open `dataset/sample_deletion_requests.csv` and `dataset/sample_output.csv` side by side. Manually trace ONE sample case by hand: read its request_text, figure out by eye what status/steps it should produce, and compare to the actual `sample_output.csv` row for that case_id. Write what you learn about the expected format/strictness as a DECISIONS.md entry (Phase 1).

Do not proceed to Phase 2 until Steps 1.1–1.5 are complete.

---

## PHASE 2 — Ingestion layer

**Step 2.1.** Write `code/ingest.py`. It loads every `dataset/*.csv` file into a dataframe/table using the REAL column names confirmed in Phase 1. It also loads `dataset/evidence_files.csv` as the evidence manifest. Expose one function per file, e.g. `load_deletion_requests()`, `load_user_identities()`, etc., each returning a clean dataframe/table.

**Step 2.2.** Write a tiny test: load every file, print row counts, confirm `deletion_requests.csv` has 518 rows and `output.csv` template exists with the right 3 columns (even if blank).

**Step 2.3.** Write a DECISIONS.md entry under Phase 1 (or create Phase "2" header if more appropriate) confirming row counts and any surprises (nulls, duplicate ids, unexpected formats).

---

## PHASE 3 — Identity resolution

**Step 3.1.** Write `code/identity_resolver.py` implementing exactly the algorithm in `DESIGN.md` §1. Function signature: `resolve_identity(email) -> {current: {...}, historical: [...]}`.

**Step 3.2.** Test it manually against 3 cases from `dataset/sample_deletion_requests.csv`: one where the email matches current identity directly, and (if available in the sample set) one where it does not. Print the resolved identifier sets.

**Step 3.3.** Write a DECISIONS.md entry under Phase 2 describing exactly how `user_audit_log.csv` is structured (what counts as "old identifier", how changes are linked to a user_id) and confirm the resolver handles it per the real schema.

---

## PHASE 4 — Request classification

**Step 4.1.** Write `code/request_classifier.py` implementing `DESIGN.md` §2. This is the first LLM call. Use ONE fixed prompt template stored as a constant at the top of the file. The prompt must ask for exactly one of three labels back: `FULL_DELETION_REQUEST`, `PARTIAL_DELETION_REQUEST`, `NOT_A_DELETION_REQUEST`. Parse the model's response defensively (strip whitespace, uppercase, validate it's one of the 3 allowed labels — if not, retry once, then fail loudly rather than guessing).

**Step 4.2.** Log every call made here (model name, input tokens, output tokens, case_id) to a running usage log file (e.g. `code/evaluation/usage_log.jsonl`) — one line per call, append-only. This file feeds `usage_report.md` later.

**Step 4.3.** Test against all rows in `dataset/sample_deletion_requests.csv`. Manually check a few classifications make sense by reading the `request_text` yourself.

**Step 4.4.** Write a DECISIONS.md entry under Phase 3 with the exact prompt text used and why those 3 labels (not more granular) were chosen.

---

## PHASE 5 — Evidence retrieval

**Step 5.1.** Write `code/evidence_retrieval.py` implementing `DESIGN.md` §3. Pure filtering/joining, no LLM calls.

**Step 5.2.** Test against the same sample cases — confirm the returned evidence_files/system_activity rows look plausible (right identifiers, timestamps before audit_at only).

**Step 5.3.** DECISIONS.md entry under Phase 4: confirm how identifiers are matched across tables (exact string match? case-insensitive? hashed comparison for email_hash?). This detail matters and must be explicit, not assumed.

---

## PHASE 6 — Evidence extraction

**Step 6.1.** Write `code/vlm_client.py`: a thin wrapper around whichever LLM/VLM API is configured, with a single function `extract_from_file(file_path, file_type) -> structured_dict`. Include retry-once-then-fail-loud behavior and token/cost logging to the same `usage_log.jsonl` from Phase 4.

**Step 6.2.** Write `code/evidence_extraction.py` implementing `DESIGN.md` §4:
- for `json`/`log`/`sql`/`sqlite` files: parse directly with deterministic code, NO LLM call
- for `pdf`/`image` files: call `vlm_client.extract_from_file`
Use ONE fixed extraction prompt template for all VLM calls (store as constant, same rule as Phase 4).

**Step 6.3.** Test against a handful of evidence files of each type referenced by your sample cases. Print the extracted structured facts and sanity-check them against the actual file content yourself (open the PDF/image/JSON directly and compare).

**Step 6.4.** DECISIONS.md entry under Phase 5: exact extraction prompt text used for VLM calls, and confirmation that JSON/log/SQLite parsing needed no model calls (state this explicitly — it's a point the AI Judge is likely to ask about directly: "why no LLM for structured files").

---

## PHASE 7 — State reconstruction

**Step 7.1.** Write `code/state_reconstruction.py` implementing `DESIGN.md` §5. No LLM calls.

**Step 7.2.** Test: for one sample case with multiple systems touched, print the full per-resource timeline and final state. Manually verify against the raw `system_activity.csv` rows for that case.

**Step 7.3.** DECISIONS.md entry under Phase 6: document how "active risk" (unresolved SYNC/IMPORT/RESTORE) is detected precisely — what counts as "no subsequent disable/block event."

---

## PHASE 8 — Policy engine

**Step 8.1.** Before writing any code: open `dataset/deletion_rules.csv` fully and read every row. This file defines the actual policy logic — do not write `policy_engine.py` from assumption.

**Step 8.2.** Resolve the Open Question already flagged in `DECISIONS.md` ("missing required-RETAIN record" handling) using the real file content. Write the resolution as a new DECISIONS.md entry and mark the open-question checkbox resolved.

**Step 8.3.** Write `code/policy_engine.py` implementing `DESIGN.md` §6, using the real `deletion_rules.csv` structure confirmed in Step 8.1.

**Step 8.4.** Test against sample cases, print classification (OK / PROBLEM-type / CORRECTLY_RETAINED) per resource, manually verify against `sample_output.csv` findings for those cases.

**Step 8.5.** DECISIONS.md entry under Phase 7: summarize the real policy categories found in `deletion_rules.csv` and how each maps to the FINDING/REMEDIATION operations.

---

## PHASE 9 — Status decision

**Step 9.1.** Write `code/status_decision.py` implementing `DESIGN.md` §7. Trivial roll-up, no LLM calls.

**Step 9.2.** Test against all sample cases, compare resulting `deletion_status` to `sample_output.csv` exactly. Record match rate.

**Step 9.3.** DECISIONS.md entry under Phase 8: report the match rate and, for any mismatch, the root cause (traced back to which earlier stage was wrong).

---

## PHASE 10 — Step generation

**Step 10.1.** Write `code/step_generator.py` implementing `DESIGN.md` §8 exactly, including the global phase-grouping rule (D-4 in DECISIONS.md) and the evidence_id rule (D-3).

**Step 10.2.** Test against sample cases, compare generated step objects (unordered, field-by-field) against `sample_output.csv`. Record field-level match rate.

**Step 10.3.** DECISIONS.md entry under Phase 9: match rate + any remediation/verification mapping that needed a case-specific override not already in `DESIGN.md` §8.

---

## PHASE 11 — Ordering and renumbering

**Step 11.1.** Write `code/ordering.py` implementing `DESIGN.md` §9 EXACTLY. This file must contain zero LLM calls and zero randomness. Use the operation-priority table from `DESIGN.md` §0 / `config.py`, hardcoded as an ordered list — do not reconstruct ordering from string comparison of operation names.

**Step 11.2.** Write a standalone unit test: construct a synthetic unsorted list of step objects covering every operation in the priority table, run it through the sort function, assert the output order exactly matches the priority table order (and system_id/resource_id tiebreak). This test must exist as actual code, not just manual inspection.

**Step 11.3.** Test full pipeline output ordering against `sample_output.csv` for sequence accuracy.

**Step 11.4.** DECISIONS.md entry under Phase 10: sequence accuracy rate on sample set; confirm the unit test from 11.2 passes.

---

## PHASE 12 — Validation

**Step 12.1.** Write `code/validator.py` implementing every check in `DESIGN.md` — row count, sort by case_id, JSON validity, enum membership for every operation/state/phase value, evidence_id rule (empty vs non-empty per status), step_no consecutive-from-1.

**Step 12.2.** Run it against a dry pipeline output on the sample set. Fix any failures before proceeding.

**Step 12.3.** DECISIONS.md entry under Phase 11: list every validation check implemented, confirm all pass on sample set.

---

## PHASE 13 — main.py wiring

**Step 13.1.** Write `code/main.py`: read `dataset/deletion_requests.csv`, for each row run Stages 2 through 11 in order (calling the modules built above), collect all rows, run Stage 11 validation, write `output.csv`.

**Step 13.2.** Write `code/README.md`: install instructions, how to run `main.py`, how to run `evaluation/run_eval.py`, any environment variables needed.

**Step 13.3.** Run `main.py` against the SAMPLE set only first (not the full 518 yet) end-to-end as a smoke test.

---

## PHASE 14 — Sample-set evaluation

**Step 14.1.** Write `code/evaluation/run_eval.py`: runs the full pipeline on `dataset/sample_deletion_requests.csv`, computes the 3 metrics from `DESIGN.md` §11 (case-level status accuracy, step/field-level accuracy, sequence accuracy) against `dataset/sample_output.csv`.

**Step 14.2.** Run it. For every mismatch, trace back to the responsible stage, fix the root cause (not a per-case patch), re-run, repeat until accuracy is as high as reasonably achievable. Write ONE DECISIONS.md entry per distinct root-cause fix under Phase 12, following the template.

**Step 14.3.** Write `code/evaluation/custom_cases.py`: construct at least 3 synthetic cases covering rows of the edge-case matrix in `DESIGN.md` §10 NOT already exercised by the sample set (check which rows the sample set covers first, pick gaps). Run the pipeline on them, record expected-vs-actual reasoning manually (there's no ground truth for these — the correctness check is your own careful manual trace, written out).

**Step 14.4.** DECISIONS.md entry under Phase 12 summarizing the 3+ custom cases and their results.

---

## PHASE 15 — Full run and final audit

**Step 15.1.** Clear/reset the `usage_log.jsonl` file (or start a fresh one) so the final log reflects only the final production run, not all the debugging runs before it. Note this reset in DECISIONS.md.

**Step 15.2.** Run `main.py` against the FULL `dataset/deletion_requests.csv` (518 rows) to produce the final `output.csv`.

**Step 15.3.** Run `code/validator.py` against the final `output.csv` as a standalone final check (not just as part of the main.py internal call).

**Step 15.4.** Run through this checklist explicitly, one by one, ticking each:
- [ ] exactly 518 data rows
- [ ] sorted by case_id, no duplicates, no missing case_ids (diff against `deletion_requests.csv` case_id column)
- [ ] every `steps_json` is valid JSON
- [ ] every operation/state/phase value is from the allowed table, exact string match
- [ ] step_no consecutive from 1 in every row
- [ ] phase order FINDING → REMEDIATION → VERIFICATION in every row
- [ ] operation-priority + system_id/resource_id ascending order within each phase, every row
- [ ] NOT_APPLICABLE rows have literally `[]`
- [ ] COMPLETE rows: every step has non-empty evidence_id
- [ ] INCOMPLETE rows: remediation/verification steps have empty evidence_id, findings have non-empty
- [ ] manually spot-check 10–15 random rows against raw evidence files directly

**Step 15.5.** Write `code/evaluation/evaluation_report.md` per `DESIGN.md` §11, pulling the metrics and failure history directly from DECISIONS.md Phase 12/13 entries.

**Step 15.6.** Write `code/evaluation/usage_report.md` per `DESIGN.md` §12, aggregating the final `usage_log.jsonl` from the Step 15.1/15.2 run only.

**Step 15.7.** Final DECISIONS.md entry under Phase 13: full checklist results, final metrics, final token/cost totals.

---

## PHASE 16 — Packaging and submission

**Step 16.1.** Create `code.zip` containing the `code/` directory only. Explicitly EXCLUDE: virtualenv folders, `node_modules`, any build artifacts, `data/`, `dataset/`. Confirm no API keys or credentials anywhere in the zipped content (grep for common key patterns before zipping).

**Step 16.2.** Confirm the `log.txt` at the path identified in Step 0.2 exists, is non-empty, and reflects the real build session.

**Step 16.3.** Upload per `README.md` submission instructions: `code.zip`, final `output.csv`, `log.txt`.

**Step 16.4.** Before the AI Judge interview: re-read `ARCHITECTURE.md`, `DESIGN.md`, and every entry in `DECISIONS.md` start to finish, out loud if possible. Pick 3 full cases (one COMPLETE, one INCOMPLETE, one NOT_APPLICABLE) and be ready to trace each by hand from raw input row to final output row without looking at the code.

---

## Standing rule throughout all phases
If at any point a human reviewer makes an on-site decision that changes any logic described in `DESIGN.md` (e.g. overrides a remediation mapping, resolves an open question differently than first attempted, changes an ordering tiebreak) — update `DESIGN.md` itself to reflect the new correct behavior AND add the corresponding DECISIONS.md entry in the same sitting. The two files must never silently drift out of sync with the actual code.
