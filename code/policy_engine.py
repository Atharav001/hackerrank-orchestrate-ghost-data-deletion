import os
import pandas as pd
from typing import Dict, Any, List
from ingest import load_deletion_rules

_RULES_CACHE = None
_CONDITIONS_CACHE = None

def get_rules_map() -> Dict[str, str]:
    global _RULES_CACHE, _CONDITIONS_CACHE
    if _RULES_CACHE is None:
        df = load_deletion_rules()
        _RULES_CACHE = {row["data_category"]: row["required_action"] for _, row in df.iterrows()}
        _CONDITIONS_CACHE = {row["data_category"]: str(row["condition"]) for _, row in df.iterrows()}
    return _RULES_CACHE

def evaluate_resource_policy(resource: Dict[str, Any]) -> Dict[str, Any]:
    """
    Stage 7 — Policy Engine:
    Evaluates resource state against deletion_rules.csv.
    Categorizes resource as OK, CORRECTLY_RETAINED, or PROBLEM (with finding operation).
    """
    rules_map = get_rules_map()
    data_cat = resource.get("data_category", "USER_PROFILE")
    state = resource.get("state", "PRESENT")
    sys_id = resource.get("system_id", "")
    res_id = resource.get("resource_id", "")
    req_action = rules_map.get(data_cat, "DELETE")

    classification = "OK"
    finding_op = None
    finding_state = None
    remediation_op = None
    remediation_state = None
    verification_op = None
    verification_state = None

    # Flow and restore are still governed by the CSV action; their state adds a risk.
    if data_cat == "DATA_FLOW":
        if state == "ACTIVE":
            classification = "PROBLEM"
            finding_op = "REPORT_ACTIVE_DATA_FLOW"
            finding_state = "ACTIVE"
            remediation_op = "DISABLE_DATA_FLOW"
            remediation_state = "DISABLED"
            verification_op = "VERIFY_DATA_FLOW_DISABLED"
            verification_state = "DISABLED"
        else:
            classification = "OK"
            verification_op = "VERIFY_DATA_FLOW_DISABLED"
            verification_state = "DISABLED"

    # Handle BACKUP_ARCHIVE restore risk
    elif data_cat == "BACKUP_ARCHIVE":
        if state == "ACTIVE":
            classification = "PROBLEM"
            finding_op = "REPORT_RESTORE_RISK"
            finding_state = "ACTIVE"
            remediation_op = "BLOCK_RESTORE"
            remediation_state = "BLOCKED"
            verification_op = "VERIFY_RESTORE_BLOCKED"
            verification_state = "BLOCKED"
        else:
            classification = "CORRECTLY_RETAINED"
            verification_op = "VERIFY_RESTORE_BLOCKED"
            verification_state = "BLOCKED"

    # Handle SECURITY_AUDIT_LOG / LEGAL_HOLD_RECORD
    elif req_action == "RETAIN":
        classification = "CORRECTLY_RETAINED"
        verification_op = "VERIFY_RECORD_PRESENT"
        verification_state = "PRESENT"

    # Handle DELETE requirement (USER_PROFILE, SEARCH_INDEX_ENTRY, USER_EXPORT, etc.)
    elif req_action == "DELETE":
        if state == "PRESENT":
            classification = "PROBLEM"
            finding_op = "REPORT_REMAINING_RECORD"
            finding_state = "PRESENT"
            remediation_op = "DELETE_RECORD"
            remediation_state = "ABSENT"
            verification_op = "VERIFY_RECORD_ABSENT"
            verification_state = "ABSENT"
        else:
            classification = "OK"
            verification_op = "VERIFY_RECORD_ABSENT"
            verification_state = "ABSENT"

    # Handle REDACT requirement (SUPPORT_MESSAGE, ACCOUNT_TOMBSTONE, EMAIL_DELIVERY_LOG)
    elif req_action == "REDACT":
        if state == "PRESENT":
            classification = "PROBLEM"
            finding_op = "REPORT_EXPOSED_PII"
            finding_state = "PRESENT"
            remediation_op = "REDACT_RECORD"
            remediation_state = "REDACTED"
            verification_op = "VERIFY_RECORD_REDACTED"
            verification_state = "REDACTED"
        else:
            classification = "OK"
            verification_op = "VERIFY_RECORD_REDACTED"
            verification_state = "REDACTED"

    # Handle ANONYMIZE requirement (ANALYTICS_PROFILE, PRODUCT_TELEMETRY)
    elif req_action == "ANONYMIZE":
        if state == "PRESENT":
            classification = "PROBLEM"
            finding_op = "REPORT_EXPOSED_PII"
            finding_state = "PRESENT"
            remediation_op = "ANONYMIZE_RECORD"
            remediation_state = "ANONYMIZED"
            verification_op = "VERIFY_RECORD_ANONYMIZED"
            verification_state = "ANONYMIZED"
        else:
            classification = "OK"
            verification_op = "VERIFY_RECORD_ANONYMIZED"
            verification_state = "ANONYMIZED"

    return {
        "system_id": sys_id,
        "resource_id": res_id,
        "data_category": data_cat,
        "current_state": state,
        "classification": classification,
        "finding_op": finding_op,
        "finding_state": finding_state,
        "remediation_op": remediation_op,
        "remediation_state": remediation_state,
        "verification_op": verification_op,
        "verification_state": verification_state,
        "evidence_id": resource.get("evidence_id", "")
    }

def evaluate_case_policy(reconstructed_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    results = []
    for res in reconstructed_data.get("resources", []):
        results.append(evaluate_resource_policy(res))
    return results

def test_policy_engine():
    res_problem = {
        "system_id": "account_service",
        "resource_id": "account_005",
        "data_category": "USER_PROFILE",
        "state": "PRESENT",
        "evidence_id": "evidence_54"
    }
    eval_res = evaluate_resource_policy(res_problem)
    assert eval_res["classification"] == "PROBLEM"
    assert eval_res["finding_op"] == "REPORT_REMAINING_RECORD"
    assert eval_res["remediation_op"] == "DELETE_RECORD"
    assert eval_res["verification_op"] == "VERIFY_RECORD_ABSENT"

    res_anonymized = {
        "system_id": "analytics_platform",
        "resource_id": "analytics_1895",
        "data_category": "ANALYTICS_PROFILE",
        "state": "ANONYMIZED",
        "evidence_id": "evidence_92"
    }
    eval_anon = evaluate_resource_policy(res_anonymized)
    assert eval_anon["classification"] == "OK"
    assert eval_anon["verification_op"] == "VERIFY_RECORD_ANONYMIZED"

    print("Policy engine tests passed successfully!")

if __name__ == "__main__":
    test_policy_engine()
