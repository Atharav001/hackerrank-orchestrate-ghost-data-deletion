# DECISIONS.md — Living Decision Log

## How to use this file (read before editing)

This file is append-only in spirit: never delete or rewrite a past entry, even if later proven wrong. If a decision changes, add a NEW entry that supersedes it and link back to the old entry number. The point is a full audit trail of reasoning, so you (and the AI Judge) can see not just what was built but what was considered and rejected.

**Every entry uses this exact template:**
```
### [D-<number>] <short title>
- Phase: <which build phase, matches AGENT_INSTRUCTIONS.md phase numbers>
- Date/step: <when during the build>
- Decision: <what was decided, one or two sentences>
- Why: <the reasoning>
- Alternatives considered: <what else was possible>
- What would have happened with the alternative: <concrete consequence — be specific,
  not "it would be worse"; e.g. "would have broken sequence accuracy because X">
- Status: ACTIVE | SUPERSEDED by [D-<n>]
```

**Rule for the coding agent:** write a new entry EVERY time any of the following happens, in the same turn it happens, not reconstructed afterward:
- a module's logic is implemented for the first time
- a schema/column-name assumption from DESIGN.md turns out wrong once real `dataset/*.csv` files are opened
- an edge case not already in DESIGN.md §10 is discovered
- a conflicting-evidence situation (DESIGN.md §10 row 2) is actually encountered
- an "OPEN QUESTION" flagged in DESIGN.md is resolved
- a result from `run_eval.py` causes a logic change
- a manual on-site review changes any earlier decision
- the step-mapping rules in DESIGN.md §8 (e.g. which remediation operation to use) need a case-specific override

---

## Phase 0 — Planning (decisions made before any code, during design discussion)

### [D-1] Pipeline split: LLM-only-for-extraction, deterministic-everything-else
- Phase: 0 (Architecture)
- Decision: LLM/VLM calls restricted to Stage 3 (request classification) and Stage 5 (unstructured evidence extraction) only. All ordering, enum selection, status decision, and JSON structure built by deterministic code.
- Why: grader scores sequence accuracy and schema/field accuracy strictly; LLM output is non-deterministic and would introduce ordering drift across runs, which is pure risk with no accuracy upside since ordering is a fixed rule, not a judgment call.
- Alternatives considered: single large LLM call per case that outputs full `steps_json` directly.
- What would have happened with the alternative: ordering and enum-exactness would depend on prompt-following reliability of the model every single case; a single off-spec operation string or wrong sort order per case silently fails that row's grading with no way to unit-test ordering independent of the LLM. Also makes `usage_report.md` costs much higher (full JSON generation vs short classification/extraction calls) with no accuracy benefit.
- Status: ACTIVE

### [D-2] Historical identifiers always checked, never skipped on "no current match"
- Phase: 0 (Design, identity resolution)
- Decision: Stage 2 always queries `user_audit_log.csv` regardless of whether the current `user_identities.csv` lookup succeeds.
- Why: the entire premise of the problem (per `problem_statement.md`) is that ghost data reappears via stale/historical identifiers that a sync job recreated. Skipping historical lookup would miss exactly the failure mode the challenge is built around.
- Alternatives considered: only check historical identifiers if current lookup fails (cheaper, fewer queries).
- What would have happened with the alternative: would miss cases where a user has a CURRENT valid identity but older evidence records under an OLD identifier are still floating around — that's a real "data remains" finding, not an edge case, likely common in the 518-row set given the framing. Would under-report FINDING steps and over-report COMPLETE status.
- Status: ACTIVE

### [D-3] evidence_id required for COMPLETE, empty for proposed INCOMPLETE remediation/verification
- Phase: 0 (Design, step generation)
- Decision: enforced per problem_statement.md rules section directly — not a discretionary choice, but logged here because it is a common place to introduce bugs.
- Why: spec is explicit: "Findings and verification steps for COMPLETE cases must cite a file_id, activity_id, or audit_id. Proposed remediation and future verification steps for INCOMPLETE cases use an empty evidence_id."
- Alternatives considered: none — this is a hard requirement, not a design choice.
- What would have happened with the alternative: direct schema violation, likely automatic point loss on every INCOMPLETE/COMPLETE case if gotten backwards.
- Status: ACTIVE

### [D-4] Phase-global step ordering, not per-resource interleaving
- Phase: 0 (Design, step generation)
- Decision: all FINDING steps across all resources emitted first, then all REMEDIATION, then all VERIFICATION — never finding→remediation→verification repeated per resource.
- Why: problem_statement.md states "Order steps by phase: findings, remediation, then verification" as a case-wide rule, and the allowed-operations table defines a single global priority order used across phases.
- Alternatives considered: group by resource first (all 3 phases for resource A, then all 3 for resource B) — reads more naturally as a remediation plan.
- What would have happened with the alternative: would violate the explicit phase-ordering rule and fail sequence accuracy on every multi-resource INCOMPLETE case — likely a large fraction of the 518.
- Status: ACTIVE

