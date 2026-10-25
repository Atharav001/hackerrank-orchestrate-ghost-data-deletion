import os
import json
import re
import sqlite3
from typing import List, Dict, Any, Set
import pandas as pd
from config import DATASET_DIR, EVIDENCE_FILES_PATH

_EVIDENCE_CACHE = None

def _parse_sql_values(value_text: str) -> List[str]:
    """Parse one SQL VALUES tuple without splitting commas inside quoted text."""
    values, buf, quote, i = [], [], None, 0
    while i < len(value_text):
        ch = value_text[i]
        if quote:
            if ch == quote:
                if i + 1 < len(value_text) and value_text[i + 1] == quote:
                    buf.append(quote); i += 2; continue
                quote = None
            else:
                buf.append(ch)
        elif ch in "'\"":
            quote = ch
        elif ch == ',':
            values.append(''.join(buf).strip()); buf = []
        else:
            buf.append(ch)
        i += 1
    values.append(''.join(buf).strip())
    return values

def _clean_str(val: Any) -> str:
    if val is None or pd.isna(val):
        return ""
    s = str(val).strip()
    return "" if s.lower() in ("none", "null", "nan") else s

def _as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "enabled", "active", "allowed"}

def _sql_records(path: str, evidence_id: str, rel_path: str, captured_at: str) -> List[Dict[str, Any]]:
    """Read SQLite-compatible evidence through SQLite so quoted/multiline values stay intact."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        with open(path, "r", encoding="utf-8", errors="strict") as src:
            conn.executescript(src.read())
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        normalized: List[Dict[str, Any]] = []
        for table in tables:
            quoted_table = '"' + table.replace('"', '""') + '"'
            for raw in conn.execute(f"SELECT * FROM {quoted_table}"):
                row = {str(k).lower(): v for k, v in dict(raw).items()}
                payload = row.get("record_json")
                if payload:
                    try:
                        embedded = json.loads(payload)
                        if isinstance(embedded, dict):
                            row = {**row, **{str(k).lower(): v for k, v in embedded.items()}}
                    except (TypeError, json.JSONDecodeError):
                        pass
                collection = str(row.get("collection_name") or table).lower()
                origin = str(row.get("origin_system") or "").lower()
                name = collection + " " + table.lower() + " " + origin
                mappings = [
                    (("tombstone", "deleted_customer_reference"), ("identity_service", "ACCOUNT_TOMBSTONE")),
                    (("customer_profile", "customer_account"), ("account_service", "USER_PROFILE")),
                    (("search",), ("search_service", "SEARCH_INDEX_ENTRY")),
                    (("analytics", "telemetry"), ("analytics_platform", "ANALYTICS_PROFILE")),
                    (("support_attachment", "attachment"), ("support_platform", "SUPPORT_ATTACHMENT")),
                    (("support", "conversation", "message"), ("support_platform", "SUPPORT_MESSAGE")),
                    (("export",), ("export_service", "USER_EXPORT")),
                    (("connector", "data_flow", "subscription"), ("integration_service", "DATA_FLOW")),
                    (("backup", "restore", "archive"), ("backup_service", "BACKUP_ARCHIVE")),
                    (("security", "audit", "retention"), ("security_service", "SECURITY_AUDIT_LOG")),
                    (("marketing",), ("marketing_platform", "MARKETING_PROFILE")),
                    (("cache",), ("cache_service", "CACHE_ENTRY")),
                ]
                system, category = next((pair for keys, pair in mappings if any(key in name for key in keys)), (origin or "unknown_service", "USER_PROFILE"))
                resource_id = _clean_str(row.get("resource_id"))
                if not resource_id:
                    continue
                id_keys = {
                    "user_id", "subject_reference", "subject_ref", "customer_reference", "owner_id",
                    "owner_user_id", "customer_id", "email", "owner_email", "customer_email",
                    "requester_email", "phone", "owner_phone", "requester_phone", "email_hash",
                }
                identifiers = {str(row[k]).strip() for k in id_keys if k in row and _clean_str(row[k])}
                has_direct = any(k in row and _clean_str(row[k]) for k in (
                    "email", "owner_email", "customer_email", "requester_email", "phone",
                    "owner_phone", "requester_phone", "email_hash", "full_name", "name",
                ))
                state = "PRESENT"
                if category == "ANALYTICS_PROFILE":
                    state = "PRESENT" if has_direct else "ANONYMIZED"
                elif category in {"SUPPORT_MESSAGE", "SUPPORT_ATTACHMENT", "EMAIL_DELIVERY_LOG", "ACCOUNT_TOMBSTONE"}:
                    state = "PRESENT" if has_direct else "REDACTED"
                elif category == "DATA_FLOW":
                    state = "ACTIVE" if _as_bool(row.get("enabled")) else "DISABLED"
                elif category == "BACKUP_ARCHIVE":
                    state = "ACTIVE" if _as_bool(row.get("restore_allowed")) else "BLOCKED"
                elif category == "SEARCH_INDEX_ENTRY":
                    state = "PRESENT"
                elif category == "USER_EXPORT":
                    state = "PRESENT" if _as_bool(row.get("download_available", True)) else "ABSENT"
                observed_at = _clean_str(row.get("updated_at") or row.get("captured_at") or row.get("indexed_at") or captured_at)
                normalized.append({
                    "evidence_id": evidence_id, "file_path": rel_path, "captured_at": captured_at,
                    "observed_at": observed_at, "system_id": system, "resource_id": resource_id,
                    "data_category": category, "state": state, "identifiers": identifiers,
                    "details": json.dumps(row, ensure_ascii=False, default=str),
                    "policy_facts": row,
                })
        return normalized
    finally:
        conn.close()

def _ocr_images(paths: List[str]) -> Dict[str, Dict[str, Any]]:
    """OCR images with local Tesseract first and optional text-only vision fallback."""
    if not paths:
        return {}
    from image_ocr import extract_text
    results: Dict[str, Dict[str, Any]] = {}
    for path in paths:
        results[path] = extract_text(path)
    return results

def _log_records(path: str, evidence_id: str, rel_path: str, captured_at: str) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    trace_context: Dict[str, Dict[str, str]] = {}
    attr_re = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(?:\"([^\"]*)\"|'([^']*)'|([^\s]+))")
    for line in open(path, "r", encoding="utf-8", errors="replace"):
        text = line.strip()
        attrs = {m.group(1).lower(): next(v for v in m.groups()[1:] if v is not None) for m in attr_re.finditer(text)}
        trace_id = attrs.get("trace_id", "")
        if trace_id:
            context = trace_context.setdefault(trace_id, {})
            for key, value in attrs.items():
                if key in {"lookup_key", "match_key", "subject_key", "subject_ref", "subject_reference", "correlation_key", "owner_key", "customer_reference", "user_id", "email", "phone", "email_hash", "customer_email", "matched_value"} and value:
                    context[key] = value
        else:
            context = {}
        # A query-start log may establish the identity context for a resource
        # revealed on the next line of the same trace. Retain trace context until
        # its resource result arrives.
        if "resource_id" not in attrs:
            continue
        res_id = attrs["resource_id"]
        raw_service = attrs.get("service", attrs.get("system", attrs.get("origin_system", "account_service"))).lower()
        service = next((canonical for token, canonical in (("support", "support_platform"), ("search", "search_service"), ("analytics", "analytics_platform"), ("backup", "backup_service"), ("restore", "backup_service"), ("integration", "integration_service"), ("connector", "integration_service"), ("export", "export_service"), ("security", "security_service"), ("marketing", "marketing_platform"), ("account", "account_service")) if token in raw_service), raw_service)
        event = attrs.get("event", attrs.get("event_type", "")).lower()
        merged = {**context, **attrs}
        id_keys = {"lookup_key", "match_key", "subject_key", "subject_ref", "subject_reference", "correlation_key", "owner_key", "customer_reference", "user_id", "email", "phone", "email_hash", "customer_email", "matched_value"}
        identifiers = {v.strip() for k, v in merged.items() if k in id_keys and v.strip() and v.strip().lower() not in {"null", "none", "anonymous"}}
        category, state = "USER_PROFILE", "PRESENT"
        if "search" in service:
            category = "SEARCH_INDEX_ENTRY"
            state = "PRESENT" if attrs.get("result", "").lower() in {"hit", "found", "present"} else "ABSENT" if attrs.get("result", "").lower() in {"miss", "not_found", "absent"} else "PRESENT"
        elif "support" in service or "attachment" in event:
            category = "SUPPORT_ATTACHMENT" if "attachment" in event or "attachment" in attrs.get("file", "").lower() else "SUPPORT_MESSAGE"
            state = "PRESENT" if attrs.get("matched_value") or attrs.get("rows") == "1" or "pii_scan" in event or attrs.get("marker_found", "").lower() == "false" else "REDACTED"
        elif "analytic" in service:
            category = "ANALYTICS_PROFILE"
            state = "PRESENT" if identifiers else "ANONYMIZED"
        elif "integration" in service or "connector" in event:
            category = "DATA_FLOW"
            state = "ACTIVE" if attrs.get("enabled", "").lower() in {"true", "1", "yes"} or "enabled=true" in text.lower() else "DISABLED"
        elif "backup" in service or "restore" in event:
            category = "BACKUP_ARCHIVE"
            state = "BLOCKED" if attrs.get("restore_allowed", "").lower() in {"false", "0", "no"} or attrs.get("deletion_block", "").lower() in {"true", "1", "yes"} else "ACTIVE"
        elif "export" in service:
            category = "USER_EXPORT"
            state = "PRESENT" if attrs.get("available", "").lower() in {"true", "1", "yes"} or "completed" in event else "PRESENT"
        elif "security" in service:
            category, state = "SECURITY_AUDIT_LOG", "PRESENT"
        elif "marketing" in service:
            category = "MARKETING_PROFILE"
            state = "PRESENT" if identifiers else "ABSENT"
        observed = re.match(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)", text)
        records.append({
            "evidence_id": evidence_id, "file_path": rel_path, "captured_at": captured_at,
            "observed_at": observed.group(1) if observed else captured_at,
            "system_id": service, "resource_id": res_id, "data_category": category,
            "state": state, "identifiers": identifiers, "details": text,
            "policy_facts": attrs,
        })
    return records

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
    image_rows = manifest_df[manifest_df["file_path"].astype(str).str.lower().str.endswith((".png", ".jpg", ".jpeg"))]
    image_full_paths = [os.path.join(DATASET_DIR, str(p)) for p in image_rows["file_path"].tolist()]
    image_texts = _ocr_images(image_full_paths)

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
                                for k in ["user_id", "subject_reference", "subject_ref", "customer_reference", "email", "owner_email", "customer_email", "phone", "owner_phone", "email_hash", "query"]:
                                    val = _clean_str(it.get(k))
                                    if val:
                                        id_set.add(val)
                                # Documents inside hits
                                if "hits" in it and isinstance(it["hits"], dict):
                                    for doc in it["hits"].get("documents", []):
                                        for k in ["user_id", "subject_reference", "email", "phone", "customer_reference", "display_name", "email_hash"]:
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
                                    "observed_at": _clean_str(it.get("updated_at") or it.get("last_checked_at") or it.get("checked_at") or it.get("indexed_at") or it.get("created_at") or captured_at),
                                    "system_id": svc,
                                    "resource_id": res_id,
                                    "data_category": cat,
                                    "state": state,
                                    "identifiers": id_set,
                                    "details": str(it),
                                    "policy_facts": it
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
                            for k in ["user_id", "subject_reference", "subject_ref", "customer_reference", "email", "phone", "email_hash", "name", "owner_email", "customer_email", "owner_phone", "requester_email", "requester_phone"]:
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
                                "observed_at": _clean_str(r.get("updated_at") or r.get("last_checked_at") or r.get("checked_at") or r.get("indexed_at") or captured_at),
                                "system_id": svc,
                                "resource_id": res_id,
                                "data_category": cat,
                                "state": state,
                                "identifiers": id_set,
                                "details": str(r),
                                "policy_facts": r
                            })

                # Format C: generic collection with records list
                elif "records" in data:
                    coll = data.get("collection") or data.get("origin") or ""
                    for r in data["records"]:
                        res_id = r.get("resource_id") or ""
                        if not res_id:
                            continue
                        id_set = set()
                        for k in ["user_id", "subject_reference", "subject_ref", "customer_reference", "email", "phone", "email_hash", "name", "owner_email", "customer_email", "owner_phone", "requester_email", "requester_phone"]:
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
                            "observed_at": _clean_str(r.get("updated_at") or r.get("last_checked_at") or r.get("checked_at") or r.get("indexed_at") or captured_at),
                            "system_id": svc,
                            "resource_id": res_id,
                            "data_category": cat,
                            "state": state,
                            "identifiers": id_set,
                            "details": str(r),
                            "policy_facts": r
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
                all_records.extend(_sql_records(full_path, eid, rel_path, captured_at))
            except (OSError, sqlite3.Error, UnicodeError) as exc:
                raise RuntimeError(f"Unable to parse SQL evidence {eid} ({rel_path}): {exc}") from exc

        # 4. Log files
        elif ext == ".log":
            all_records.extend(_log_records(full_path, eid, rel_path, captured_at))
            continue
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

        # 5. Image evidence is OCRed up front so identifiers can connect it to a subject.
        elif ext in (".png", ".jpg", ".jpeg"):
            ocr_result = image_texts.get(full_path, {})
            visual_text = str(ocr_result.get("text", ""))
            low = visual_text.lower()
            stem = os.path.basename(rel_path).lower()
            image_kinds = [
                ("search", "search_service", "SEARCH_INDEX_ENTRY"),
                ("analytics", "analytics_platform", "ANALYTICS_PROFILE"),
                ("backup", "backup_service", "BACKUP_ARCHIVE"),
                ("restore", "backup_service", "BACKUP_ARCHIVE"),
                ("connector", "integration_service", "DATA_FLOW"),
                ("marketing", "marketing_platform", "MARKETING_PROFILE"),
                ("support", "support_platform", "SUPPORT_MESSAGE"),
                ("security", "security_service", "SECURITY_AUDIT_LOG"),
                ("customer_export", "export_service", "USER_EXPORT"),
                ("deleted_account", "identity_service", "ACCOUNT_TOMBSTONE"),
                ("object_storage", "object_storage", "SUPPORT_ATTACHMENT"),
                ("account", "account_service", "USER_PROFILE"),
            ]
            system, category = next(((svc, cat) for key, svc, cat in image_kinds if key in stem), ("visual_evidence", "USER_PROFILE"))
            # Normalize common OCR spacing errors in typed resource identifiers.
            normalized_text = re.sub(r"\b(data_flow|audit_record|account|search|export|support|analytics|backup|connector|object|tombstone|marketing)\s+(\d+)\b", r"\1_\2", visual_text, flags=re.I)
            expected_prefix = {
                "USER_PROFILE": "account", "SEARCH_INDEX_ENTRY": "search", "ANALYTICS_PROFILE": "analytics",
                "BACKUP_ARCHIVE": "backup", "DATA_FLOW": "data_flow|connector", "MARKETING_PROFILE": "marketing",
                "USER_EXPORT": "export", "SUPPORT_MESSAGE": "support", "SUPPORT_ATTACHMENT": "object|support", "SECURITY_AUDIT_LOG": "audit_record",
                "ACCOUNT_TOMBSTONE": "user",
            }.get(category, "")
            resource_pattern = rf"\b(?:{expected_prefix})_\d+\b" if expected_prefix else r"\b(?:account|search|export|support|analytics|backup|connector|data_flow|audit_record|object|tombstone|marketing)_\d+\b"
            resources = list(dict.fromkeys(re.findall(resource_pattern, normalized_text, re.I)))
            user_ids = list(dict.fromkeys(re.findall(r"\buser_\d+\b", normalized_text, re.I)))
            emails = list(dict.fromkeys(re.findall(r"[A-Za-z0-9_.+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]+", visual_text)))
            hashes = list(dict.fromkeys(re.findall(r"\b[a-fA-F0-9]{40,64}\b", visual_text)))
            phone_candidates = list(dict.fromkeys(re.findall(r"\+\d[\d ().-]{7,}\d", visual_text)))
            identities = emails + user_ids + hashes + phone_candidates
            # A storage browser proves object existence, but its screenshot may not
            # display a subject email. Connect its filename to resource IDs grounded
            # by identity-linked activity during retrieval.
            if category == "SUPPORT_ATTACHMENT":
                object_matches = re.findall(r"delivery_confirmation_(\d+)\.pdf", low)
                resources.extend(f"object_{n}" for n in object_matches)
                resources = list(dict.fromkeys(resources))
            if category == "ACCOUNT_TOMBSTONE" and not resources:
                resources = user_ids[:1]
            visual_resources = resources or [f"visual_{eid}"]

            # Associate a resource only with identity tokens on the same visual row
            # (or a nearby line when OCR returns text without coordinates).
            tokens = ocr_result.get("tokens") or []
            token_resources = []
            for tok in tokens:
                word = str(tok.get("text", ""))
                center_y = tok["top"] + tok.get("height", 0) / 2
                match = re.search(resource_pattern, word, re.I) if expected_prefix else None
                if match:
                    token_resources.append((match.group(0).lower(), center_y))
            # Recover OCR-split identifiers such as `data_flow` + `9846` when
            # the prefix and numeric suffix share a visual row.
            prefix_names = expected_prefix.split("|") if expected_prefix else []
            for tok in tokens:
                word = str(tok.get("text", "")).lower().rstrip("_:")
                if word not in prefix_names:
                    continue
                cy = tok["top"] + tok.get("height", 0) / 2
                right = tok["left"] + tok.get("width", 0)
                candidates = [n for n in tokens if re.fullmatch(r"\d{2,8}", str(n.get("text", "")))
                              and abs((n["top"] + n.get("height", 0) / 2) - cy) <= 8
                              and 0 <= n["left"] - right <= 180]
                if candidates:
                    number = min(candidates, key=lambda n: n["left"] - right)
                    token_resources.append((f"{word}_{number['text']}", cy))
            resources = list(dict.fromkeys(resources + [rid for rid, _ in token_resources]))
            token_identities = []
            id_pattern = re.compile(r"(?:[A-Za-z0-9_.+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]+|user_\d+|\b[a-fA-F0-9]{40,64}\b|\+\d[\d ().-]{7,}\d)", re.I)
            for tok in tokens:
                for value in id_pattern.findall(str(tok.get("text", ""))):
                    token_identities.append((value, tok["top"] + tok.get("height", 0) / 2))
            state = "PRESENT"
            if category == "DATA_FLOW":
                state = "DISABLED" if re.search(r"disabled|inactive|stopped", low) else "ACTIVE"
            elif category == "BACKUP_ARCHIVE":
                state = "BLOCKED" if re.search(r"restore\s+(?:access\s+)?blocked|restore_allowed\s*[:=]\s*(?:false|no)", low) else "ACTIVE"
            elif category == "SEARCH_INDEX_ENTRY":
                state = "ABSENT" if re.search(r"no results|0 hits|not found|absent", low) else "PRESENT"
            elif category in {"ANALYTICS_PROFILE", "SUPPORT_MESSAGE", "ACCOUNT_TOMBSTONE"}:
                direct_pii = bool(emails or hashes or phone_candidates)
                if category == "ACCOUNT_TOMBSTONE":
                    direct_pii = direct_pii or bool(re.search(r"(?:full[_ ]name|customer name)\s*[:=]", low))
                    state = "PRESENT" if direct_pii else "REDACTED"
                elif category == "ANALYTICS_PROFILE":
                    state = "PRESENT" if direct_pii or user_ids else "ANONYMIZED"
                else:
                    state = "PRESENT" if direct_pii or re.search(r"support_\d+.{0,60}[A-Z][a-z]+\s+[A-Z][a-z]+", visual_text) else "REDACTED"
            elif category == "USER_PROFILE":
                state = "ABSENT" if re.search(r"deleted|not found|no profile|account absent", low) else "PRESENT"
            for resource_id in visual_resources:
                row_ids = set()
                if tokens and resource_id != f"visual_{eid}":
                    positions = [y for rid, y in token_resources if rid == resource_id.lower()]
                    if resource_id.startswith("user_"):
                        positions.extend(y for value, y in token_identities if value.lower() == resource_id.lower())
                    if positions:
                        for identity_value, identity_y in token_identities:
                            # Keep one nearest value of each identifier type per
                            # resource row to avoid joining neighboring table rows.
                            same_type = [v for v, _ in token_identities if
                                         ("@" in v) == ("@" in identity_value) and
                                         v.startswith("user_") == identity_value.startswith("user_")]
                            if not same_type:
                                continue
                            distance = min(abs(identity_y - resource_y) for resource_y in positions)
                            closest = min(abs(y - resource_y) for v, y in token_identities if v in same_type for resource_y in positions)
                            if distance == closest and distance <= 180:
                                row_ids.add(identity_value)
                elif resource_id != f"visual_{eid}":
                    # The OpenAI OCR path returns faithful text without bounding
                    # boxes. Associate identifiers only on or near the matching
                    # resource line, never every identifier on a multi-row page.
                    text_lines = visual_text.splitlines()
                    id_regex = re.compile(r"[A-Za-z0-9_.+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]+|user_\d+|\b[a-fA-F0-9]{40,64}\b|\+\d[\d ().-]{7,}\d", re.I)
                    matching_lines = [i for i, line in enumerate(text_lines)
                                      if re.search(re.escape(resource_id).replace("_", r"[_ ]+"), line, re.I)]
                    for line_no in matching_lines:
                        for nearby in text_lines[max(0, line_no - 2):line_no + 3]:
                            row_ids.update(id_regex.findall(nearby))
                elif len(visual_resources) == 1:
                    row_ids.update(identities)
                all_records.append({
                    "evidence_id": eid, "file_path": rel_path, "captured_at": captured_at,
                    "observed_at": captured_at, "system_id": system,
                    "resource_id": resource_id, "data_category": category, "state": state,
                    "identifiers": row_ids, "details": visual_text or "IMAGE_CONTENT_UNVERIFIED: OCR unavailable; inspect source artifact",
                    "policy_facts": {
                        "ocr_verified": bool(visual_text), "content_unverified": not bool(visual_text),
                        "ocr_source": ocr_result.get("source", "unavailable"),
                        "ocr_confidence": ocr_result.get("confidence"),
                    },
                })

        # 6. PDF documents
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
