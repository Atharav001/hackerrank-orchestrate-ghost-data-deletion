from typing import List, Dict, Any

def decide_deletion_status(request_classification: str, evaluated_resources: List[Dict[str, Any]]) -> str:
    """
    Stage 8 — Status Decision Layer:
    Determines case deletion_status: COMPLETE, INCOMPLETE, or NOT_APPLICABLE.
    """
    if request_classification == "NOT_A_DELETION_REQUEST":
        return "NOT_APPLICABLE"

    # If any resource is classified as a PROBLEM, status is INCOMPLETE
    for res in evaluated_resources:
        if res.get("classification") == "PROBLEM":
            return "INCOMPLETE"

    return "COMPLETE"

def test_status_decision():
    assert decide_deletion_status("NOT_A_DELETION_REQUEST", []) == "NOT_APPLICABLE"
    assert decide_deletion_status("FULL_DELETION_REQUEST", [{"classification": "OK"}]) == "COMPLETE"
    assert decide_deletion_status("FULL_DELETION_REQUEST", [{"classification": "OK"}, {"classification": "PROBLEM"}]) == "INCOMPLETE"
    print("Status decision tests passed successfully!")

if __name__ == "__main__":
    test_status_decision()
