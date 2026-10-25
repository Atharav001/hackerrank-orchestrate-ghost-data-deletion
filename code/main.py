import os
import sys
import json
import argparse
import pandas as pd
from typing import Dict, Any, List

# Allow `python3 code/main.py` from the repository root.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    DELETION_REQUESTS_PATH,
    OUTPUT_PATH,
    SAMPLE_DELETION_REQUESTS_PATH
)
from ingest import (
    load_deletion_requests,
    load_user_identities,
    load_user_audit_log,
    load_system_activity,
    load_deletion_rules,
    load_evidence_manifest
)
from identity_resolver import resolve_identity
from request_classifier import classify_request_with_scope
from evidence_retrieval import retrieve_evidence_for_case
from state_reconstruction import reconstruct_state_for_case
from policy_engine import evaluate_case_policy
from status_decision import decide_deletion_status
from step_generator import generate_steps_for_case
from validator import validate_dataframe

def audit_case(case_row: Dict[str, Any], uids_df, audit_df) -> Dict[str, Any]:
    """
    Executes Stages 2 through 10 for a single case.
    """
    case_id = str(case_row.get("case_id"))
    email = str(case_row.get("email", "")).strip()
    req_text = str(case_row.get("request_text", ""))

    # Stage 2: Identity Resolution
    identity_info = resolve_identity(email, uids_df, audit_df)

    # Stage 3: Request Classification
    req_class, scope = classify_request_with_scope(req_text, case_id=case_id)
    if req_class == "NOT_A_DELETION_REQUEST":
        return {
            "case_id": case_id,
            "deletion_status": "NOT_APPLICABLE",
            "steps_json": "[]"
        }

    # Stage 4: Evidence Retrieval
    retrieved_data = retrieve_evidence_for_case(case_row, identity_info)

    # Stage 6: State Reconstruction
    reconstructed_state = reconstruct_state_for_case(case_row, identity_info, retrieved_data)

    # Stage 7: Policy Engine
    evaluated_resources = evaluate_case_policy(reconstructed_state)
    if req_class == "PARTIAL_DELETION_REQUEST" and scope:
        evaluated_resources = [r for r in evaluated_resources if r.get("data_category") == scope]

    # Stage 8: Status Decision
    deletion_status = decide_deletion_status(req_class, evaluated_resources)

    # Stage 9 & 10: Step Generation & Deterministic Ordering
    steps = generate_steps_for_case(deletion_status, evaluated_resources)

    return {
        "case_id": case_id,
        "deletion_status": deletion_status,
        "steps_json": json.dumps(steps, separators=(',', ':'))
    }

def run_pipeline(input_path: str = DELETION_REQUESTS_PATH, output_path: str = OUTPUT_PATH) -> pd.DataFrame:
    """
    Full pipeline orchestrating Stages 1 through 11.
    """
    print(f"Loading input requests from {input_path}...")
    requests_df = pd.read_csv(input_path)
    uids_df = load_user_identities()
    audit_df = load_user_audit_log()

    print(f"Auditing {len(requests_df)} cases...")
    output_rows = []
    for idx, row in requests_df.iterrows():
        res = audit_case(dict(row), uids_df, audit_df)
        output_rows.append(res)
        if (idx + 1) % 50 == 0 or (idx + 1) == len(requests_df):
            print(f"  Processed {idx + 1}/{len(requests_df)} cases")

    out_df = pd.DataFrame(output_rows)
    # Ensure sorted by case_id
    # The supplied IDs are case_33..case_550, not fixed-width strings.
    # Sort by the numeric suffix required by the contract.
    out_df = out_df.assign(_case_num=out_df["case_id"].astype(str).str.extract(r"(\d+)$", expand=False).astype(int))
    out_df = out_df.sort_values(by=["_case_num", "case_id"]).drop(columns=["_case_num"]).reset_index(drop=True)

    # Stage 11: Schema validation
    print("Validating generated predictions against submission contract...")
    errors = validate_dataframe(out_df, expected_row_count=len(requests_df))
    if errors:
        print(f"Validation warnings/errors ({len(errors)}):")
        for err in errors[:10]:
            print("  ", err)
    else:
        print("Schema validation passed with 0 errors!")

    # Write output.csv
    print(f"Writing {len(out_df)} output rows to {output_path}...")
    out_df.to_csv(output_path, index=False)
    print("Pipeline run completed successfully.")
    return out_df

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the deletion audit on the full dataset or public sample.")
    parser.add_argument("--sample", action="store_true", help="Audit dataset/sample_deletion_requests.csv (32 public cases).")
    args = parser.parse_args()
    run_pipeline(input_path=SAMPLE_DELETION_REQUESTS_PATH if args.sample else DELETION_REQUESTS_PATH)
