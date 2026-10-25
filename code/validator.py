import os
import json
import pandas as pd
from typing import List, Tuple, Dict, Any
from config import (
    ALLOWED_STATUSES,
    ALLOWED_PHASES,
    ALLOWED_OPERATIONS,
    ALLOWED_STATES,
    OPERATION_TO_PRIORITY_INDEX,
    PHASE_ORDER_INDEX
)

def validate_step(step: Dict[str, Any], expected_step_no: int, deletion_status: str, case_id: str) -> List[str]:
    errors = []
    
    # Required keys
    required_keys = {"step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"}
    if not required_keys.issubset(step.keys()):
        missing = required_keys - set(step.keys())
        errors.append(f"{case_id} step {step.get('step_no')}: Missing keys: {missing}")
        return errors

    # Check step_no
    if step["step_no"] != expected_step_no:
        errors.append(f"{case_id}: step_no is {step['step_no']}, expected {expected_step_no}")

    # Check phase enum
    phase = step["phase"]
    if phase not in ALLOWED_PHASES:
        errors.append(f"{case_id} step {expected_step_no}: Invalid phase '{phase}'")

    # Check operation enum
    op = step["operation"]
    if op not in ALLOWED_OPERATIONS:
        errors.append(f"{case_id} step {expected_step_no}: Invalid operation '{op}'")

    # Check state enum
    st = step["state"]
    if st not in ALLOWED_STATES:
        errors.append(f"{case_id} step {expected_step_no}: Invalid state '{st}'")

    # Check non-empty system_id and resource_id
    if not str(step["system_id"]).strip():
        errors.append(f"{case_id} step {expected_step_no}: Empty system_id")
    if not str(step["resource_id"]).strip():
        errors.append(f"{case_id} step {expected_step_no}: Empty resource_id")

    # Check evidence_id rules per status and phase
    ev_id = step["evidence_id"]
    if deletion_status == "COMPLETE":
        if not str(ev_id).strip():
            errors.append(f"{case_id} COMPLETE step {expected_step_no}: evidence_id must not be empty")
    elif deletion_status == "INCOMPLETE":
        if phase == "FINDING":
            if not str(ev_id).strip():
                errors.append(f"{case_id} INCOMPLETE FINDING step {expected_step_no}: evidence_id must not be empty")
        elif phase in ("REMEDIATION", "VERIFICATION"):
            if ev_id != "":
                errors.append(f"{case_id} INCOMPLETE {phase} step {expected_step_no}: evidence_id must be empty string, got '{ev_id}'")

    return errors

def validate_dataframe(df: pd.DataFrame, expected_row_count: int = None) -> List[str]:
    errors = []
    
    # Check columns
    required_cols = ["case_id", "deletion_status", "steps_json"]
    if list(df.columns) != required_cols:
        errors.append(f"Header columns mismatch: got {list(df.columns)}, expected {required_cols}")
        return errors

    # Check row count if specified
    if expected_row_count is not None and len(df) != expected_row_count:
        errors.append(f"Row count mismatch: expected {expected_row_count}, got {len(df)}")

    # Check sorted case_ids and uniqueness
    case_ids = list(df["case_id"])
    if len(case_ids) != len(set(case_ids)):
        errors.append("Duplicate case_ids found in output")

    # Validate each row
    for idx, row in df.iterrows():
        cid = str(row["case_id"])
        status = str(row["deletion_status"])
        steps_raw = row["steps_json"]

        if status not in ALLOWED_STATUSES:
            errors.append(f"{cid}: Invalid deletion_status '{status}'")
            continue

        try:
            steps = json.loads(steps_raw)
        except Exception as e:
            errors.append(f"{cid}: Invalid JSON in steps_json: {e}")
            continue

        if not isinstance(steps, list):
            errors.append(f"{cid}: steps_json is not an array")
            continue

        if status == "NOT_APPLICABLE":
            if len(steps) != 0:
                errors.append(f"{cid}: NOT_APPLICABLE must have empty array '[]', got {len(steps)} steps")
            continue

        # Check phase ordering and sorting
        last_phase_idx = -1
        phase_steps = []
        curr_phase = None

        for step_idx, step in enumerate(steps, start=1):
            step_errs = validate_step(step, step_idx, status, cid)
            errors.extend(step_errs)

            phase = step.get("phase")
            if phase in PHASE_ORDER_INDEX:
                p_idx = PHASE_ORDER_INDEX[phase]
                if p_idx < last_phase_idx:
                    errors.append(f"{cid}: Phase out of order: {phase} after prior phase")
                last_phase_idx = p_idx

                if phase != curr_phase:
                    if phase_steps:
                        # Verify intra-phase ordering
                        for i in range(len(phase_steps) - 1):
                            s1 = phase_steps[i]
                            s2 = phase_steps[i+1]
                            k1 = (OPERATION_TO_PRIORITY_INDEX.get(s1['operation'], 999), str(s1['system_id']), str(s1['resource_id']))
                            k2 = (OPERATION_TO_PRIORITY_INDEX.get(s2['operation'], 999), str(s2['system_id']), str(s2['resource_id']))
                            if k1 > k2:
                                errors.append(f"{cid}: Intra-phase ordering violation in {curr_phase}: {s1} before {s2}")
                    curr_phase = phase
                    phase_steps = [step]
                else:
                    phase_steps.append(step)

        if phase_steps:
            for i in range(len(phase_steps) - 1):
                s1 = phase_steps[i]
                s2 = phase_steps[i+1]
                k1 = (OPERATION_TO_PRIORITY_INDEX.get(s1['operation'], 999), str(s1['system_id']), str(s1['resource_id']))
                k2 = (OPERATION_TO_PRIORITY_INDEX.get(s2['operation'], 999), str(s2['system_id']), str(s2['resource_id']))
                if k1 > k2:
                    errors.append(f"{cid}: Intra-phase ordering violation in {curr_phase}: {s1} before {s2}")

    return errors

def validate_file(file_path: str, expected_row_count: int = None) -> Tuple[bool, List[str]]:
    if not os.path.exists(file_path):
        return False, [f"File does not exist: {file_path}"]
    df = pd.read_csv(file_path)
    errors = validate_dataframe(df, expected_row_count)
    return len(errors) == 0, errors

def test_validator():
    from config import SAMPLE_OUTPUT_PATH
    success, errors = validate_file(SAMPLE_OUTPUT_PATH, expected_row_count=32)
    assert success is True, f"Validation failed on sample_output.csv: {errors}"
    print("Validator test passed successfully on sample_output.csv!")

if __name__ == "__main__":
    test_validator()
