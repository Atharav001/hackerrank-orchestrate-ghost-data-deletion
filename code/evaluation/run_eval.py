import os
import sys
import json
import pandas as pd
from typing import Dict, Any, List

# Ensure code directory is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from config import SAMPLE_DELETION_REQUESTS_PATH, SAMPLE_OUTPUT_PATH
from ingest import load_user_identities, load_user_audit_log
from main import audit_case

def evaluate_predictions(pred_df: pd.DataFrame, ground_truth_df: pd.DataFrame) -> Dict[str, Any]:
    """
    Computes:
    1. Case-level status accuracy
    2. Step-level / field-level accuracy
    3. Sequence accuracy
    """
    # Merge on case_id
    merged = pd.merge(ground_truth_df, pred_df, on="case_id", suffixes=("_true", "_pred"))
    total_cases = len(merged)

    status_matches = 0
    sequence_matches = 0
    total_expected_steps = 0
    total_matched_steps = 0
    total_field_comparisons = 0
    total_field_matches = 0

    mismatches = []

    for _, row in merged.iterrows():
        case_id = row["case_id"]
        status_true = row["deletion_status_true"]
        status_pred = row["deletion_status_pred"]

        status_ok = (status_true == status_pred)
        if status_ok:
            status_matches += 1

        steps_true = json.loads(row["steps_json_true"])
        steps_pred = json.loads(row["steps_json_pred"])

        total_expected_steps += len(steps_true)

        # Check sequence accuracy: exact length and exact identical step objects in order
        sequence_ok = False
        if len(steps_true) == len(steps_pred):
            seq_equal = True
            for st, sp in zip(steps_true, steps_pred):
                for k in ["step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"]:
                    total_field_comparisons += 1
                    if st.get(k) == sp.get(k):
                        total_field_matches += 1
                    else:
                        seq_equal = False
                if st == sp:
                    total_matched_steps += 1
            if seq_equal:
                sequence_ok = True
                sequence_matches += 1
        else:
            # Step counts differ
            for sp in steps_pred:
                # count field comparisons against closest or record mismatch
                pass
            for st in steps_true:
                for k in ["step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"]:
                    total_field_comparisons += 1

        if not (status_ok and sequence_ok):
            mismatches.append({
                "case_id": case_id,
                "status_true": status_true,
                "status_pred": status_pred,
                "steps_true_count": len(steps_true),
                "steps_pred_count": len(steps_pred),
                "steps_true": steps_true,
                "steps_pred": steps_pred
            })

    case_status_accuracy = (status_matches / total_cases) * 100.0 if total_cases > 0 else 0.0
    sequence_accuracy = (sequence_matches / total_cases) * 100.0 if total_cases > 0 else 0.0
    field_accuracy = (total_field_matches / total_field_comparisons) * 100.0 if total_field_comparisons > 0 else 0.0

    return {
        "total_cases": total_cases,
        "status_matches": status_matches,
        "case_status_accuracy": case_status_accuracy,
        "sequence_matches": sequence_matches,
        "sequence_accuracy": sequence_accuracy,
        "field_accuracy": field_accuracy,
        "mismatches": mismatches
    }

def run_sample_eval():
    """
    Runs the pipeline on sample_deletion_requests.csv and compares with sample_output.csv.
    """
    print(f"Loading sample ground truth from {SAMPLE_OUTPUT_PATH}...")
    ground_truth_df = pd.read_csv(SAMPLE_OUTPUT_PATH)

    print(f"Loading sample requests from {SAMPLE_DELETION_REQUESTS_PATH}...")
    requests_df = pd.read_csv(SAMPLE_DELETION_REQUESTS_PATH)
    uids_df = load_user_identities()
    audit_df = load_user_audit_log()

    print(f"Auditing {len(requests_df)} sample cases...")
    pred_rows = []
    for _, row in requests_df.iterrows():
        res = audit_case(dict(row), uids_df, audit_df)
        pred_rows.append(res)

    pred_df = pd.DataFrame(pred_rows)
    metrics = evaluate_predictions(pred_df, ground_truth_df)

    print("\n" + "=" * 50)
    print("EVALUATION RESULTS (Sample Dataset - 32 Cases):")
    print("=" * 50)
    print(f"Case-level Status Accuracy: {metrics['case_status_accuracy']:.2f}% ({metrics['status_matches']}/{metrics['total_cases']})")
    print(f"Sequence Accuracy:         {metrics['sequence_accuracy']:.2f}% ({metrics['sequence_matches']}/{metrics['total_cases']})")
    print(f"Field-level Accuracy:      {metrics['field_accuracy']:.2f}%")
    print("=" * 50)

    if metrics["mismatches"]:
        print(f"\nMismatches ({len(metrics['mismatches'])} cases):")
        for m in metrics["mismatches"][:5]:
            print(f"- Case: {m['case_id']} | Status True: {m['status_true']} vs Pred: {m['status_pred']}")
    else:
        print("\nAll 32 sample cases matched perfectly!")

    return metrics

if __name__ == "__main__":
    run_sample_eval()
