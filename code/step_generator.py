from typing import List, Dict, Any
from ordering import order_and_renumber_steps

def generate_steps_for_case(
    deletion_status: str,
    evaluated_resources: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Stage 9 — Step Generation Layer:
    Generates unordered step dictionaries for findings, remediation, and verification,
    then applies Stage 10 deterministic ordering and renumbering.
    """
    if deletion_status == "NOT_APPLICABLE":
        return []

    raw_steps = []

    if deletion_status == "COMPLETE":
        # Only verification steps with non-empty evidence_id
        for res in evaluated_resources:
            v_op = res.get("verification_op")
            v_st = res.get("verification_state")
            ev_id = res.get("evidence_id") or ""
            if v_op and v_st:
                raw_steps.append({
                    "phase": "VERIFICATION",
                    "system_id": res["system_id"],
                    "resource_id": res["resource_id"],
                    "operation": v_op,
                    "state": v_st,
                    "evidence_id": ev_id
                })

    elif deletion_status == "INCOMPLETE":
        # 1. Findings for PROBLEM resources (evidence_id non-empty)
        for res in evaluated_resources:
            if res.get("classification") == "PROBLEM":
                f_op = res.get("finding_op")
                f_st = res.get("finding_state")
                ev_id = res.get("evidence_id") or ""
                if f_op and f_st:
                    raw_steps.append({
                        "phase": "FINDING",
                        "system_id": res["system_id"],
                        "resource_id": res["resource_id"],
                        "operation": f_op,
                        "state": f_st,
                        "evidence_id": ev_id
                    })

        # 2. Remediation for PROBLEM resources (evidence_id empty)
        for res in evaluated_resources:
            if res.get("classification") == "PROBLEM":
                r_op = res.get("remediation_op")
                r_st = res.get("remediation_state")
                if r_op and r_st:
                    raw_steps.append({
                        "phase": "REMEDIATION",
                        "system_id": res["system_id"],
                        "resource_id": res["resource_id"],
                        "operation": r_op,
                        "state": r_st,
                        "evidence_id": ""
                    })

        # 3. Verification for ALL resources (evidence_id empty)
        for res in evaluated_resources:
            v_op = res.get("verification_op")
            v_st = res.get("verification_state")
            if v_op and v_st:
                raw_steps.append({
                    "phase": "VERIFICATION",
                    "system_id": res["system_id"],
                    "resource_id": res["resource_id"],
                    "operation": v_op,
                    "state": v_st,
                    "evidence_id": ""
                })

    # Stage 10 ordering and renumbering
    return order_and_renumber_steps(raw_steps)

def test_step_generator():
    res_problem = {
        "system_id": "account_service",
        "resource_id": "account_005",
        "data_category": "USER_PROFILE",
        "current_state": "PRESENT",
        "classification": "PROBLEM",
        "finding_op": "REPORT_REMAINING_RECORD",
        "finding_state": "PRESENT",
        "remediation_op": "DELETE_RECORD",
        "remediation_state": "ABSENT",
        "verification_op": "VERIFY_RECORD_ABSENT",
        "verification_state": "ABSENT",
        "evidence_id": "evidence_54"
    }
    steps = generate_steps_for_case("INCOMPLETE", [res_problem])
    assert len(steps) == 3
    assert steps[0]["phase"] == "FINDING" and steps[0]["evidence_id"] == "evidence_54"
    assert steps[1]["phase"] == "REMEDIATION" and steps[1]["evidence_id"] == ""
    assert steps[2]["phase"] == "VERIFICATION" and steps[2]["evidence_id"] == ""
    print("Step generator tests passed successfully!")

if __name__ == "__main__":
    test_step_generator()
