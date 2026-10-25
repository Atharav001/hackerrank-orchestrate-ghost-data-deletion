# Evaluation Report: Ghost Data Deletion Audit Agent

## 1. Executive Summary
This report is based on a **live re-run** of `code/evaluation/run_eval.py` on 2026-10-25 against `dataset/sample_deletion_requests.csv` and `dataset/sample_output.csv`. Earlier draft text that claimed 100% sample accuracy is withdrawn. The pipeline modules exist and run, but sample step matching is not submission-ready yet.

---

## 2. Accuracy Metrics (Sample Dataset)
The sample evaluation dataset consists of 32 requests.

| Metric | Target Requirement | Measured Result (live run) |
| :--- | :--- | :--- |
| **Case-level Status Accuracy** | 100% | **78.12% (25/32 cases)** |
| **Sequence Accuracy** | >95% | **12.50% (4/32 cases)** |
| **Field-level Accuracy** | >98% | **18.58%** |

### Metric Definitions:
1. **Case-level Status Accuracy:** Percentage of requests correctly assigned to `COMPLETE`, `INCOMPLETE`, or `NOT_APPLICABLE`.
2. **Step / Field-level Accuracy:** Percentage of step objects where `step_no`, `phase`, `system_id`, `resource_id`, `operation`, `state`, and `evidence_id` match ground truth exactly.
3. **Sequence Accuracy:** Percentage of cases where the ordered list of step objects strictly matches the ground truth sequence with zero positional drift.

### Status mismatches (7 cases)
| Case | True status | Predicted status |
| :--- | :--- | :--- |
| case_03 | COMPLETE | INCOMPLETE |
| case_10 | INCOMPLETE | COMPLETE |
| case_12 | INCOMPLETE | COMPLETE |
| case_15 | INCOMPLETE | COMPLETE |
| case_16 | INCOMPLETE | COMPLETE |
| case_20 | INCOMPLETE | COMPLETE |
| case_22 | INCOMPLETE | COMPLETE |

Most remaining sample cases have the **correct status but wrong or incomplete steps**. Common patterns:

- COMPLETE cases emit **zero verification steps** when the proof is “record absent from a SQL replica” (for example case_01 / case_02 citing `evidence_54`).
- INCOMPLETE cases often **omit** `VERIFY_RECORD_ABSENT` for the primary `account_service` row even when other findings are correct.
- Extra `VERIFY_RECORD_PRESENT` steps appear for `legal_service` / `doc_evidence_27` that sample output does not include.
- Several findings that sample output expects (search remaining, support PII, active data flows) are missing when evidence is image-based or not extracted.

---

## 3. Custom Evaluation Cases
Three synthetic cases exist in `code/evaluation/custom_cases.py`. Live run of case 1 **fails**.

### Case 1: `custom_edge_01` — Non-Deletion Request Handling
- **Input Text:** `"Hi support, could you please send me a copy of my last three monthly invoices? I need them for tax filing purposes. Thanks!"`
- **Expected Result:** `NOT_APPLICABLE`, `steps_json = []`
- **Observed Result:** `COMPLETE` (classifier keyword list did not match this wording). **FAIL**

### Case 2: `custom_edge_02` — Case-Insensitive Historical Identity
- **Scenario:** Uppercase/historical email with possible failover replica leftovers.
- **Status:** Not fully trusted until sample sequence accuracy is fixed. Classifier currently treats most deletion-like text as `FULL_DELETION_REQUEST`.

### Case 3: `custom_edge_03` — Active Data Flow
- **Scenario:** Sync/restore risk without relying only on a remaining profile row.
- **Status:** Same — harness exists; do not treat as passing until re-run after logic fixes.

---

## 4. Failures Found and Remaining Fixes
These are the issues that must be fixed before packing `code.zip` and writing the 518-row `output.csv`:

1. **Absence proof for COMPLETE cases.** If a user’s account is gone from a snapshot, still emit `VERIFY_RECORD_ABSENT` citing that snapshot (`file_id`).
2. **INCOMPLETE verification of the primary account.** Sample output still wants `VERIFY_RECORD_ABSENT` on `account_service` even when the finding is on another system.
3. **Image evidence.** 11 of 94 files are `.png` and are currently skipped by `evidence_extraction.py`.
4. **Request classification.** Keyword list is too narrow; LLM branch is unused. Non-deletion requests that are phrased differently become false audits.
5. **Legal-hold / retained records.** Do not emit extra `VERIFY_RECORD_PRESENT` rows that sample output does not include.
6. **Honest usage accounting.** No billed LLM/VLM calls occurred in this run.

Until sample sequence accuracy is high, do not treat the 518-row hidden set as ready.
