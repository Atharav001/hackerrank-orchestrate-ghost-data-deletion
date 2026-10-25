# DESIGN.md — Ghost Data Deletion Audit Agent

This file specifies exact logic. ARCHITECTURE.md says what the pieces are; this file says precisely how each piece behaves. If anything here conflicts with the actual `dataset/*.csv` headers once opened, DESIGN.md must be updated immediately (see DECISIONS.md logging rule) — never silently code around a mismatch.

## 0. Confirmed schemas (from problem_statement.md — do not guess further than this)

**`deletion_requests.csv`** (input, 518 rows):
```
case_id, email, requested_at, reported_status, reported_at, audit_at, request_text
```
`reported_status` ∈ {COMPLETE, PARTIALLY_COMPLETE, NOT_STARTED} — treat as an unverified CLAIM, never as ground truth.

**`output.csv`** (required output, 518 rows, sorted by case_id):
```
case_id, deletion_status, steps_json
```
`deletion_status` ∈ {COMPLETE, INCOMPLETE, NOT_APPLICABLE}

**Step object** (each element inside the `steps_json` array):
```json
{
  "step_no": 1,
  "phase": "FINDING | REMEDIATION | VERIFICATION",
  "system_id": "string",
  "resource_id": "string",
  "operation": "<see table below>",
  "state": "<see table below>",
  "evidence_id": "string or empty"
}
```

### Allowed operation/state table (exact strings, case-sensitive, copy verbatim)

| # | Phase | Operation | State |
|---|---|---|---|
| 1 | FINDING | REPORT_REMAINING_RECORD | PRESENT |
| 2 | FINDING | REPORT_EXPOSED_PII | PRESENT |
| 3 | FINDING | REPORT_ACTIVE_DATA_FLOW | ACTIVE |
| 4 | FINDING | REPORT_RESTORE_RISK | ACTIVE |
| 5 | REMEDIATION | DISABLE_DATA_FLOW | DISABLED |
| 6 | REMEDIATION | BLOCK_RESTORE | BLOCKED |
| 7 | REMEDIATION | DELETE_RECORD | ABSENT |
| 8 | REMEDIATION | REDACT_RECORD | REDACTED |
| 9 | REMEDIATION | ANONYMIZE_RECORD | ANONYMIZED |
| 10 | VERIFICATION | VERIFY_RECORD_ABSENT | ABSENT |
| 11 | VERIFICATION | VERIFY_RECORD_PRESENT | PRESENT |
| 12 | VERIFICATION | VERIFY_RECORD_REDACTED | REDACTED |
| 13 | VERIFICATION | VERIFY_RECORD_ANONYMIZED | ANONYMIZED |
| 14 | VERIFICATION | VERIFY_DATA_FLOW_DISABLED | DISABLED |
| 15 | VERIFICATION | VERIFY_RESTORE_BLOCKED | BLOCKED |

The `#` column above IS the operation-priority index used in Stage 10 sort. Store this table as an ordered list/dict in `config.py`. Never derive this order any other way (not alphabetical, not by first-seen).

## 1. Stage 2 — Identity Resolution algorithm

```
INPUT: case row (has `email`)
1. Look up `email` in user_identities.csv → get current user_id + all current identifier fields.
   - If no match: still proceed — the email may ONLY exist historically (this is the exact
     "ghost" failure mode in the story). Do not early-exit on "not found".
2. Look up user_id (if found) OR email (if not) in user_audit_log.csv →
   collect every historical identifier ever associated with this user
   (old emails, old email_hash, old phone, old name).
3. Build identifier_set = {current fields} ∪ {all historical fields}.
4. Output: identifier_set, tagged with which are CURRENT vs HISTORICAL
   (needed later — tombstone rules only permit the stable user_id reference,
   not any direct identifier, current or historical).
```

## 2. Stage 3 — Request Classification algorithm

```
INPUT: request_text
1. Classify into one of:
   a. FULL_DELETION_REQUEST   → user_id scope = ALL records
   b. PARTIAL_DELETION_REQUEST → scope = named category only (e.g. "delete my payment info")
   c. NOT_A_DELETION_REQUEST   → e.g. a question, a complaint, a data-access request, unrelated text
2. If (c): deletion_status = NOT_APPLICABLE, steps_json = [], SKIP all remaining stages for this case.
3. If (a) or (b): record scope, continue to Stage 4 with scope passed through.
```
This is the one place an LLM call is justified for a classification decision — keep the prompt narrow: "classify this single piece of text into exactly one of these 3 labels, return label only." Do not let it also decide deletion_status here.

## 3. Stage 4 — Evidence Retrieval algorithm