---

## Phase 1 — Ingestion & Schema Confirmation

### [D-5] Real dataset CSV schema confirmation
- Phase: 1 (Ingestion & Schema Confirmation)
- Date/step: Step 1.4 / 2026-10-25
- Decision: Confirmed real CSV schemas via `code/schema_dump.py`:
  - `deletion_requests.csv` (518 rows): `case_id`, `email`, `requested_at`, `reported_status`, `reported_at`, `audit_at`, `request_text` (matches spec exactly)
  - `deletion_rules.csv` (15 rows): `rule_id`, `data_category`, `condition`, `required_action`
  - `evidence_files.csv` (94 rows): `file_id`, `file_path`, `origin`, `captured_at`
  - `user_identities.csv` (850 rows): `user_id`, `name`, `email`, `phone`, `email_hash`, `updated_at`
  - `user_audit_log.csv` (306 rows): `audit_id`, `user_id`, `event_time`, `field_name`, `old_value`, `new_value`
  - `system_activity.csv` (4011 rows): `activity_id`, `event_time`, `event_type`, `source_system`, `target_system`, `resource_id`, `reported_result`, `details`
  - `sample_deletion_requests.csv` (32 rows) & `sample_output.csv` (32 rows): 22 INCOMPLETE, 10 COMPLETE.
- Why: Validated against actual filesystem to avoid column name guesswork and establish definitive schema bindings.
- Alternatives considered: Guessing column names or relying solely on text descriptions.
- What would have happened with the alternative: Silent KeyError or misattributed fields during joins and evidence matching.
- Status: ACTIVE

### [D-6] Hand-trace of sample cases (case_01, case_05) and ground-truth mechanics
- Phase: 1 (Ingestion & Schema Confirmation)
- Date/step: Step 1.5 / 2026-10-25
- Decision: Confirmed evidence citations and status mechanics:
  - In `case_01` (amina.elmasri@gmail.com, account_001), reported COMPLETE, audit_at 2026-09-03. Primary evidence `evidence_54` (failover SQL dump captured 2026-09-02) contains no `account_001` record -> True status is COMPLETE, yielding single step `VERIFY_RECORD_ABSENT` citing `evidence_54`.
  - In `case_05` (leila.haddad@yahoo.com, account_005), reported COMPLETE at 2026-08-28, audit_at 2026-09-08. Primary evidence `evidence_54` reveals un-deleted active record `INSERT INTO customer_profiles_failover_replica VALUES ('account_005', 'user_05', 'Leila Haddad', ...)` -> True status is INCOMPLETE. Yields 3 steps: `REPORT_REMAINING_RECORD` citing `evidence_54`, followed by `DELETE_RECORD` (empty evidence_id), followed by `VERIFY_RECORD_ABSENT` (empty evidence_id).
- Why: Empirically proves that failover SQL replicas hold ghost records missed by primary workflows, confirming the core architectural hypothesis and validating the empty evidence_id rule for proposed remediation.
- Alternatives considered: Trusting `reported_status`.
- What would have happened with the alternative: Complete misclassification on case_05 and other failover replica ghost records.
- Status: ACTIVE


---

## Phase 2 — Identity Resolution Implementation
*(append entries here as built)*

---

## Phase 3 — Request Classification Implementation
*(append entries here as built)*

---

## Phase 4 — Evidence Retrieval Implementation
*(append entries here as built)*

---

## Phase 5 — Evidence Extraction Implementation (VLM/parsers)
*(append entries here as built)*

---

## Phase 6 — State Reconstruction Implementation
*(append entries here as built)*

---

## Phase 7 — Policy Engine Implementation
*(append entries here as built — this is the section most likely to need real deletion_rules.csv content before finishing; flag any DESIGN.md §6 OPEN QUESTION resolution here specifically)*

---

## Phase 8 — Status Decision Implementation
*(append entries here as built)*

---

## Phase 9 — Step Generation Implementation
*(append entries here as built)*

---

## Phase 10 — Ordering & Renumbering Implementation
*(append entries here as built)*

---

## Phase 11 — Validation Implementation
*(append entries here as built)*

---

## Phase 12 — Sample-Set Evaluation & Debugging
*(every mismatch found against sample_output.csv gets its own entry here: what mismatched, root cause, fix applied)*

---

## Phase 13 — Full Run & Final Audit
*(final pre-submission checklist results, any last-minute logic changes, final token/cost numbers)*

---

## Open Questions Log
*(anything flagged "do not guess silently" in DESIGN.md goes here until resolved, then gets a resolution entry above and is marked RESOLVED here)*

- [ ] DESIGN.md §6: exact handling of a required-RETAIN record that is missing — no matching operation obviously fits "missing retained record" as a FINDING; needs confirmation against actual `deletion_rules.csv` wording once opened. STATUS: OPEN.
