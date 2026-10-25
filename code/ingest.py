import os
import pandas as pd
from config import (
    DELETION_REQUESTS_PATH,
    SAMPLE_DELETION_REQUESTS_PATH,
    SAMPLE_OUTPUT_PATH,
    USER_IDENTITIES_PATH,
    USER_AUDIT_LOG_PATH,
    SYSTEM_ACTIVITY_PATH,
    DELETION_RULES_PATH,
    EVIDENCE_FILES_PATH,
    DATASET_DIR
)

def load_deletion_requests(path=DELETION_REQUESTS_PATH) -> pd.DataFrame:
    df = pd.read_csv(path)
    required_cols = ['case_id', 'email', 'requested_at', 'reported_status', 'reported_at', 'audit_at', 'request_text']
    assert list(df.columns) == required_cols, f"Mismatch in deletion_requests columns: {df.columns}"
    return df

def load_sample_deletion_requests(path=SAMPLE_DELETION_REQUESTS_PATH) -> pd.DataFrame:
    df = pd.read_csv(path)
    return df

def load_sample_output(path=SAMPLE_OUTPUT_PATH) -> pd.DataFrame:
    df = pd.read_csv(path)
    return df

def load_user_identities(path=USER_IDENTITIES_PATH) -> pd.DataFrame:
    df = pd.read_csv(path)
    required_cols = ['user_id', 'name', 'email', 'phone', 'email_hash', 'updated_at']
    assert list(df.columns) == required_cols, f"Mismatch in user_identities columns: {df.columns}"
    return df

def load_user_audit_log(path=USER_AUDIT_LOG_PATH) -> pd.DataFrame:
    df = pd.read_csv(path)
    required_cols = ['audit_id', 'user_id', 'event_time', 'field_name', 'old_value', 'new_value']
    assert list(df.columns) == required_cols, f"Mismatch in user_audit_log columns: {df.columns}"
    return df

def load_system_activity(path=SYSTEM_ACTIVITY_PATH) -> pd.DataFrame:
    df = pd.read_csv(path)
    required_cols = ['activity_id', 'event_time', 'event_type', 'source_system', 'target_system', 'resource_id', 'reported_result', 'details']
    assert list(df.columns) == required_cols, f"Mismatch in system_activity columns: {df.columns}"
    return df

def load_deletion_rules(path=DELETION_RULES_PATH) -> pd.DataFrame:
    df = pd.read_csv(path)
    required_cols = ['rule_id', 'data_category', 'condition', 'required_action']
    assert list(df.columns) == required_cols, f"Mismatch in deletion_rules columns: {df.columns}"
    return df

def load_evidence_manifest(path=EVIDENCE_FILES_PATH) -> pd.DataFrame:
    df = pd.read_csv(path)
    required_cols = ['file_id', 'file_path', 'origin', 'captured_at']
    assert list(df.columns) == required_cols, f"Mismatch in evidence_files columns: {df.columns}"
    return df

def test_ingest():
    del_req = load_deletion_requests()
    assert len(del_req) == 518, f"Expected 518 deletion requests, got {len(del_req)}"
    
    uids = load_user_identities()
    assert len(uids) == 850
    
    audit = load_user_audit_log()
    assert len(audit) == 306
    
    act = load_system_activity()
    assert len(act) == 4011
    
    rules = load_deletion_rules()
    assert len(rules) == 15
    
    manifest = load_evidence_manifest()
    assert len(manifest) == 94
    
    # Check template
    out_tmpl = pd.read_csv(os.path.join(DATASET_DIR, "output.csv"))
    assert list(out_tmpl.columns) == ['case_id', 'deletion_status', 'steps_json']
    
    print("All ingest tests passed successfully!")

if __name__ == "__main__":
    test_ingest()
