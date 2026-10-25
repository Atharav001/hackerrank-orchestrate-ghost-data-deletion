import os
import re
import pandas as pd
from typing import Dict, Any, List, Set
from config import SYSTEM_ACTIVITY_PATH
from ingest import load_system_activity
from evidence_extraction import extract_all_evidence_records

_ACTIVITY_DF = None

def _contains_identifier(text: str, identifier: str) -> bool:
    """Match an identifier as a token, avoiding user_1/user_10 collisions."""
    value = str(identifier).strip().lower()
    if not value:
        return False
    return re.search(r"(?<![A-Za-z0-9@._+-])" + re.escape(value) + r"(?![A-Za-z0-9@._+-])", str(text).lower()) is not None

def get_activity_df() -> pd.DataFrame:
    global _ACTIVITY_DF
    if _ACTIVITY_DF is None:
        _ACTIVITY_DF = load_system_activity()
    return _ACTIVITY_DF

def retrieve_evidence_for_case(case_row: Dict[str, Any], identity_info: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve identity-linked records and expand only through grounded resource IDs."""
    audit_at = str(case_row.get("audit_at", ""))
    user_id = identity_info.get("user_id")
    typed_ids = identity_info.get("identifiers_as_of_audit", identity_info.get("all_identifiers", {}))
    legal_ids = (typed_ids.get("user_ids", []) + typed_ids.get("emails", []) +
                 typed_ids.get("phones", []) + typed_ids.get("email_hashes", []))
    targets = {str(v).lower().strip() for v in legal_ids if len(str(v).strip()) >= 3}
    if case_row.get("email"):
        targets.add(str(case_row["email"]).lower().strip())

    all_records = extract_all_evidence_records()
    eligible = []
    direct_evidence = []
    for rec in all_records:
        cap_at = str(rec.get("captured_at", ""))
        observed_at = str(rec.get("observed_at") or cap_at)
        if cap_at <= audit_at and observed_at <= audit_at:
            eligible.append(rec)
            if any(_contains_identifier(candidate, target)
                   for candidate in rec.get("identifiers", []) for target in targets):
                direct_evidence.append(rec)

    # First match activity via legal identifiers. Then use resource IDs explicitly
    # tied to the subject by those activity rows to join artifacts that show no PII
    # (e.g. an object-storage screenshot referenced by an identity-link event).
    act_df = get_activity_df()
    activity_candidates = act_df[act_df["event_time"].astype(str) <= audit_at]
    direct_activity = []
    for _, row in activity_candidates.iterrows():
        details = str(row.get("details", ""))
        if any(_contains_identifier(details, target) for target in targets):
            direct_activity.append(dict(row))
    linked_resource_ids = {str(r.get("resource_id", "")).lower() for r in direct_evidence}
    linked_resource_ids.update(str(r.get("resource_id", "")).lower() for r in direct_activity)
    matched_activity = list(direct_activity)
    seen_activity = {str(r.get("activity_id", "")) for r in matched_activity}
    for _, row in activity_candidates.iterrows():
        rec = dict(row)
        aid = str(rec.get("activity_id", ""))
        if aid not in seen_activity and str(rec.get("resource_id", "")).lower() in linked_resource_ids:
            matched_activity.append(rec)
            seen_activity.add(aid)

    linked_resource_ids.update(str(r.get("resource_id", "")).lower() for r in matched_activity)
    matched_evidence = list(direct_evidence)
    seen_evidence = {(str(r.get("evidence_id")), str(r.get("system_id")), str(r.get("resource_id"))) for r in matched_evidence}
    for rec in eligible:
        key = (str(rec.get("evidence_id")), str(rec.get("system_id")), str(rec.get("resource_id")))
        if key not in seen_evidence and str(rec.get("resource_id", "")).lower() in linked_resource_ids:
            matched_evidence.append(rec)
            seen_evidence.add(key)

    return {
        "case_id": case_row.get("case_id"),
        "user_id": user_id,
        "audit_at": audit_at,
        "matched_evidence_records": matched_evidence,
        "matched_activity_records": matched_activity,
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
