# ARCHITECTURE.md — Ghost Data Deletion Audit Agent

## 1. Purpose (one sentence)
For every row in `dataset/deletion_requests.csv`, determine the TRUE deletion state of a user's data across all systems (not the claimed state), and emit `output.csv` with `case_id, deletion_status, steps_json` exactly matching the grader's schema.

## 2. High-level data flow

```
dataset/*.csv  +  dataset/evidence/*  (pdf, image, json, log, sqlite)
        │
        ▼
 STAGE 1  — Ingestion Layer
        │   loads all CSVs into memory/DB tables, parses evidence_files.csv manifest
        ▼
 STAGE 2  — Identity Resolution Layer
        │   per case: build full identifier set (current + historical: email, email_hash, phone, user_id)
        ▼
 STAGE 3  — Request Classification Layer
        │   decide: is this a real deletion request? full or partial scope? → may short-circuit to NOT_APPLICABLE
        ▼
 STAGE 4  — Evidence Retrieval Layer
        │   pull every evidence_files row + system_activity row that matches ANY identifier in the set, timestamp ≤ audit_at
        ▼
 STAGE 5  — Evidence Extraction Layer
        │   structured files (json/log/sqlite) parsed directly (deterministic code)
        │   unstructured files (pdf/image) parsed via VLM into structured facts
        ▼
 STAGE 6  — State Reconstruction Layer
        │   per (system_id, resource_id): build timeline from system_activity, resolve state AT audit_at
        ▼
 STAGE 7  — Policy Engine
        │   apply deletion_rules.csv to every record → classify each as OK / PROBLEM(type) / CORRECTLY_RETAINED
        ▼
 STAGE 8  — Status Decision Layer
        │   roll up all record classifications → COMPLETE / INCOMPLETE / NOT_APPLICABLE
        ▼
 STAGE 9  — Step Generation Layer
        │   build FINDING steps → (if INCOMPLETE) REMEDIATION steps → VERIFICATION steps
        ▼
 STAGE 10 — Deterministic Ordering & Renumbering Layer
        │   enforce phase order, operation-priority table, system_id/resource_id ascending, step_no 1..N
        ▼
 STAGE 11 — Schema Validation Layer
        │   enum checks, evidence_id rules, JSON validity, row count, sort order
        ▼
   output.csv (exactly 518 rows, sorted by case_id)
```

## 3. Module-to-file mapping (code/ layout)

```
code/
├── main.py                  # entry point — orchestrates Stage 1 to 11, writes output.csv
├── README.md                # how to install + run (required by HackerRank submission rules)
├── config.py                # file paths, model names, constants (operation-priority table lives here)
├── ingest.py                 # STAGE 1
├── identity_resolver.py      # STAGE 2
├── request_classifier.py     # STAGE 3
├── evidence_retrieval.py     # STAGE 4
├── evidence_extraction.py    # STAGE 5 (includes vlm_client.py calls for images/pdf)
├── vlm_client.py              # wraps LLM/VLM API calls, used only inside Stage 5
├── state_reconstruction.py   # STAGE 6
├── policy_engine.py          # STAGE 7 (loads + applies deletion_rules.csv)
├── status_decision.py        # STAGE 8
├── step_generator.py         # STAGE 9
├── ordering.py                # STAGE 10 (pure deterministic, NO LLM calls allowed here)
├── validator.py               # STAGE 11
├── schema_dump.py             # one-off utility: prints real column names of every dataset CSV
└── evaluation/
    ├── run_eval.py             # runs pipeline on sample_deletion_requests.csv, diffs vs sample_output.csv
    ├── custom_cases.py         # 3+ hand-built adversarial test cases (see DESIGN.md §7)
    ├── evaluation_report.md    # REQUIRED deliverable — written after run_eval.py executes
    └── usage_report.md         # REQUIRED deliverable — token/cost log from the final full run
```

## 4. Hard separation rule: LLM vs deterministic code

This is the single most important architectural rule. Violating it is the most common way these submissions lose points on sequence accuracy and schema accuracy.

| Layer | Uses LLM/VLM? | Why |
|---|---|---|
| Stage 1 Ingestion | No | Pure CSV parsing |
| Stage 2 Identity Resolution | No | Table joins, deterministic |
| Stage 3 Request Classification | Yes (small, cheap call) | `request_text` is free-form natural language |
| Stage 4 Evidence Retrieval | No | Filter/join operation |
| Stage 5 Evidence Extraction | Yes, only for images/PDF/scanned docs. No for JSON/log/SQLite — those are parsed directly | VLM needed only where data is unstructured/visual |
| Stage 6 State Reconstruction | No | Timeline logic over timestamps, pure code |
| Stage 7 Policy Engine | No | `deletion_rules.csv` lookup table, pure code |
| Stage 8 Status Decision | No | Boolean roll-up of Stage 7 output |
| Stage 9 Step Generation | No (template-driven from Stage 7/8 output) | Steps are derived mechanically from findings, not invented by a model |
| Stage 10 Ordering | No | Must be 100% deterministic — grader checks exact array order |
| Stage 11 Validation | No | Pure assertions |

**Rule for the coding agent: never let an LLM call decide step ordering, enum values, or JSON structure. LLM calls only ever produce raw extracted facts or a classification label, which then gets handed to deterministic code.**

## 5. External dependencies

- CSV/DataFrame library (pandas or equivalent)
- SQLite reader (stdlib `sqlite3` or equivalent) for `.sql`/`.sqlite` evidence
- PDF text extraction library
- Image/VLM API client (Anthropic/OpenAI/Gemini — whichever is configured)
- JSON stdlib

No network calls anywhere except the LLM/VLM API client. Everything else reads local files only.

## 6. Non-functional requirements carried from the problem statement

- Must produce exactly 518 output rows, sorted by `case_id`
- Must not hardcode any case-specific answer
- Must log every model call (for `usage_report.md`)
- Must log every coding-agent conversation turn to `log.txt` (handled by AGENTS.md, not by this code — see AGENT_INSTRUCTIONS.md)
- `code.zip` excludes venv/node_modules/build artifacts/`data/`/`dataset/`

See DESIGN.md for exact logic per stage and DECISIONS.md for why each architectural choice was made.
