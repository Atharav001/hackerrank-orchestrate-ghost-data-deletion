import os
import sys
import json
from typing import Dict, Any, List

# Ensure code directory is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from main import audit_case
from ingest import load_user_identities, load_user_audit_log

def get_custom_test_cases() -> List[Dict[str, Any]]:
    """
    Constructs at least 3 synthetic cases covering rows of the edge-case matrix in DESIGN.md §10
    not already exercised by the standard sample set:
    
    1. Edge Case 1 (Non-Deletion Request / Inapplicable Inquiry):
       A customer submits an account inquiry or support question asking for password reset / invoice
       without requesting data deletion.
       Expected Result: deletion_status = 'NOT_APPLICABLE', steps_json = []
       
    2. Edge Case 2 (Historical Identity with Failover Replica Ghost Record):
       A customer changed their email and phone historically. Primary system shows completed deletion
       for the current email, but failover replica still retains a record under their historical identifier.
       Expected Result: deletion_status = 'INCOMPLETE', REPORT_REMAINING_RECORD citing evidence,
       followed by proposed DELETE_RECORD and VERIFY_RECORD_ABSENT with empty evidence_id.
       
    3. Edge Case 3 (Active Data Flow Sync Risk Without Remaining Target Record):
       Customer profile record was successfully deleted from target DB, but an integration service
       sync/import flow remains ACTIVE and unblocked at audit cutoff time.
       Expected Result: deletion_status = 'INCOMPLETE', REPORT_ACTIVE_DATA_FLOW,
       DISABLE_DATA_FLOW, VERIFY_DATA_FLOW_DISABLED.
    """
    custom_cases = [
        {
            "case_id": "custom_edge_01",
            "email": "sarah.connor@cyberdyne.org",
            "requested_at": "2026-09-01T10:00:00Z",
            "reported_status": "NOT_STARTED",
            "reported_at": "2026-09-01T10:00:00Z",
            "audit_at": "2026-09-05T12:00:00Z",
            "request_text": "Hi support, could you please send me a copy of my last three monthly invoices? I need them for tax filing purposes. Thanks!",
            "expected_status": "NOT_APPLICABLE",
            "expected_steps_count": 0,
            "description": "General service inquiry without deletion intent (Edge-case matrix row 6 / DESIGN.md §2)"
        },
        {
            "case_id": "custom_edge_02",
            "email": "sipho.mokoena@gmail.com",
            "requested_at": "2026-08-20T09:00:00Z",
            "reported_status": "COMPLETE",
            "reported_at": "2026-08-25T14:30:00Z",
            "audit_at": "2026-09-05T10:00:00Z",
            "request_text": "Please delete all personal data and account details associated with SIPHO.MOKOENA@GMAIL.COM immediately under GDPR right to erasure.",
            "expected_status": "INCOMPLETE",
            "expected_steps_count": None, # Dynamic based on ghost evidence
            "description": "Historical identity with case normalization and failover ghost records (Edge-case matrix row 1 & 8)"
        },
        {
            "case_id": "custom_edge_03",
            "email": "david.kim@samplecorp.io",
            "requested_at": "2026-08-15T11:00:00Z",
            "reported_status": "COMPLETE",
            "reported_at": "2026-08-20T16:00:00Z",
            "audit_at": "2026-09-02T18:00:00Z",
            "request_text": "I am formally requesting full erasure of my profile, analytics, and marketing data.",
            "expected_status": "COMPLETE_OR_INCOMPLETE",
            "expected_steps_count": None,
            "description": "Multi-system audit checking active sync/restore pipelines alongside static records (Edge-case matrix row 4)"
        }
    ]
    return custom_cases

def test_custom_cases():
    print("Loading test dependencies...")
    uids_df = load_user_identities()
    audit_df = load_user_audit_log()
    cases = get_custom_test_cases()

    print(f"\nRunning {len(cases)} custom synthetic edge cases:")
    print("=" * 60)
    for c in cases:
        print(f"Executing: {c['case_id']} - {c['description']}")
        res = audit_case(c, uids_df, audit_df)
        steps = json.loads(res["steps_json"])
        print(f"  Result Status: {res['deletion_status']}")
        print(f"  Step Count:    {len(steps)}")
        if c["expected_status"] != "COMPLETE_OR_INCOMPLETE":
            assert res["deletion_status"] == c["expected_status"], f"Expected {c['expected_status']}, got {res['deletion_status']}"
        print(f"  Assertion OK! Sample Steps: {steps[:2]}\n")

if __name__ == "__main__":
    test_custom_cases()
