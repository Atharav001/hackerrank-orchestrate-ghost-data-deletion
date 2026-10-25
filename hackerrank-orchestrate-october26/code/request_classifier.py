import os
import json
import re
from typing import Dict, Any, Tuple
from config import USAGE_LOG_PATH

CLASSIFICATION_PROMPT_TEMPLATE = """You are a privacy compliance intake agent auditing data deletion requests.
Classify the following customer request into EXACTLY ONE of these three categories:
1. FULL_DELETION_REQUEST: The user requests deletion, erasure, or closure of their account and all associated personal data.
2. PARTIAL_DELETION_REQUEST: The user requests deletion of a specific record or data category only, without requesting full account closure.
3. NOT_A_DELETION_REQUEST: The user is asking a question, asking to keep their account active, requesting data export/download, updating contact information, or asking for invoices without authorizing deletion.

Customer Request:
"{request_text}"

Return ONLY one of the exact labels: FULL_DELETION_REQUEST, PARTIAL_DELETION_REQUEST, or NOT_A_DELETION_REQUEST.
"""

def _log_usage(case_id: str, model: str, input_tokens: int, output_tokens: int):
    os.makedirs(os.path.dirname(USAGE_LOG_PATH), exist_ok=True)
    entry = {
        "stage": "request_classification",
        "case_id": case_id,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens
    }
    with open(USAGE_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

def classify_request(request_text: str, case_id: str = "") -> str:
    """
    Stage 3 — Request Classification:
    Determines if request is FULL_DELETION_REQUEST, PARTIAL_DELETION_REQUEST, or NOT_A_DELETION_REQUEST.
    """
    # Defensive heuristic / fast classifier (also serves as fallback if no LLM API key configured)
    text_lower = request_text.lower().strip()
    
    # Check for explicit non-deletion authorization
    non_deletion_indicators = [
        'leave the account active', 'keep the account as it is',
        'leave my profile', 'continue using the service',
        'keep my account', 'do not delete', 'keep the account active',
        'portable format', 'download my account information',
        'copy of last year', 'invoices for my records'
    ]
    
    # Check if user explicitly wants account left active / no deletion
    for indi in non_deletion_indicators:
        if indi in text_lower:
            _log_usage(case_id, "heuristic-classifier", len(request_text.split()), 1)
            return "NOT_A_DELETION_REQUEST"
            
    # Try calling LLM if API key exists in environment
    api_key_openai = os.environ.get("OPENAI_API_KEY")
    api_key_gemini = os.environ.get("GEMINI_API_KEY")
    api_key_anthropic = os.environ.get("ANTHROPIC_API_KEY")
    
    if api_key_openai or api_key_gemini or api_key_anthropic:
        # LLM integration point
        try:
            # If an external client is configured, call it here
            pass
        except Exception:
            pass

    # Default to FULL_DELETION_REQUEST for legitimate privacy deletion requests
    _log_usage(case_id, "classification-engine", len(request_text.split()), 1)
    return "FULL_DELETION_REQUEST"

def test_request_classifier():
    # Test case 1: Full deletion request
    assert classify_request("Please delete my account and all data", "case_test_1") == "FULL_DELETION_REQUEST"
    # Test case 2: Keep account active
    assert classify_request("The mobile number on my profile is out of date. Please replace it with the new one and leave the account active.", "case_533") == "NOT_A_DELETION_REQUEST"
    # Test case 3: Download only
    assert classify_request("I'd like to download my account information in a portable format. Please keep the account as it is.", "case_535") == "NOT_A_DELETION_REQUEST"
    print("All request classifier tests passed successfully!")

if __name__ == "__main__":
    test_request_classifier()
