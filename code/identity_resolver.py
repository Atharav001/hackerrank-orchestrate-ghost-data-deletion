import os
import pandas as pd
from typing import Dict, Any, Set
from ingest import load_user_identities, load_user_audit_log

# Cached dataframes
_UIDS_DF = None
_AUDIT_DF = None

def get_dataframes():
    global _UIDS_DF, _AUDIT_DF
    if _UIDS_DF is None:
        _UIDS_DF = load_user_identities()
    if _AUDIT_DF is None:
        _AUDIT_DF = load_user_audit_log()
    return _UIDS_DF, _AUDIT_DF

def resolve_identity(email: str, uids_df: pd.DataFrame = None, audit_df: pd.DataFrame = None, audit_at: str = None) -> Dict[str, Any]:
    """
    Stage 2 — Identity Resolution algorithm:
    1. Look up email in user_identities.csv (case-insensitive).
       If found, retrieve current user_id and all current fields.
    2. If not found, look up email in user_audit_log.csv (case-insensitive)
       to discover the user_id from historical events.
    3. Retrieve all historical identifier changes from user_audit_log for this user_id.
    4. Build complete identifier set partitioned into CURRENT and HISTORICAL.
    """
    if uids_df is None or audit_df is None:
        u_df, a_df = get_dataframes()
        if uids_df is None:
            uids_df = u_df
        if audit_df is None:
            audit_df = a_df

    email_clean = email.strip()
    email_lower = email_clean.lower()

    user_id = None
    current_identity = {}
    historical_events = []

    # Step 1: Look up in user_identities (case-insensitive)
    match_cur = uids_df[uids_df['email'].str.lower() == email_lower]
    if len(match_cur) > 0:
        row = match_cur.iloc[0]
        user_id = row['user_id']
        current_identity = {
            'user_id': row['user_id'],
            'name': str(row['name']) if pd.notna(row['name']) else '',
            'email': str(row['email']) if pd.notna(row['email']) else '',
            'phone': str(row['phone']) if pd.notna(row['phone']) else '',
            'email_hash': str(row['email_hash']) if pd.notna(row['email_hash']) else '',
            'updated_at': str(row['updated_at']) if pd.notna(row['updated_at']) else ''
        }
    else:
        # Step 2: Check audit log old_value / new_value
        match_audit = audit_df[
            (audit_df['field_name'] == 'email') &
            ((audit_df['old_value'].str.lower() == email_lower) | (audit_df['new_value'].str.lower() == email_lower))
        ]
        if len(match_audit) > 0:
            user_id = match_audit.iloc[0]['user_id']
            # User might still exist in user_identities by user_id
            match_uid = uids_df[uids_df['user_id'] == user_id]
            if len(match_uid) > 0:
                row = match_uid.iloc[0]
                current_identity = {
                    'user_id': row['user_id'],
                    'name': str(row['name']) if pd.notna(row['name']) else '',
                    'email': str(row['email']) if pd.notna(row['email']) else '',
                    'phone': str(row['phone']) if pd.notna(row['phone']) else '',
                    'email_hash': str(row['email_hash']) if pd.notna(row['email_hash']) else '',
                    'updated_at': str(row['updated_at']) if pd.notna(row['updated_at']) else ''
                }
            else:
                current_identity = {
                    'user_id': user_id,
                    'name': '',
                    'email': email_clean,
                    'phone': '',
                    'email_hash': '',
                    'updated_at': ''
                }

    # Step 3: Collect all historical records from user_audit_log for this user_id
    if user_id:
        audit_rows = audit_df[audit_df['user_id'] == user_id].sort_values(by='event_time')
        for _, a_row in audit_rows.iterrows():
            historical_events.append({
                'audit_id': str(a_row['audit_id']),
                'user_id': str(a_row['user_id']),
                'event_time': str(a_row['event_time']),
                'field_name': str(a_row['field_name']),
                'old_value': str(a_row['old_value']) if pd.notna(a_row['old_value']) else '',
                'new_value': str(a_row['new_value']) if pd.notna(a_row['new_value']) else ''
            })

    # Step 4: Build typed identifier sets
    all_emails: Set[str] = set()
    all_phones: Set[str] = set()
    all_hashes: Set[str] = set()
    all_names: Set[str] = set()
    all_user_ids: Set[str] = set()

    if user_id:
        all_user_ids.add(user_id)
    if current_identity.get('email'):
        all_emails.add(current_identity['email'])
    if email_clean:
        all_emails.add(email_clean)
    if current_identity.get('phone'):
        all_phones.add(current_identity['phone'])
    if current_identity.get('email_hash'):
        all_hashes.add(current_identity['email_hash'])
    if current_identity.get('name'):
        all_names.add(current_identity['name'])

    for ev in historical_events:
        fn = ev['field_name']
        for val in [ev['old_value'], ev['new_value']]:
            if not val:
                continue
            if fn == 'email':
                all_emails.add(val)
            elif fn == 'phone':
                all_phones.add(val)
            elif fn == 'email_hash':
                all_hashes.add(val)

    # Build a second identity set from history known by the case cutoff.
    eligible_events = [ev for ev in historical_events if not audit_at or ev["event_time"] <= audit_at]
    asof = {"user_ids": sorted({user_id} if user_id else set()), "emails": set(), "phones": set(), "email_hashes": set()}
    if current_identity.get("updated_at") and (not audit_at or current_identity["updated_at"] <= audit_at):
        for key, value in (("emails", current_identity.get("email")), ("phones", current_identity.get("phone")), ("email_hashes", current_identity.get("email_hash"))):
            if value: asof[key].add(value)
    asof["emails"].add(email_clean)
    for ev in eligible_events:
        key = {"email": "emails", "phone": "phones", "email_hash": "email_hashes"}.get(ev["field_name"])
        if key:
            for value in (ev["old_value"], ev["new_value"]):
                if value: asof[key].add(value)
    asof = {key: sorted(value) for key, value in asof.items()}

    # All non-empty literal values that identify this user
    all_values: Set[str] = set()
    for s in [all_user_ids, all_emails, all_phones, all_hashes, all_names]:
        all_values.update(s)

    audit_cutoff = None
    # Caller may attach an audit cutoff; otherwise preserve all identifiers for
    # existing callers and the per-case pipeline supplies a cutoff below.
    return {
        'user_id': user_id,
        'current': current_identity,
        'historical': historical_events,
        'identifiers_as_of_audit': asof,
        'all_identifiers': {
            'user_ids': sorted(list(all_user_ids)),
            'emails': sorted(list(all_emails)),
            'phones': sorted(list(all_phones)),
            'email_hashes': sorted(list(all_hashes)),
            'names': sorted(list(all_names))
        },
        'all_values': sorted(list(all_values))
    }

