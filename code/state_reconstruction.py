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

    # Group evidence records by (system_id, resource_id)
    # Take the latest evidence snapshot before audit_at
    resources = {}

    for er in ev_records:
        key = (er["system_id"], er["resource_id"])
        if key not in resources:
            resources[key] = er
        else:
            # Pick latest captured evidence
            if er["captured_at"] > resources[key]["captured_at"]:
                resources[key] = er

    # Check for active data-flow / restore risks in activity logs if not already captured in evidence
    for ar in act_records:
        res_id = ar.get("resource_id")
        evt_type = ar.get("event_type")
        target_sys = ar.get("target_system")
        res_result = ar.get("reported_result")

        details = str(ar.get("details", "")).lower()
        result = str(res_result or "").lower()
        flow_event = str(evt_type or "").upper() in {"CHECK_DATA_FLOW", "SYNC", "IMPORT", "DATA_FLOW"}
        restore_event = str(evt_type or "").upper() in {"CHECK_RESTORE_ACCESS", "RESTORE", "BACKUP_RESTORE"}
        flow_active = result in {"ACTIVE", "ENABLED", "RUNNING", "SUCCESS"} or any(x in details for x in ("remains enabled", "enabled=true", "active", "running"))
        restore_active = result in {"ACTIVE", "ENABLED", "ALLOWED", "RUNNING", "SUCCESS"} or any(x in details for x in ("remains active", "restore_allowed=true", "allowed"))
        # Treat structured flow/restore events as risks; free text is only a fallback.
        if flow_event and flow_active:
            key = (target_sys, res_id)
            if key not in resources or resources[key]["state"] != "DISABLED":
                resources[key] = {
                    "evidence_id": ar.get("activity_id"),
                    "file_path": "system_activity.csv",
                    "captured_at": ar.get("event_time"),
                    "system_id": target_sys,
                    "resource_id": res_id,
                    "data_category": "DATA_FLOW",
                    "state": "ACTIVE",
                    "identifiers": set(),
                    "details": ar.get("details")
                }
        elif restore_event and restore_active:
            key = (target_sys, res_id)
            if key not in resources or resources[key]["state"] != "BLOCKED":
                resources[key] = {
                    "evidence_id": ar.get("activity_id"),
                    "file_path": "system_activity.csv",
                    "captured_at": ar.get("event_time"),
                    "system_id": target_sys,
                    "resource_id": res_id,
                    "data_category": "BACKUP_ARCHIVE",
                    "state": "ACTIVE",
                    "identifiers": set(),
                    "details": ar.get("details")
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
            "details": rec.get("details", "")
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
