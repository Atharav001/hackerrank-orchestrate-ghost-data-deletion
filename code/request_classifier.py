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

def classify_request_with_scope(request_text: str, case_id: str = "") -> Tuple[str, str]:
    """
    Stage 3 — Request Classification:
    Determines if request is FULL_DELETION_REQUEST, PARTIAL_DELETION_REQUEST, or NOT_A_DELETION_REQUEST.
    """
    text_lower = request_text.lower().strip()
    deletion = re.search(r"(delet\w*|eras\w*|remov\w*|forget\w*|clos\w*|supprim\w*|elimin\w*|lösch\w*|削除)", text_lower)
    negated = re.search(r"\b(?:do not|don't|never)\s+(?:delete|remove|erase)|\b(?:keep|leave|retain)\b.{0,30}\b(?:delete|remove|erase)\b", text_lower)
    non_deletion = re.search(r"\b(export|download|access|copy|correct|update|change|replace|invoice|marketing|unsubscribe|opt.?out|portable)\b", text_lower)
    if (not deletion) or negated or (non_deletion and not re.search(r"\b(delete|erase|remove|forget|close)\b", text_lower)):
        result = ("NOT_A_DELETION_REQUEST", "")
    else:
        partial_terms = {
            "USER_PROFILE": r"profile|account details|contact details|name|phone|email",
            "SUPPORT_MESSAGE": r"support|conversation|ticket|message",
            "SUPPORT_ATTACHMENT": r"attachment|document",
            "ANALYTICS_PROFILE": r"analytics|analytics profile",
            "MARKETING_PROFILE": r"marketing|advertising",
            "USER_EXPORT": r"export|downloaded file",
            "SEARCH_INDEX_ENTRY": r"search index|search result",
            "EMAIL_DELIVERY_LOG": r"email log|delivery log",
        }
        scope = next((cat for cat, pat in partial_terms.items() if re.search(pat, text_lower)), "")
        result = ("PARTIAL_DELETION_REQUEST", scope) if scope and not re.search(r"\b(all|everything|entire|full|account and all)\b", text_lower) else ("FULL_DELETION_REQUEST", "")
    _log_usage(case_id, "deterministic-classifier", len(request_text.split()), 1)
    return result

def classify_request(request_text: str, case_id: str = "") -> str:
    return classify_request_with_scope(request_text, case_id)[0]

def test_request_classifier():
    # Test case 1: Full deletion request
    assert classify_request("Please delete my account and all data", "case_test_1") == "FULL_DELETION_REQUEST"
    assert classify_request("Delete only my marketing profile", "case_test_partial") == "PARTIAL_DELETION_REQUEST"
    # Test case 2: Keep account active
    assert classify_request("The mobile number on my profile is out of date. Please replace it with the new one and leave the account active.", "case_533") == "NOT_A_DELETION_REQUEST"
    # Test case 3: Download only
    assert classify_request("I'd like to download my account information in a portable format. Please keep the account as it is.", "case_535") == "NOT_A_DELETION_REQUEST"
    print("All request classifier tests passed successfully!")

if __name__ == "__main__":
    test_request_classifier()