def test_identity_resolver():
    from ingest import load_sample_deletion_requests
    samples = load_sample_deletion_requests()
    
    # Test case 1: direct current match (case_01)
    res_01 = resolve_identity("amina.elmasri@gmail.com")
    assert res_01['user_id'] == 'user_01'
    assert 'amina.elmasri@gmail.com' in res_01['all_identifiers']['emails']
    
    # Test case 2: historical email match (case_10: nadia.ionescu@yahoo.com)
    res_10 = resolve_identity("nadia.ionescu@yahoo.com")
    assert res_10['user_id'] == 'user_10'
    assert 'nadia.ionescu@yahoo.com' in res_10['all_identifiers']['emails']
    assert 'n.petrescu@yahoo.com' in res_10['all_identifiers']['emails']
    assert len(res_10['historical']) >= 1
    
    # Test case 3: uppercase email match (case_38: SIPHO.MOKOENA@GMAIL.COM)
    res_38 = resolve_identity("SIPHO.MOKOENA@GMAIL.COM")
    assert res_38['user_id'] is not None
    assert 'sipho.mokoena@gmail.com' in [e.lower() for e in res_38['all_identifiers']['emails']]
    
    print("All identity resolver tests passed successfully!")

if __name__ == "__main__":
    test_identity_resolver()
