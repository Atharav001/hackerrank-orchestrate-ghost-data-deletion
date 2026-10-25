import os
import json
import re
import glob
from typing import List, Dict, Any, Set
import pandas as pd
from config import DATASET_DIR, EVIDENCE_FILES_PATH

_EVIDENCE_CACHE = None

def _clean_str(val: Any) -> str:
    if val is None or pd.isna(val):
        return ""
    s = str(val).strip()
    return "" if s.lower() in ("none", "null", "nan") else s

def extract_all_evidence_records() -> List[Dict[str, Any]]:
    """
    Parses all 94 evidence files in dataset/evidence/ into normalized records:
    {
       'evidence_id': str,
       'file_path': str,
       'captured_at': str,
       'system_id': str,
       'resource_id': str,
       'data_category': str,
       'state': str,  # PRESENT, ABSENT, REDACTED, ANONYMIZED, ACTIVE, DISABLED, BLOCKED
       'identifiers': set of str,
       'details': str
    }
    """
    global _EVIDENCE_CACHE
    if _EVIDENCE_CACHE is not None:
        return _EVIDENCE_CACHE

    manifest_df = pd.read_csv(EVIDENCE_FILES_PATH)
    all_records = []

    for _, row in manifest_df.iterrows():
        eid = str(row['file_id'])
        rel_path = str(row['file_path'])
        captured_at = str(row['captured_at'])
        full_path = os.path.join(DATASET_DIR, rel_path)
        ext = os.path.splitext(full_path)[1].lower()

        if not os.path.exists(full_path):
            continue

        # 1. JSON records
        if ext == ".json":
            try:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    data = json.load(f)

                # Format A: service_resource_export_*.json
                if "service_exports" in data:
                    for svc, d_svc in data["service_exports"].items():
                        for subk, sublist in d_svc.items():
                            for it in sublist:
                                res_id = it.get("resource_id") or ""
                                if not res_id:
                                    continue
                                id_set = set()
                                for k in ["customer_reference", "subject_reference", "email", "owner_email", "customer_email", "phone", "owner_phone", "email_hash", "query"]:
                                    val = _clean_str(it.get(k))
                                    if val:
                                        id_set.add(val)
                                # Documents inside hits
                                if "hits" in it and isinstance(it["hits"], dict):
                                    for doc in it["hits"].get("documents", []):
                                        for k in ["email", "phone", "customer_reference", "display_name", "email_hash"]:
                                            val = _clean_str(doc.get(k))
                                            if val:
                                                id_set.add(val)

                                state = "PRESENT"
                                cat = "USER_PROFILE"

                                if svc == "account_service":
                                    cat = "USER_PROFILE"
                                    state = "ABSENT" if it.get("status_code") == 404 or it.get("profile") is None else "PRESENT"
                                elif svc == "analytics_platform":
                                    cat = "ANALYTICS_PROFILE"
                                    has_pii = bool(_clean_str(it.get("email")) or _clean_str(it.get("customer_reference")) or _clean_str(it.get("phone")))
                                    state = "PRESENT" if has_pii else "ANONYMIZED"
                                elif svc == "backup_service":
                                    cat = "BACKUP_ARCHIVE"
                                    state = "BLOCKED" if it.get("restore_allowed") is False else "ACTIVE"
                                elif svc == "export_service":
                                    cat = "USER_EXPORT"
                                    state = "PRESENT"
                                elif svc == "integration_service":
                                    cat = "DATA_FLOW"
                                    state = "ACTIVE" if it.get("enabled") is True else "DISABLED"
                                elif svc == "search_service":
                                    cat = "SEARCH_INDEX_ENTRY"
                                    total_hits = it.get("hits", {}).get("total", 0) if isinstance(it.get("hits"), dict) else 0
                                    state = "PRESENT" if total_hits > 0 else "ABSENT"
                                elif svc == "security_service":
                                    cat = "SECURITY_AUDIT_LOG"
                                    state = "PRESENT"
                                elif svc == "support_platform":
                                    cat = "SUPPORT_MESSAGE"
                                    has_pii = bool(_clean_str(it.get("requester_email")) or _clean_str(it.get("requester_phone")) or _clean_str(it.get("requester_name")))
                                    state = "PRESENT" if has_pii else "REDACTED"

                                all_records.append({
                                    "evidence_id": eid,
                                    "file_path": rel_path,
                                    "captured_at": captured_at,
                                    "system_id": svc,
                                    "resource_id": res_id,
                                    "data_category": cat,
                                    "state": state,
                                    "identifiers": id_set,
                                    "details": str(it)
                                })

                # Format B: customer_data_snapshot_bundle_*.json
                elif "snapshots" in data:
                    for snap in data["snapshots"]:
                        coll = snap.get("collection", "")
                        for r in snap.get("records", []):
                            res_id = r.get("resource_id") or ""
                            if not res_id:
                                continue
                            id_set = set()
                            for k in ["customer_reference", "subject_reference", "email", "phone", "email_hash", "name", "owner_email"]:
                                val = _clean_str(r.get(k))
                                if val:
                                    id_set.add(val)

                            svc = "account_service"
                            cat = "USER_PROFILE"
                            state = "PRESENT"

                            if coll == "customer_profiles":
                                svc = "account_service"
                                cat = "USER_PROFILE"
                                state = "PRESENT"
                            elif coll in ("deleted_customer_references", "account_tombstones"):
                                svc = "identity_service"
                                cat = "ACCOUNT_TOMBSTONE"
                                has_pii = bool(_clean_str(r.get("email")) or _clean_str(r.get("phone")) or _clean_str(r.get("name")))
                                state = "PRESENT" if has_pii else "REDACTED"
                            elif coll == "security_audit_events":
                                svc = "security_service"
                                cat = "SECURITY_AUDIT_LOG"
                                state = "PRESENT"
                            elif coll == "analytics_profiles":
                                svc = "analytics_platform"
                                cat = "ANALYTICS_PROFILE"
                                has_pii = bool(_clean_str(r.get("email")) or _clean_str(r.get("phone")) or _clean_str(r.get("customer_reference")))
                                state = "PRESENT" if has_pii else "ANONYMIZED"
                            elif coll == "support_conversations":
                                svc = "support_platform"
                                cat = "SUPPORT_MESSAGE"
                                has_pii = bool(_clean_str(r.get("email")) or _clean_str(r.get("phone")) or _clean_str(r.get("requester_email")))
                                state = "PRESENT" if has_pii else "REDACTED"
                            elif coll == "search_index_entries":
                                svc = "search_service"
                                cat = "SEARCH_INDEX_ENTRY"
                                state = "PRESENT"
                            elif coll == "data_flow_connectors":
                                svc = "integration_service"
                                cat = "DATA_FLOW"
                                state = "ACTIVE" if r.get("enabled") is True else "DISABLED"
                            elif coll == "backup_archives":
                                svc = "backup_service"
                                cat = "BACKUP_ARCHIVE"
                                state = "ACTIVE" if r.get("restore_allowed") is True else "BLOCKED"
                            elif coll == "data_exports":
                                svc = "export_service"
                                cat = "USER_EXPORT"
                                state = "PRESENT"

                            all_records.append({
                                "evidence_id": eid,
                                "file_path": rel_path,
                                "captured_at": captured_at,
                                "system_id": svc,
                                "resource_id": res_id,
                                "data_category": cat,
                                "state": state,
                                "identifiers": id_set,
                                "details": str(r)
                            })

                # Format C: generic collection with records list
                elif "records" in data:
                    coll = data.get("collection") or data.get("origin") or ""
                    for r in data["records"]:
                        res_id = r.get("resource_id") or ""
                        if not res_id:
                            continue
                        id_set = set()
                        for k in ["customer_reference", "subject_reference", "email", "phone", "email_hash", "name", "owner_email", "customer_email"]:
                            val = _clean_str(r.get(k))
                            if val:
                                id_set.add(val)

                        svc = "account_service"
                        cat = "USER_PROFILE"
                        state = "PRESENT"

                        if "export" in rel_path:
                            svc = "export_service"
                            cat = "USER_EXPORT"
                            state = "PRESENT"
                        elif "analytics" in rel_path:
                            svc = "analytics_platform"
                            cat = "ANALYTICS_PROFILE"
                            has_pii = bool(_clean_str(r.get("email")) or _clean_str(r.get("phone")) or _clean_str(r.get("customer_reference")))
                            state = "PRESENT" if has_pii else "ANONYMIZED"
                        elif "connector" in rel_path:
                            svc = "integration_service"
                            cat = "DATA_FLOW"
                            state = "ACTIVE" if r.get("enabled") is True else "DISABLED"
                        elif "security" in rel_path:
                            svc = "security_service"
                            cat = "SECURITY_AUDIT_LOG"
                            state = "PRESENT"

                        all_records.append({
                            "evidence_id": eid,
                            "file_path": rel_path,
                            "captured_at": captured_at,
                            "system_id": svc,
                            "resource_id": res_id,
                            "data_category": cat,
                            "state": state,
                            "identifiers": id_set,
                            "details": str(r)
                        })

            except Exception:
                pass

        # 2. Text handover file
        elif ext == ".txt":
            try:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("- ") and "|" in line:
                            parts = [p.strip() for p in line[2:].split("|")]
                            if len(parts) >= 6:
                                t_stamp, svc, res_id, cat, raw_status, ident = parts[:6]
                                id_set = set()
                                if ident and ident.lower() != "no direct identifier":
                                    id_set.add(ident)

                                state = "PRESENT"
                                raw_upper = raw_status.upper()
                                if raw_upper in ("NOT_FOUND", "ABSENT"):
                                    state = "ABSENT"
                                elif raw_upper in ("FOUND", "PRESENT"):
                                    state = "PRESENT"
                                elif raw_upper == "ANONYMIZED":
                                    state = "ANONYMIZED"
                                elif raw_upper == "REDACTED":
                                    state = "REDACTED"
                                elif raw_upper == "IDENTIFIABLE":
                                    state = "PRESENT"
                                elif raw_upper in ("ACTIVE", "ENABLED"):
                                    state = "ACTIVE"
                                elif raw_upper in ("DISABLED", "STOPPED"):
                                    state = "DISABLED"
                                elif raw_upper == "BLOCKED":
                                    state = "BLOCKED"

                                all_records.append({
                                    "evidence_id": eid,
                                    "file_path": rel_path,
                                    "captured_at": captured_at,
                                    "system_id": svc,
                                    "resource_id": res_id,
                                    "data_category": cat,
                                    "state": state,
                                    "identifiers": id_set,
                                    "details": line
                                })
            except Exception:
                pass

        # 3. SQL database snapshots
        elif ext == ".sql":
            try:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line_s = line.strip()
                        if line_s.startswith("INSERT INTO"):
                            m = re.match(r"INSERT INTO [\"`]?([a-zA-Z0-9_]+)[\"`]? VALUES\s*\((.*)\);?", line_s)
                            if m:
                                table_name = m.group(1)
                                vals_str = m.group(2)
                                raw_vals = [v.strip().strip("'\"") for v in vals_str.split(",")]
                                if not raw_vals:
                                    continue
                                res_id = raw_vals[0]
                                id_set = set()
                                for v in raw_vals[1:]:
                                    cv = _clean_str(v)
                                    if cv and len(cv) >= 3 and cv.upper() not in ("NULL", "NONE", "ACTIVE", "DELETED", "BLOCKED", "ENABLED", "DISABLED", "0", "1"):
                                        id_set.add(cv)

                                svc = "account_service"
                                cat = "USER_PROFILE"
                                state = "PRESENT"

                                if "customer_profiles" in table_name or "customer_accounts" in table_name or "customer_data" in table_name:
                                    svc = "account_service"
                                    cat = "USER_PROFILE"
                                    state = "PRESENT"
                                elif "search" in table_name:
                                    svc = "search_service"
                                    cat = "SEARCH_INDEX_ENTRY"
                                    state = "PRESENT"
                                elif "analytics" in table_name:
                                    svc = "analytics_platform"
                                    cat = "ANALYTICS_PROFILE"
                                    state = "PRESENT"
                                elif "support" in table_name:
                                    svc = "support_platform"
                                    cat = "SUPPORT_MESSAGE"
                                    state = "PRESENT"
                                elif "backup" in table_name:
                                    svc = "backup_service"
                                    cat = "BACKUP_ARCHIVE"
                                    # restore allowed flag is usually in raw_vals
                                    is_allowed = any(v in ("1", "'1'", "true", "TRUE") for v in raw_vals)
                                    state = "ACTIVE" if is_allowed else "BLOCKED"
                                elif "connector" in table_name or "data_flow" in table_name:
                                    svc = "integration_service"
                                    cat = "DATA_FLOW"
                                    is_enabled = any(v in ("1", "'1'", "true", "TRUE") for v in raw_vals)
                                    state = "ACTIVE" if is_enabled else "DISABLED"
                                elif "export" in table_name:
                                    svc = "export_service"
                                    cat = "USER_EXPORT"
                                    state = "PRESENT"
                                elif "audit" in table_name or "security" in table_name:
                                    svc = "security_service"
                                    cat = "SECURITY_AUDIT_LOG"
                                    state = "PRESENT"

                                all_records.append({
                                    "evidence_id": eid,
                                    "file_path": rel_path,
                                    "captured_at": captured_at,
                                    "system_id": svc,
                                    "resource_id": res_id,
                                    "data_category": cat,
                                    "state": state,
                                    "identifiers": id_set,
                                    "details": line_s
                                })
            except Exception:
                pass

        # 4. Log files
        elif ext == ".log":
            try:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if "resource_id=" not in line and '"resource_id":' not in line:
                            continue
                        
                        # Extract resource_id
                        m_res = re.search(r'resource_id=[\"|\']?([a-zA-Z0-9_]+)[\"|\']?', line)
                        if not m_res:
                            m_res = re.search(r'\"resource_id\":\s*\"([^\"]+)\"', line)
                        if not m_res:
                            continue
                        res_id = m_res.group(1)

                        # Extract service
                        m_svc = re.search(r'service=[\"|\']?([a-zA-Z0-9_]+)[\"|\']?', line)
                        if not m_svc:
                            m_svc = re.search(r'system=[\"|\']?([a-zA-Z0-9_]+)[\"|\']?', line)
                        if not m_svc:
                            m_svc = re.search(r'\"service\":\s*\"([^\"]+)\"', line)
                        svc = m_svc.group(1) if m_svc else "account_service"

                        # Extract identifiers
                        id_set = set()
                        for pattern in [r'lookup_key=[\"|\']?([^\"\s]+)[\"|\']?',
                                        r'customer_reference=[\"|\']?([^\"\s]+)[\"|\']?',
                                        r'subject_reference=[\"|\']?([^\"\s]+)[\"|\']?',
                                        r'subject_ref=[\"|\']?([^\"\s]+)[\"|\']?',
                                        r'email=[\"|\']?([^\"\s]+)[\"|\']?',
                                        r'customer_email=[\"|\']?([^\"\s]+)[\"|\']?',
                                        r'matched_value=[\"|\']?([^\"\s]+)[\"|\']?',
                                        r'correlation_key=[\"|\']?([^\"\s]+)[\"|\']?']:
                            for m_id in re.finditer(pattern, line):
                                val = _clean_str(m_id.group(1))
                                if val:
                                    id_set.add(val)

                        state = "PRESENT"
                        cat = "USER_PROFILE"

                        if svc == "account_service":
                            cat = "USER_PROFILE"
                            state = "ABSENT" if ("rows=0" in line or "404" in line) else "PRESENT"
                        elif svc == "search_service":
                            cat = "SEARCH_INDEX_ENTRY"
                            state = "PRESENT" if ("result=hit" in line or 'total_hits=1' in line or 'result="hit"' in line) else "ABSENT"
                        elif svc == "support_platform":
                            cat = "SUPPORT_MESSAGE"
                            state = "PRESENT" if ("matched_value" in line or "message_pii_scan" in line or "attachment_pii_scan" in line) else "REDACTED"
                        elif svc == "analytics_platform":
                            cat = "ANALYTICS_PROFILE"
                            has_email = any("@" in s for s in id_set)
                            state = "PRESENT" if has_email else "ANONYMIZED"
                        elif svc == "integration_service":
                            cat = "DATA_FLOW"
                            state = "ACTIVE" if ("enabled=true" in line or 'enabled="true"' in line) else "DISABLED"
                        elif svc == "backup_service":
                            cat = "BACKUP_ARCHIVE"
                            state = "BLOCKED" if ("restore_allowed=false" in line or 'restore_allowed="false"' in line) else "ACTIVE"
                        elif svc == "security_service":
                            cat = "SECURITY_AUDIT_LOG"
                            state = "PRESENT"

                        all_records.append({
                            "evidence_id": eid,
                            "file_path": rel_path,
                            "captured_at": captured_at,
                            "system_id": svc,
                            "resource_id": res_id,
                            "data_category": cat,
                            "state": state,
                            "identifiers": id_set,
                            "details": line.strip()
                        })
            except Exception:
                pass

        # 5. PDF documents
        elif ext == ".pdf":
            try:
                import pypdf
                reader = pypdf.PdfReader(full_path)
                pdf_text = "\n".join([p.extract_text() or "" for p in reader.pages])

                # Extract emails, phones, user_ids
                emails = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', pdf_text)
                user_ids = re.findall(r'user_\d+', pdf_text)
                res_ids = re.findall(r'(?:support_\d+|export_\d+|audit_record_\d+|account_\d+)', pdf_text)
                
                id_set = set(emails + user_ids)
                primary_res = res_ids[0] if res_ids else f"doc_{eid}"

                svc = "support_platform"
                cat = "SUPPORT_ATTACHMENT"
                if "history" in rel_path or "statement" in pdf_text.lower():
                    svc = "export_service"
                    cat = "USER_EXPORT"
                elif "security" in rel_path:
                    svc = "security_service"
                    cat = "SECURITY_AUDIT_LOG"
                elif "legal" in rel_path:
                    svc = "legal_service"
                    cat = "LEGAL_HOLD_RECORD"

                all_records.append({
                    "evidence_id": eid,
                    "file_path": rel_path,
                    "captured_at": captured_at,
                    "system_id": svc,
                    "resource_id": primary_res,
                    "data_category": cat,
                    "state": "PRESENT",
                    "identifiers": id_set,
                    "details": pdf_text[:200]
                })
            except Exception:
                pass

    _EVIDENCE_CACHE = all_records
    return all_records

def test_evidence_extraction():
    records = extract_all_evidence_records()
    assert len(records) > 500, f"Expected > 500 records, got {len(records)}"
    
    # Check that case_05's account_005 is found in evidence_54
    ev54_acc5 = [r for r in records if r['resource_id'] == 'account_005' and r['evidence_id'] == 'evidence_54']
    assert len(ev54_acc5) >= 1, "Failed to find account_005 in evidence_54"
    assert ev54_acc5[0]['state'] == 'PRESENT'
    
    # Check that case_11's search_052 is found in evidence_03
    ev03_s52 = [r for r in records if r['resource_id'] == 'search_052' and r['evidence_id'] == 'evidence_03']
    assert len(ev03_s52) >= 1, "Failed to find search_052 in evidence_03"
    assert ev03_s52[0]['state'] == 'PRESENT'

    print(f"Evidence extraction passed: {len(records)} normalized records extracted!")

if __name__ == "__main__":
    test_evidence_extraction()
