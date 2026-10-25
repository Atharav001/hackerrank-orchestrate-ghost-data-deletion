# IMPROVEMENT.md — Full Professional Audit

**Scope:** every file in `ALL_CODE_BUNDLE.md` — `config.py`, `ingest.py`, `identity_resolver.py`, `request_classifier.py`, `vlm_client.py`, `evidence_extraction.py`, `evidence_retrieval.py`, `state_reconstruction.py`, `policy_engine.py`, `status_decision.py`, `step_generator.py`, `ordering.py`, `validator.py`, `main.py`, `schema_dump.py`, `evaluation/run_eval.py`, `evaluation/custom_cases.py`, `evaluation/evaluation_report.md`, `evaluation/usage_report.md`, `code/README.md`, `DECISIONS.md` (D-5 through D-17).
**Method:** traced every case through the 10-stage pipeline by hand, checked each stage's output against what the next stage assumes, cross-checked written claims (DECISIONS.md, usage_report.md, evaluation_report.md) against what the code actually does.
**Verdict up front:** the deterministic ordering/validation layer (`ordering.py`, `validator.py`, `run_eval.py`) is genuinely solid. The identity/evidence/classification layer has several real correctness gaps, and two of the written deliverables (`usage_report.md`'s Stage 3 numbers, and the "LLM call" framing in `ARCHITECTURE.md`/`DECISIONS.md`) describe behavior the code does not actually perform. These are flagged as CRITICAL below because an AI Judge interview will catch them in minutes.

---

## 1. Stage-by-stage wiring check

| Stage | Module | Wired correctly into main.py? | Does what it claims to do? |
|---|---|---|---|
| 1 Ingestion | `ingest.py` | Yes | Yes — strict column assertions, fails loud on mismatch. Good. |
| 2 Identity Resolution | `identity_resolver.py` | Yes | Mostly — see Finding C-1, H-1 |
| 3 Request Classification | `request_classifier.py` | Yes | **No — see Finding C-2.** Claims LLM-backed, is 100% keyword heuristic; LLM branch is a no-op `pass`. |
| 4 Evidence Retrieval | `evidence_retrieval.py` | Yes | Partially — see Finding C-3 (ID substring collision) |
| 5 Evidence Extraction | `evidence_extraction.py` + `vlm_client.py` | Partially | **No — see Finding C-4.** Image evidence is silently dropped, never reaches `vlm_client.py` at all. |
| 6 State Reconstruction | `state_reconstruction.py` | Yes | Partially — see Finding H-2 (active-risk detection too narrow/fragile) |
| 7 Policy Engine | `policy_engine.py` | Yes | Partially — see Finding H-3 (`condition` column from `deletion_rules.csv` never read), Finding H-4 (DATA_FLOW/BACKUP_ARCHIVE bypass the CSV rules entirely) |
| 8 Status Decision | `status_decision.py` | Yes | Yes — simple, correct roll-up given its inputs |
| 9 Step Generation | `step_generator.py` | Yes | Yes, for FULL_DELETION_REQUEST. **No scoping logic for PARTIAL_DELETION_REQUEST — see Finding H-5** |
| 10 Ordering | `ordering.py` | Yes | **Yes — this is the best-built module in the repo.** Real unit test covering all 15 operations, correct tie-break chain, no issues found. |
| 11 Validation | `validator.py` | Called inside `main.py` + standalone | Yes — comprehensive, correctly enforces evidence_id rules per phase/status. No issues found. |

**Takeaway:** the back half of the pipeline (7 onward) is where the real engineering is solid. The front half (identity → classification → extraction) is where silent failure modes live, and silent failure in an audit tool means false `COMPLETE` verdicts — the exact failure mode the challenge is built around.

---

## 2. Findings, severity-ranked

### CRITICAL

#### C-1. `request_classifier.py` never calls an LLM — the entire "Stage 3" story is fiction
```python
if api_key_openai or api_key_gemini or api_key_anthropic:
    try:
        # If an external client is configured, call it here
        pass
    except Exception:
        pass
_log_usage(case_id, "classification-engine", len(request_text.split()), 1)
return "FULL_DELETION_REQUEST"
```
The `CLASSIFICATION_PROMPT_TEMPLATE` constant is defined and never sent anywhere. Classification is 100% a hardcoded 11-phrase keyword list (`non_deletion_indicators`), with everything else defaulting to `FULL_DELETION_REQUEST`. The phrases in that list are lifted near-verbatim from the sample cases described in `DECISIONS.md` D-8 (`case_533`, `case_535`) — this is literally the thing you asked me to check for: hardcoded, sample-fitted logic presented as a general capability.

**Consequences:**
- Any `NOT_APPLICABLE` case in the hidden 518-set phrased differently than those 11 phrases gets misclassified as `FULL_DELETION_REQUEST` and run through a full (wrong) audit.
- `PARTIAL_DELETION_REQUEST` is defined in the prompt and in `DESIGN.md` but **the heuristic can never return it** — dead code path.
- `usage_report.md`'s claimed "518 Stage 3 Model Calls" with token/cost figures is **not measured data** — it's `len(request_text.split())` used as a fake token count, logged under a fabricated model name `"classification-engine"` / `"heuristic-classifier"`. No API was ever called. The cost table in `usage_report.md` ($0.0049) describes a run that didn't happen this way.
- `custom_cases.py`'s own test for this exact logic reuses the same hardcoded phrases as its test input — it's testing memorization against itself, not generalization.

**Fix:** either (a) actually wire a real API call behind those env-var checks and remove the keyword list as the primary path (keep it only as a fallback when no key is present, and say so explicitly), or (b) if staying fully heuristic for cost/determinism reasons, rewrite `usage_report.md` to say so honestly — report zero LLM calls for Stage 3 and explain the deterministic classifier design, rather than reporting fabricated call counts and costs. Lying to the judge by omission here is strictly worse than disclosing a design trade-off.

#### C-2. Image evidence is silently dropped before it ever reaches the VLM client
`evidence_extraction.py`'s `extract_all_evidence_records()` branches on `ext` for `.json`, `.txt`, `.sql`, `.log`, `.pdf`. **There is no branch for `.png`/`.jpg`/`.jpeg`.** The dataset README explicitly states evidence "may include PDFs, **images**, logs, JSON, plain text, or SQL snapshot exports." Any image file in the real 94-file manifest is matched by none of the `elif` branches, falls through, and contributes **zero records** to the evidence set — no error, no log line, nothing.

This means `vlm_client.py`'s image path (`extract_from_file`) is **dead code** — `evidence_extraction.py` never calls it for images at all. Separately, even if it were called, that path is itself fake:
```python
elif file_type.lower() in ["png", "jpg", "jpeg"]:
    api_key = os.environ.get("OPENAI_API_KEY") or ...
    if api_key:
        pass          # <- real call never made
    _log_vlm_usage(case_id, file_id, "vlm-image-inspector", 256, 16)  # <- hardcoded fake tokens
    return {"success": True, "text": "", "identifiers_found": []}
```
It unconditionally returns empty identifiers regardless of image content, and logs hardcoded token counts (`256`, `16`) that have nothing to do with any real call.

**Consequences:**
- If any case's only evidence of remaining data is a screenshot/scanned image, that evidence is invisible to the pipeline — the case will be wrongly scored `COMPLETE`.
- `usage_report.md`'s claim "all 94 evidence files parsed via deterministic PDF/SQL/JSON parsers" is **false** — images, if present among the 94, are parsed by nothing.
- This directly contradicts `ARCHITECTURE.md`'s Stage 5 design ("VLM needed only where data is unstructured/visual") and `DECISIONS.md` D-10's claim of having a working VLM fallback.

**Fix:** add an image branch in `evidence_extraction.py` that calls a real VLM API (or, at minimum, logs explicitly "N image files present in manifest, M skipped, 0 parsed" so the gap is visible instead of silent). Before touching code, open `evidence_files.csv` and count how many of the 94 entries are actually images — this determines how urgent the fix is.

### HIGH

#### H-1. Substring identifier matching risks cross-user contamination
`evidence_retrieval.py`:
```python
matched = False
if user_id and user_id.lower() in det_lower:
    matched = True
elif any(val in det_lower for val in all_values_lower):
    matched = True
```
and `identity_resolver.py` builds `all_values_lower` from a `len(v) >= 3` filter only — no word-boundary check. Two real risks:
1. **user_id substring collision**: `"user_1" in "...user_10 processed..."` → `True`. With IDs like `user_1`, `user_10`, `user_100`, a case for `user_1` can pick up activity/evidence that actually belongs to `user_10` or `user_100`. For a tool whose entire job is proving one user's data is gone, leaking another user's records into the findings is a serious correctness bug, not a cosmetic one.
2. **Name substring collision**: full names are added to the identifier set and matched the same way. A short/common name fragment (`"Kim"`, `"Lee"`) can match unrelated text containing a different person's name.

**Fix:** match on exact tokens / word boundaries (`re.search(r'\b' + re.escape(val) + r'\b', det_lower)`) rather than plain substring `in`, and never use a legal name as a cross-system join key — use `user_id`/`email`/`email_hash`/`phone` only.

#### H-2. Active-risk detection depends on exact English phrases, not structured state
`state_reconstruction.py` only flags an active data-flow/restore risk when `event_type == "CHECK_DATA_FLOW"` and the literal substring `"remains enabled"` appears in `details` (same pattern for `"CHECK_RESTORE_ACCESS"` / `"remains active"`). This is narrower than `DESIGN.md` §5's own spec, which calls for scanning **any** `SYNC`/`IMPORT`/`RESTORE` activity with no subsequent disable/block event — not just a specific "CHECK_*" event type with one hardcoded phrase. A real `SYNC` or `RESTORE` event that doesn't happen to be phrased with "remains enabled"/"remains active" is invisible to this logic. Given the whole premise of the challenge is sync jobs recreating deleted data, this is the detector for exactly that scenario, and it's the most fragile piece of code in the pipeline.

**Fix:** reconstruct state from structured fields (`event_type` + `reported_result`, or an explicit enabled/active flag if one exists in `system_activity.csv`) rather than free-text phrase matching. If no structured flag exists, build a small allow-list of `event_type` values that constitute "flow" events and check the latest one's result, not a literal sentence fragment.

#### H-3. `deletion_rules.csv`'s `condition` column is loaded and never used
```python
_RULES_CACHE = {row["data_category"]: row["required_action"] for _, row in df.iterrows()}
```
`ingest.py` confirms the real schema is `rule_id, data_category, condition, required_action` — four columns. `policy_engine.py` only ever reads two of them. If any rule is conditional (e.g. "RETAIN only if flagged for active fraud investigation, else DELETE"), that conditionality is silently discarded — the engine applies the same action to every record in that category regardless of circumstance. This directly undercuts the build summary's claim of "Implements all 15 rules from deletion_rules.csv" — it implements `data_category → required_action` only.

**Fix:** open `deletion_rules.csv`, read what's actually in `condition` for each of the 15 rows, and if any row has a non-trivial condition, implement it explicitly (with a DECISIONS.md entry per rule). If `condition` turns out to be empty/trivial for all 15 rows, say that explicitly in DECISIONS.md rather than leaving the column silently unread with no acknowledgment.

#### H-4. `DATA_FLOW` and `BACKUP_ARCHIVE` bypass `deletion_rules.csv` entirely
```python
if data_cat == "DATA_FLOW" or "data_flow" in res_id:
    ...
elif data_cat == "BACKUP_ARCHIVE" or "backup" in res_id:
    ...
elif req_action == "RETAIN":
    ...
```
These two categories are handled by hardcoded if/elif branches before the CSV-driven `req_action` lookup is even consulted, and partly triggered by a substring match on `resource_id` (`"backup" in res_id`) rather than the actual `data_category` field. If `deletion_rules.csv` specifies different treatment for these categories than what's hardcoded here, the CSV is silently overridden. Also fragile: any resource_id that happens to contain the substring "backup" (even if unrelated to a real backup archive) gets routed down this special path.

**Fix:** remove the resource_id substring shortcuts, route every category through the same `rules_map.get(data_cat, ...)` lookup, and implement DATA_FLOW/BACKUP_ARCHIVE-specific active-risk logic as a modifier on top of the CSV-driven action, not a replacement for it.

#### H-5. No scoping logic for `PARTIAL_DELETION_REQUEST`
`DESIGN.md` §2/§10 specify that a partial request ("delete my payment info only") should scope the audit to just that category. In the actual code, `audit_case()` in `main.py` treats `FULL_DELETION_REQUEST` and (the never-returned) `PARTIAL_DELETION_REQUEST` identically — every resource across every system is evaluated regardless of what the user actually asked for. Combined with C-1 (classifier can never even return `PARTIAL_DELETION_REQUEST`), this scoping requirement is simply unimplemented. If the hidden 518-set contains genuine partial requests, those cases will be wrongly flagged `INCOMPLETE` for retained data the user never asked to have deleted.

**Fix:** have the classifier return a `scope` (category or `None` for full) alongside the label, and filter `evaluated_resources` in `main.py`/`step_generator.py` to that scope before Stage 8.

### MEDIUM

#### M-1. SQL `INSERT` parser breaks on any value containing a comma
```python
raw_vals = [v.strip().strip("'\"") for v in vals_str.split(",")]
```
`evidence_extraction.py`'s SQL branch splits on literal commas with no quote-awareness. Any column value containing a comma (an address like `"123 Main St, Apt 4"`, a name like `"Smith, John"`, a notes field) shifts every subsequent column's value by one position — silently corrupting `resource_id` and the identifier set for that row, with no error raised. Also not handled: multi-line `INSERT` statements, escaped quotes (`O''Brien`).

**Fix:** use a real SQL statement parser (`sqlparse`) or a proper CSV-style tokenizer that respects quoting, not `str.split(",")`.

#### M-2. Inconsistent "fail-safe direction" across the `.log` parser's default states
Within `evidence_extraction.py`'s log branch, when the expected substring isn't found:
- `account_service` defaults to `PRESENT` (fails toward "flag it")
- `backup_service` defaults to `ACTIVE`/at-risk (fails toward "flag it")
- `search_service` defaults to `ABSENT` (fails toward "assume it's fine")
- `support_platform` defaults to `REDACTED` (fails toward "assume it's fine")
- `integration_service` defaults to `DISABLED` (fails toward "assume it's fine")

For an audit tool, the principled default on ambiguous/unparseable evidence should always be "assume the risk exists, don't assume compliance" — because a missed `PROBLEM` produces a false `COMPLETE`, which is the exact failure the whole challenge is about, while a false `PROBLEM` only costs an extra remediation step. Three of the five services currently default the wrong direction.

**Fix:** standardize every unmatched-pattern default to the "flag for review" state, never to the "compliant" state, across every parser branch.

#### M-3. SQL/log-derived records never distinguish "present" from "already redacted at column level"
JSON-sourced records compute a `has_pii` boolean (checks whether email/phone/customer_reference fields are populated) to decide between `PRESENT` and `REDACTED`/`ANONYMIZED`. SQL- and log-sourced records do not do this — most branches hardcode `state = "PRESENT"` for any matched row, even if the actual email/name columns in that row are already null or masked. This creates an inconsistency: the same underlying fact (a redacted record) is classified differently depending on which file format it came from.

**Fix:** apply the same `has_pii`-style check to parsed SQL rows and log lines before assigning `PRESENT` vs `REDACTED`/`ANONYMIZED`.

#### M-4. `custom_cases.py`'s 3 "custom edge cases" are weaker than they're presented as
- `custom_edge_01` (NOT_APPLICABLE): genuinely independent, hard assertion. Good.
- `custom_edge_02`: reuses a **real identity already in the dataset** (`sipho.mokoena@gmail.com`, the same email used in `identity_resolver.py`'s own unit test) rather than a constructed scenario, and its expected outcome (`INCOMPLETE`) is asserted without independent verification against raw evidence — the comment says "dynamic based on ghost evidence," i.e. assumed, not traced by hand.
- `custom_edge_03`: uses `expected_status = "COMPLETE_OR_INCOMPLETE"`, which the test code explicitly skips asserting on (`if c["expected_status"] != "COMPLETE_OR_INCOMPLETE":`). This case validates nothing — it just runs and prints.

Net effect: only 1 of the 3 required custom cases has a real, verified assertion. `evaluation_report.md` presents all 3 as validated findings, which overstates what was actually checked.

**Fix:** build 3 cases on synthetic emails/user_ids that don't exist anywhere in the real dataset, hand-trace the expected result from constructed evidence you write yourself, and assert on all 3 — not 1.

#### M-5. `output.csv` sort order uses plain lexicographic string sort on `case_id`
```python
out_df = out_df.sort_values(by="case_id").reset_index(drop=True)
```
If `case_id` values are not uniformly zero-padded to the same width across all 518 rows (e.g. `case_1`, `case_10`, `case_100`, `case_2` mixed with no padding), string sort produces the wrong order (`case_1, case_10, case_100, ..., case_2`), which would fail the grader's "sorted by case_id" requirement even though every individual row is otherwise correct. **This could not be confirmed or ruled out without the real file** — it needs a direct check.

**Fix (verify before anything else in this list):** open `dataset/deletion_requests.csv`, check whether `case_id` is consistently zero-padded (e.g. always `case_001`...`case_518`). If not, sort by the numeric suffix instead: `out_df.sort_values(by="case_id", key=lambda s: s.str.extract(r'(\d+)').astype(int)[0])`.

### LOW

- `ingest.py`'s `test_ingest()` hardcodes exact row counts (518/850/306/4011/15/94). Fine as an internal smoke test, but worth being ready to explain in interview as "structural sanity check," not an "eval," since the word choice could look like hardcoded test-label matching at a glance.
- Module-level caches (`_UIDS_DF`, `_EVIDENCE_CACHE`, etc.) are global mutable state — fine for this single-threaded script, but blocks any future parallelization of the 518-case loop without a refactor.
- `vlm_client.py`'s PDF branch calls `pypdf.PdfReader` with no retry/backoff and a bare `except Exception` that swallows the real error message into a generic `{"success": False, "error": str(e)}` — acceptable, but worth logging which files hit this path so a corrupted/unsupported PDF doesn't silently vanish the same way images do (C-2).

---

## 3. Claims-vs-code consistency check

| Written claim | Where | Actual code behavior | Match? |
|---|---|---|---|
| "Stage 3 uses a fixed LLM prompt" | ARCHITECTURE.md, DECISIONS.md D-8 | `CLASSIFICATION_PROMPT_TEMPLATE` defined, never sent; LLM branch is `pass` | **No — C-1** |
| "518 Stage 3 Model Calls... Total Estimated Cost ~$0.005" | usage_report.md | No API calls made; figures derived from `len(request_text.split())`, not real tokens | **No — C-1** |
| "All 94 evidence files parsed via deterministic PDF/SQL/JSON parsers" | usage_report.md | Images (if any in the 94) are parsed by nothing — no branch exists | **No — C-2** |
| "Implements all 15 rules from deletion_rules.csv" | user's build summary | `condition` column loaded, never read; 2 of 15 categories bypass the CSV lookup entirely | **Partially — H-3, H-4** |
| "100.0% across all 3 metrics on 32 sample cases" | evaluation_report.md | Plausible given `run_eval.py` is real and not faked, but presented with zero caveats despite known fragile logic elsewhere (H-1, H-2, M-1) that the 32-case sample may not exercise | **Technically true, overconfident framing** |
| "3 synthetic cases exercising unexercised edge rows" | user's build summary | Only 1 of 3 is independently constructed and hard-asserted | **Partially — M-4** |

This table is the one to walk through out loud before the AI Judge interview — every "No" row is a question you will get asked directly, and "I was told this was wired up but let me show you what the code actually does" is a much worse answer live than fixing it now.

---

## 4. Priority-ordered remediation plan

1. **Verify M-5 first** (5 minutes, open one file) — determines whether `output.csv` sort order is actually broken. Blocks everything else being worth doing if the output file itself fails the grader's basic sort check.
2. **Fix C-1** — either wire a real LLM call or rewrite `usage_report.md`/`ARCHITECTURE.md`/DECISIONS.md to honestly describe the deterministic classifier. This is non-negotiable before submission regardless of which path you pick — the current state is a documentation/code mismatch that actively misrepresents the system.
3. **Fix C-2** — count images in `evidence_files.csv`, add the missing branch or make the gap loud instead of silent.
4. **Fix H-1** (word-boundary matching) — small code change, removes a real cross-contamination risk.
5. **Fix H-2** (active-risk detection) — this is the detector for the challenge's core premise; worth getting right even if it takes the longest of this list.
6. **Fix H-3/H-4** — route everything through `deletion_rules.csv` uniformly, read the `condition` column.
7. **Fix H-5** — implement partial-request scoping, or explicitly document in DECISIONS.md that it's out of scope and why (acceptable only if you've confirmed the real dataset has zero partial requests).
8. **Fix M-1, M-2, M-3** — parser robustness pass.
9. **Fix M-4** — replace `custom_edge_02`/`03` with genuinely independent, hand-verified synthetic cases.
10. Re-run `run_eval.py` and `custom_cases.py` after every fix above, log the result as a new DECISIONS.md entry per the existing Phase 12 convention, and only regenerate `output.csv` once all CRITICAL + HIGH items are resolved.

Every fix above gets its own DECISIONS.md entry per your existing template — several of these (especially C-1 and H-2) are exactly the kind of "why did you build it this way" question the AI Judge is likely to ask, so the entry you write while fixing it now is the answer you'll give live later.
