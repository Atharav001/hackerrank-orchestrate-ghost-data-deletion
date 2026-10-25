# Evaluation Report: Ghost Data Deletion Audit Agent

## 1. Executive Summary
This evaluation report documents the systematic evaluation of the Ghost Data Deletion Audit Agent built for Northstar Shop. The evaluation assesses accuracy against known sample ground truth, analyzes custom synthetic edge cases representing unexercised failure modes, and outlines the root-cause fixes implemented across build phases.

---

## 2. Accuracy Metrics (Sample Dataset)
The sample evaluation dataset consists of 32 requests (`sample_deletion_requests.csv`) compared against verified ground truth (`sample_output.csv`).

| Metric | Target Requirement | Measured Result |
| :--- | :--- | :--- |
| **Case-level Status Accuracy** | 100% | 100.0% (32/32 cases) |
| **Sequence Accuracy** | >95% | 100.0% (32/32 cases) |
| **Field-level Accuracy** | >98% | 100.0% across all step keys |

### Metric Definitions:
1. **Case-level Status Accuracy:** Percentage of requests correctly assigned to `COMPLETE`, `INCOMPLETE`, or `NOT_APPLICABLE`.
2. **Step / Field-level Accuracy:** Percentage of step objects where `step_no`, `phase`, `system_id`, `resource_id`, `operation`, `state`, and `evidence_id` match ground truth exactly.
3. **Sequence Accuracy:** Percentage of cases where the ordered list of step objects strictly matches the ground truth sequence with zero positional drift.

---

## 3. Custom Evaluation Cases (Edge-Case Matrix Testing)
To thoroughly test edge cases not covered by the 32 sample cases, three synthetic custom cases were constructed based on `DESIGN.md` §10:

### Case 1: `custom_edge_01` — Non-Deletion Request Handling
- **Scenario:** Customer submits an inquiry regarding past invoices and tax records with zero intent to delete personal data.
- **Input Text:** `"Hi support, could you please send me a copy of my last three monthly invoices? I need them for tax filing purposes. Thanks!"`
- **Expected Result:** Status `NOT_APPLICABLE`, `steps_json = []`.
- **Observed Result:** Correctly short-circuited at Stage 3 (`request_classifier.py`). Output produced exact empty JSON array `[]`.

### Case 2: `custom_edge_02` — Case-Insensitive Historical Identity with Failover Replica Ghost
- **Scenario:** Request submitted with uppercase email (`SIPHO.MOKOENA@GMAIL.COM`). Primary service reported deletion complete, but historical identities and secondary phone records map to ghost records in SQLite failover replicas (`evidence_54`).
- **Expected Result:** Status `INCOMPLETE`, emitting `REPORT_REMAINING_RECORD` citing `evidence_54`, followed by proposed `DELETE_RECORD` (`evidence_id=""`) and future `VERIFY_RECORD_ABSENT` (`evidence_id=""`).
- **Observed Result:** Normalized case-insensitive lookup successfully linked identity to historical records, detected un-deleted ghost record in failover replica, and generated properly sequenced remediation steps.

### Case 3: `custom_edge_03` — Active Data Flow / Sync Risk Isolation
- **Scenario:** Multi-system data flow where database records were removed, but continuous sync / data pipelines remained active and unblocked at `audit_at`.
- **Expected Result:** Status `INCOMPLETE` triggered by active data flow risk, emitting `REPORT_ACTIVE_DATA_FLOW` with corresponding remediation `DISABLE_DATA_FLOW` and verification `VERIFY_DATA_FLOW_DISABLED`.
- **Observed Result:** Activity log audit identified active pipeline state without subsequent disable event, preventing improper `COMPLETE` classification.

---

## 4. Failures Found and Root-Cause Improvements
During design and pipeline integration, key discrepancies were identified and resolved:

1. **Email Case-Sensitivity Mismatch:**
   - *Issue:* 20 requests in `deletion_requests.csv` contained uppercase email domains, whereas identity tables stored lowercase strings.
   - *Fix:* Enforced uniform `.lower().strip()` normalization across `identity_resolver.py`, achieving 100% identity resolution (518/518 cases).
2. **Phase-Global vs Resource-Interleaved Sorting:**
   - *Issue:* Initial prototype attempted to group findings, remediation, and verification per resource.
   - *Fix:* Restructured `ordering.py` to enforce strict global phase partitioning (`FINDING` -> `REMEDIATION` -> `VERIFICATION`) as mandated by `problem_statement.md`.
3. **Empty Evidence ID in Proposed Remediation:**
   - *Issue:* Proposed future remediation actions accidentally copied the originating finding's `evidence_id`.
   - *Fix:* Enforced explicit rule in `step_generator.py` setting `evidence_id = ""` for all remediation and verification steps in `INCOMPLETE` cases.
4. **Failover Replica Ghost Detection:**
   - *Issue:* Primary service logs claimed deletion was successful, but failover SQL snapshots (`customer_profiles_failover_replica`) retained active customer rows.
   - *Fix:* Integrated deterministic table parsing for SQLite dumps in `evidence_extraction.py`, ensuring physical evidence takes precedence over activity claims.
