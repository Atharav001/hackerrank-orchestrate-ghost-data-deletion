import os
import pandas as pd
from typing import Dict, Any, List, Set
from config import SYSTEM_ACTIVITY_PATH
from ingest import load_system_activity
from evidence_extraction import extract_all_evidence_records

_ACTIVITY_DF = None

def get_activity_df() -> pd.DataFrame:
    global _ACTIVITY_DF
    if _ACTIVITY_DF is None:
        _ACTIVITY_DF = load_system_activity()
    return _ACTIVITY_DF

def retrieve_evidence_for_case(case_row: Dict[str, Any], identity_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Stage 4 — Evidence Retrieval Layer:
    Retrieves evidence files and system activity rows matching ANY identifier
    of the subject where event_time / captured_at <= audit_at.
    """
    audit_at = str(case_row.get("audit_at", ""))
    requested_at = str(case_row.get("requested_at", ""))
    user_id = identity_info.get("user_id")
    all_values_lower = set(v.lower() for v in identity_info.get("all_values", []) if len(v) >= 3)
    if "email" in case_row and case_row["email"]:
        all_values_lower.add(case_row["email"].lower().strip())

    # 1. Retrieve matching evidence records
    all_ev_records = extract_all_evidence_records()
    matched_ev_records = []
    
    for r in all_ev_records:
        cap_at = r.get("captured_at", "")
        if cap_at <= audit_at:
            rec_id_lower = set(v.lower() for v in r.get("identifiers", []))
            if rec_id_lower.intersection(all_values_lower):
                matched_ev_records.append(r)

    # 2. Retrieve matching system activity records
    act_df = get_activity_df()
    # Filter activity at or before audit_at
    sub_act = act_df[act_df["event_time"] <= audit_at]
    
    matched_act_records = []
    # Fast match against details, resource_id, and timing
    for _, a_row in sub_act.iterrows():
        det_lower = str(a_row["details"]).lower()
        res_id = str(a_row["resource_id"])
        
        # Match if details mention user_id or any identifier
        matched = False
        if user_id and user_id.lower() in det_lower:
            matched = True
        elif any(val in det_lower for val in all_values_lower):
            matched = True
            
        if matched:
            matched_act_records.append(dict(a_row))

    return {
        "case_id": case_row.get("case_id"),
        "user_id": user_id,
        "audit_at": audit_at,
        "matched_evidence_records": matched_ev_records,
        "matched_activity_records": matched_act_records
    }

def test_evidence_retrieval():
    from ingest import load_sample_deletion_requests
    from identity_resolver import resolve_identity
    
    samples = load_sample_deletion_requests()
    # Test case_05
    c5 = samples[samples["case_id"] == "case_05"].iloc[0]
    id_info = resolve_identity(c5["email"])
    ret = retrieve_evidence_for_case(dict(c5), id_info)
    assert len(ret["matched_evidence_records"]) >= 1
    # account_005 in evidence_54
    assert any(r["resource_id"] == "account_005" for r in ret["matched_evidence_records"])
    print("Stage 4 evidence retrieval test passed successfully!")

if __name__ == "__main__":
    test_evidence_retrieval()
