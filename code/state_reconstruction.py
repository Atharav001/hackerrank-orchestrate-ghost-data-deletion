import os
from typing import Dict, Any, List, Set

def reconstruct_state_for_case(
    case_row: Dict[str, Any],
    identity_info: Dict[str, Any],
    retrieved_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Stage 6 — State Reconstruction Layer:
    For each (system_id, resource_id), builds the state at audit_at by fusing
    evidence artifacts and operational activity.
    Evidence proof strictly takes precedence over claims in activity logs.
    """
    audit_at = case_row.get("audit_at", "")
    ev_records = retrieved_data.get("matched_evidence_records", [])
    act_records = retrieved_data.get("matched_activity_records", [])

    # Group evidence by service and resource, choosing the newest record-level
    # observation (not just the enclosing file capture time).
    resources = {}
    state_rank = {"PRESENT": 6, "ACTIVE": 5, "ABSENT": 4, "REDACTED": 3, "ANONYMIZED": 2, "BLOCKED": 1, "DISABLED": 0}

    for er in ev_records:
        observed_at = str(er.get("observed_at") or er.get("captured_at") or "")
        if observed_at and observed_at > str(audit_at):
            continue
        key = (er["system_id"], er["resource_id"])
        if key not in resources:
            resources[key] = {**er, "_state_time": observed_at}
        else:
            previous = resources[key]
            old_time = str(previous.get("_state_time") or previous.get("captured_at") or "")
            # Several parsers can emit multiple rows for one artifact/resource,
            # including a search hit and an empty-query result. Prefer actual
            # positive record observations when timestamps tie.
            if (observed_at, state_rank.get(er.get("state"), -1), str(er.get("evidence_id", ""))) > (
                old_time, state_rank.get(previous.get("state"), -1), str(previous.get("evidence_id", ""))
            ):
                resources[key] = {**er, "_state_time": observed_at}

    # Check for active data-flow / restore risks in activity logs if not already captured in evidence
    activity_latest = {}
    for ar in sorted(act_records, key=lambda x: str(x.get("event_time", ""))):
        res_id = ar.get("resource_id")
        evt_type = str(ar.get("event_type") or "").upper()
        target_sys = ar.get("target_system")
        details = str(ar.get("details", "")).lower()
        category = "DATA_FLOW" if evt_type == "CHECK_DATA_FLOW" else "BACKUP_ARCHIVE" if evt_type == "CHECK_RESTORE_ACCESS" else None
        proves_risk = (category == "DATA_FLOW" and any(x in details for x in ("remains enabled", "enabled=true"))) or (
            category == "BACKUP_ARCHIVE" and any(x in details for x in ("can still be restored", "restore_allowed=true"))
        )
        if category and proves_risk:
            key = (target_sys, res_id)
            previous = activity_latest.get(key)
            if previous is None or str(ar.get("event_time", "")) > str(previous.get("event_time", "")):
                activity_latest[key] = ar

    # Activity checks establish a risk only when they postdate the last state
    # evidence. Report the proving activity row as the finding citation.
    for key, ar in activity_latest.items():
        rec = resources.get(key)
        activity_time = str(ar.get("event_time", ""))
        evidence_time = str((rec or {}).get("_state_time", ""))
        if not rec or activity_time >= evidence_time:
            evt_type = str(ar.get("event_type", ""))
            category = "DATA_FLOW" if evt_type == "CHECK_DATA_FLOW" else "BACKUP_ARCHIVE"
            resources[key] = {
                "evidence_id": ar.get("activity_id"), "file_path": "system_activity.csv",
                "captured_at": activity_time, "observed_at": activity_time,
                "system_id": key[0], "resource_id": key[1], "data_category": category,
                "state": "ACTIVE", "identifiers": set(), "details": ar.get("details", ""),
                "_state_time": activity_time,
            }

    # Format resource states
    reconstructed_resources = []
    for (sys_id, res_id), rec in resources.items():
        reconstructed_resources.append({
            "system_id": sys_id,
            "resource_id": res_id,
            "data_category": rec.get("data_category", "USER_PROFILE"),
            "state": rec.get("state", "PRESENT"),
            "evidence_id": rec.get("evidence_id", ""),
            "captured_at": rec.get("captured_at", ""),
            "details": rec.get("details", ""),
            "policy_facts": rec.get("policy_facts", {}),
            "direct_identifiers": bool(rec.get("identifiers")),
            "audit_at": audit_at
        })

    return {
        "case_id": case_row.get("case_id"),
        "resources": reconstructed_resources
    }

def test_state_reconstruction():
    case_row = {"case_id": "test_1", "audit_at": "2026-09-15T12:00:00Z"}
    retrieved = {
        "matched_evidence_records": [
            {
                "system_id": "account_service",
                "resource_id": "account_005",
                "data_category": "USER_PROFILE",
                "state": "PRESENT",
                "evidence_id": "evidence_54",
                "captured_at": "2026-09-02T23:00:00Z"
            }
        ],
        "matched_activity_records": []
    }
    rec = reconstruct_state_for_case(case_row, {}, retrieved)
    assert len(rec["resources"]) == 1
    assert rec["resources"][0]["resource_id"] == "account_005"
    assert rec["resources"][0]["state"] == "PRESENT"
    print("State reconstruction test passed successfully!")

if __name__ == "__main__":
    test_state_reconstruction()
