import re
from typing import Dict, Any, Tuple

CLASSIFICATION_PROMPT_TEMPLATE = """You are a privacy compliance intake agent auditing data deletion requests.
Classify the following customer request into EXACTLY ONE of these three categories:
1. FULL_DELETION_REQUEST: The user requests deletion, erasure, or closure of their account and all associated personal data.
2. PARTIAL_DELETION_REQUEST: The user requests deletion of a specific record or data category only, without requesting full account closure.
3. NOT_A_DELETION_REQUEST: The user is asking a question, asking to keep their account active, requesting data export/download, updating contact information, or asking for invoices without authorizing deletion.

Customer Request:
"{request_text}"

Return ONLY one of the exact labels: FULL_DELETION_REQUEST, PARTIAL_DELETION_REQUEST, or NOT_A_DELETION_REQUEST.
"""

def classify_request_with_scope(request_text: str, case_id: str = "") -> Tuple[str, str]:
    """
    Stage 3 — Request Classification:
    Determines if request is FULL_DELETION_REQUEST, PARTIAL_DELETION_REQUEST, or NOT_A_DELETION_REQUEST.
    """
    text_lower = re.sub(r"\s+", " ", str(request_text or "").lower()).strip()
    deletion_pattern = r"(?:delet\w*|eras\w*|remov\w*|forget\w*|clos\w*|supprim\w*|suppression|effac\w*|elimin\w*|lösch\w*|削除|消去)"
    deletion = re.search(deletion_pattern, text_lower)
    explicit_non_deletion = re.search(
        r"\b(?:export|download|access|copy|correct|update|change|replace|invoice|unsubscribe|opt.?out|portable|password reset)\b",
        text_lower,
    )
    negated_deletion = re.search(
        r"\b(?:do not|don't|never|please do not)\s+(?:delete|remove|erase|close)|"
        r"\b(?:keep|leave|retain)\b.{0,45}\b(?:account|profile|data)\b",
        text_lower,
    )
    verify_deleted_state = re.search(r"\b(?:verify|check|confirm|inspect|review|audit)\b", text_lower) and re.search(
        r"\b(?:deleted|deletion|erased|removed|gone|already deleted)\b", text_lower
    )
    if (negated_deletion and not re.search(r"\b(?:but|however|except)\b.{0,60}" + deletion_pattern, text_lower)) or (explicit_non_deletion and not deletion and not verify_deleted_state):
        result = ("NOT_A_DELETION_REQUEST", "")
    elif deletion or verify_deleted_state:
        partial_terms = {
            "MARKETING_PROFILE": r"marketing|advertising",
            "ANALYTICS_PROFILE": r"analytics|telemetry",
            "SEARCH_INDEX_ENTRY": r"search index|search result",
            "SUPPORT_ATTACHMENT": r"attachment|uploaded document",
            "SUPPORT_MESSAGE": r"support|conversation|ticket|message",
            "USER_EXPORT": r"export|downloaded file",
            "EMAIL_DELIVERY_LOG": r"email log|delivery log",
            "USER_PROFILE": r"profile|account details|contact details|name|phone|email",
        }
        scope = next((cat for cat, pat in partial_terms.items() if re.search(pat, text_lower)), "")
        all_scope = re.search(r"\b(all|everything|entire|full|account and all|all personal data)\b", text_lower)
        result = ("PARTIAL_DELETION_REQUEST", scope) if scope and not all_scope else ("FULL_DELETION_REQUEST", "")
    else:
        result = ("NOT_A_DELETION_REQUEST", "")
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