```
INPUT: identifier_set, audit_at
1. Filter evidence_files.csv rows where any referenced identifier/case matches identifier_set.
2. Filter system_activity.csv rows where identifier matches identifier_set
   AND timestamp <= audit_at   (never use activity after the audit cutoff — the agent is
   proving state AS OF audit_at, not "as of now").
3. Return both filtered sets, plus file paths for Stage 5.
```

## 4. Stage 5 — Evidence Extraction algorithm

```
FOR each evidence file in the filtered set:
  IF file type in {json, log, sql/sqlite}:
      parse directly with deterministic code (json.load / line parser / sqlite3 query)
      → extract: which identifiers present, which system/resource, what operation recorded
  IF file type in {pdf, image}:
      send to VLM with a FIXED extraction prompt (same prompt every time, no per-case customization)
      asking it to return: identifiers visible, system/resource context, apparent record state
      → parse VLM's JSON response into the same structured shape as above
  Record every extraction with its source evidence_id — this evidence_id is what
  later gets cited in FINDING/VERIFICATION steps.
```

Fixed VLM prompt must be stored in a single constant/template file so it is auditable and reused identically across all cases (grader / judge interview may ask "did you use the same prompt for every case" — answer must be yes).

## 5. Stage 6 — State Reconstruction algorithm

```
FOR each (system_id, resource_id) touched by retrieved evidence/activity:
  1. Build an ordered timeline of system_activity events (by timestamp) up to audit_at.
  2. Determine the LAST operation applied (e.g. DELETE, SYNC, IMPORT, RESTORE, INDEX, EXPORT).
  3. Cross-check against extracted evidence (Stage 5) — does actual evidence content
     agree with what the activity log claims? If an activity log says "DELETE complete"
     but evidence file still shows identifiers present → evidence wins, log is the claim,
     evidence is the proof.
  4. Separately: scan for ANY activity record with operation ∈ {SYNC, IMPORT, RESTORE}
     whose status is ACTIVE/ENABLED and whose timestamp is <= audit_at with no
     subsequent DISABLE/BLOCK event → this is an active data-flow or restore risk,
     regardless of whether the target record currently exists.
  5. Output per resource: {current_state, identifiers_present: [...], active_risk: bool/type}
```

## 6. Stage 7 — Policy Engine algorithm

```
FOR each resource state from Stage 6:
  1. Look up its data category in deletion_rules.csv → get required_treatment
     (DELETE / REDACT / ANONYMIZE / RETAIN) and permitted_identifiers (if RETAIN or
     tombstone-permitted).
  2. Classify:
     - required_treatment == RETAIN and record present with only permitted fields
         → CORRECTLY_RETAINED (contributes to COMPLETE, generates VERIFY_RECORD_PRESENT later)
     - required_treatment == RETAIN but record MISSING
         → PROBLEM type MISSING_REQUIRED_RECORD (special finding — record that should
           exist doesn't; still blocks COMPLETE status, but has no matching operation
           in the allowed table for "missing retained record" as a finding — handle via
           REPORT_REMAINING_RECORD is wrong; re-check deletion_rules.csv wording and
           problem_statement.md before coding this branch — flag as OPEN QUESTION in
           DECISIONS.md if ambiguous, do not guess silently)
     - required_treatment == DELETE and record ABSENT → OK (no finding)
     - required_treatment == DELETE and record PRESENT → PROBLEM: REPORT_REMAINING_RECORD
     - required_treatment ∈ {REDACT, ANONYMIZE} and record present but still contains
       disallowed identifiers → PROBLEM: REPORT_EXPOSED_PII
     - required_treatment ∈ {REDACT, ANONYMIZE} and record present with only permitted
       fields → OK (already treated correctly)
     - active_risk == data_flow → PROBLEM: REPORT_ACTIVE_DATA_FLOW
     - active_risk == restore  → PROBLEM: REPORT_RESTORE_RISK
```

## 7. Stage 8 — Status Decision algorithm

```
IF Stage 3 classified NOT_A_DELETION_REQUEST → NOT_APPLICABLE (already short-circuited)
ELSE IF any PROBLEM classification exists across all resources for this case → INCOMPLETE
ELSE (every resource is OK or CORRECTLY_RETAINED, zero active risks) → COMPLETE
```

## 8. Stage 9 — Step Generation algorithm

