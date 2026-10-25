import os

# Base paths
CONFIG_FILE_PATH = os.path.abspath(__file__)
CODE_DIR = os.path.dirname(CONFIG_FILE_PATH)
REPO_ROOT = os.path.dirname(CODE_DIR)
DATASET_DIR = os.path.join(REPO_ROOT, "dataset")
EVIDENCE_DIR = os.path.join(DATASET_DIR, "evidence")
OUTPUT_PATH = os.path.join(REPO_ROOT, "output.csv")
EVAL_DIR = os.path.join(CODE_DIR, "evaluation")
USAGE_LOG_PATH = os.path.join(EVAL_DIR, "usage_log.jsonl")

# Dataset file paths
DELETION_REQUESTS_PATH = os.path.join(DATASET_DIR, "deletion_requests.csv")
SAMPLE_DELETION_REQUESTS_PATH = os.path.join(DATASET_DIR, "sample_deletion_requests.csv")
SAMPLE_OUTPUT_PATH = os.path.join(DATASET_DIR, "sample_output.csv")
USER_IDENTITIES_PATH = os.path.join(DATASET_DIR, "user_identities.csv")
USER_AUDIT_LOG_PATH = os.path.join(DATASET_DIR, "user_audit_log.csv")
SYSTEM_ACTIVITY_PATH = os.path.join(DATASET_DIR, "system_activity.csv")
DELETION_RULES_PATH = os.path.join(DATASET_DIR, "deletion_rules.csv")
EVIDENCE_FILES_PATH = os.path.join(DATASET_DIR, "evidence_files.csv")

# Exact allowed operations and states table (ordered by priority index)
OPERATION_PRIORITY = [
    ("FINDING", "REPORT_REMAINING_RECORD", "PRESENT"),          # 1
    ("FINDING", "REPORT_EXPOSED_PII", "PRESENT"),               # 2
    ("FINDING", "REPORT_ACTIVE_DATA_FLOW", "ACTIVE"),            # 3
    ("FINDING", "REPORT_RESTORE_RISK", "ACTIVE"),                # 4
    ("REMEDIATION", "DISABLE_DATA_FLOW", "DISABLED"),            # 5
    ("REMEDIATION", "BLOCK_RESTORE", "BLOCKED"),                 # 6
    ("REMEDIATION", "DELETE_RECORD", "ABSENT"),                  # 7
    ("REMEDIATION", "REDACT_RECORD", "REDACTED"),                # 8
    ("REMEDIATION", "ANONYMIZE_RECORD", "ANONYMIZED"),           # 9
    ("VERIFICATION", "VERIFY_RECORD_ABSENT", "ABSENT"),          # 10
    ("VERIFICATION", "VERIFY_RECORD_PRESENT", "PRESENT"),        # 11
    ("VERIFICATION", "VERIFY_RECORD_REDACTED", "REDACTED"),      # 12
    ("VERIFICATION", "VERIFY_RECORD_ANONYMIZED", "ANONYMIZED"),  # 13
    ("VERIFICATION", "VERIFY_DATA_FLOW_DISABLED", "DISABLED"),   # 14
    ("VERIFICATION", "VERIFY_RESTORE_BLOCKED", "BLOCKED"),       # 15
]

OPERATION_TO_PRIORITY_INDEX = {
    item[1]: idx for idx, item in enumerate(OPERATION_PRIORITY)
}

OPERATION_TO_PHASE = {
    item[1]: item[0] for item in OPERATION_PRIORITY
}

OPERATION_TO_STATE = {
    item[1]: item[2] for item in OPERATION_PRIORITY
}

PHASE_ORDER = ["FINDING", "REMEDIATION", "VERIFICATION"]
PHASE_ORDER_INDEX = {p: i for i, p in enumerate(PHASE_ORDER)}

ALLOWED_STATUSES = ["COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"]
ALLOWED_PHASES = ["FINDING", "REMEDIATION", "VERIFICATION"]
ALLOWED_OPERATIONS = list(OPERATION_TO_PRIORITY_INDEX.keys())
ALLOWED_STATES = ["ABSENT", "ACTIVE", "ANONYMIZED", "BLOCKED", "DISABLED", "PRESENT", "REDACTED"]