```
IF status == NOT_APPLICABLE:
   steps_json = []

IF status == COMPLETE:
   FOR each resource classified OK or CORRECTLY_RETAINED:
      emit ONE verification step matching its final state:
        - deleted record  → VERIFY_RECORD_ABSENT / ABSENT
        - retained record → VERIFY_RECORD_PRESENT / PRESENT
        - redacted record → VERIFY_RECORD_REDACTED / REDACTED
        - anonymized record → VERIFY_RECORD_ANONYMIZED / ANONYMIZED
        - disabled flow → VERIFY_DATA_FLOW_DISABLED / DISABLED
        - blocked restore path → VERIFY_RESTORE_BLOCKED / BLOCKED
      evidence_id = the real evidence_id/activity_id/audit_id that proves this (REQUIRED, non-empty)

IF status == INCOMPLETE:
   FOR each resource classified PROBLEM:
      1. emit the matching FINDING step (from Stage 7 classification), evidence_id = real id (REQUIRED)
      2. emit the matching REMEDIATION step (same resource), evidence_id = "" (proposed, not executed)
         mapping: REPORT_REMAINING_RECORD → DELETE_RECORD (or REDACT/ANONYMIZE if
                  deletion_rules.csv requires keeping a tombstone for that category — check
                  policy first, do not default to DELETE_RECORD blindly)
                  REPORT_EXPOSED_PII → REDACT_RECORD or ANONYMIZE_RECORD (per deletion_rules.csv)
                  REPORT_ACTIVE_DATA_FLOW → DISABLE_DATA_FLOW
                  REPORT_RESTORE_RISK → BLOCK_RESTORE
      3. emit the matching VERIFICATION step (same resource), evidence_id = ""
         mapping: DELETE_RECORD → VERIFY_RECORD_ABSENT
                  REDACT_RECORD → VERIFY_RECORD_REDACTED
                  ANONYMIZE_RECORD → VERIFY_RECORD_ANONYMIZED
                  DISABLE_DATA_FLOW → VERIFY_DATA_FLOW_DISABLED
                  BLOCK_RESTORE → VERIFY_RESTORE_BLOCKED
   Collect ALL findings first, then ALL remediations, then ALL verifications across every
   resource — do NOT interleave finding/remediation/verification per-resource. Phase
   grouping is global per case, not per resource.
```

## 9. Stage 10 — Ordering algorithm (deterministic, no exceptions)

```
1. Partition steps into three buckets by phase: FINDING, REMEDIATION, VERIFICATION.
2. Within each bucket, sort by:
   a. operation priority index (table in §0, ascending)
   b. then system_id (ascending, string sort)
   c. then resource_id (ascending, string sort)
3. Concatenate buckets in order: FINDING + REMEDIATION + VERIFICATION.
4. Renumber step_no sequentially starting at 1 across the full concatenated list.
```

## 10. Edge-case matrix (must all be explicitly handled, not accidentally handled)

| Case | Handling |
|---|---|
| Email in request doesn't match any current identity | Still check historical identifiers before concluding no data (§1 step 1) |
| Conflicting evidence sources (activity log vs file content disagree) | Evidence content wins over log claim (§5 step 3); log conflict + resolution in DECISIONS.md if first time seen |
| Record correctly retained per policy | Must NOT be flagged as problem; gets a PRESENT verification if COMPLETE |
| Active sync/restore risk but target record currently absent | Still INCOMPLETE — risk alone blocks COMPLETE even with no literal record present |
| Tombstone record (user_id kept, direct identifiers required gone) | Treat as its own resource check: user_id presence = OK by design; direct identifier fields on that SAME record checked separately for REPORT_EXPOSED_PII |
| Partial deletion request (named category only) | Only resources in that category enter Stage 6–9; everything else out of scope, not evaluated |
| COMPLETE case, no evidence_id available for a required proof | Cannot be COMPLETE without evidence — re-classify as INCOMPLETE and log why in DECISIONS.md (should be rare; if frequent, re-check Stage 4 retrieval logic first) |
| Multiple historical identities overlapping across systems inconsistently | Union all, never pick "most recent only" — a system could still reference an old identifier |

## 11. Evaluation design (for `evaluation_report.md`)

Metrics to compute via `run_eval.py` against `sample_output.csv`:
1. **Case-level status accuracy** — % of cases where `deletion_status` matches exactly
2. **Step-level / field-level accuracy** — per matched case, % of step objects with all fields identical to expected
3. **Sequence accuracy** — % of matched cases where array order matches exactly (not just set-equality)
4. **3+ custom cases** — hand-construct synthetic cases hitting rows of the edge-case matrix above that the sample set does NOT cover; run pipeline on them; document expected vs actual
5. **Failures found + fixes made** — running log, pulled directly from DECISIONS.md phase entries (do not rewrite history — copy forward)

## 12. Usage/cost tracking design (for `usage_report.md`)

Every LLM/VLM call (Stage 3 classification, Stage 5 extraction) must log: model name/provider, input tokens, output tokens, case_id it was for. Aggregate at end of final full run into: total calls, total/avg tokens per request, total/avg cost per request, broken down per model if multiple models used.
