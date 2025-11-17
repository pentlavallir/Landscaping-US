### Quick orientation

This repository is a small Streamlit app for managing landscaping services (admin + property owners). Primary files:
- `app.py` — lightweight POC UI, uses plaintext passwords and simple Gemini placeholder.
- `app_with_evt_nav.py` — richer, production-like UI: hashed passwords, scheduling, RAG chat, email/SMS helpers.
- `db.py` — single SQLite-backed data layer, schema creation, seeds and helpers.

Always start by running `streamlit` locally (see examples below) and inspect `data/app.db` after `db.init_db()` runs.

**Why things are structured this way**
- UI and app logic are colocated in the Streamlit files (`app*.py`) for simplicity.
- `db.py` centralizes schema creation, migrations, seed data and the query API; other modules call `db.*` functions rather than raw SQL.
- Attachments are stored on disk under `uploads/` and metadata is kept in SQLite (`service_attachments`, `ticket_attachments`).

### Developer workflows (concrete)
- Install deps and run (PowerShell):
```
python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt
streamlit run app_with_evt_nav.py
```
- Lightweight run (no venv):
```
pip install -r requirements.txt; streamlit run app.py
```
- Reset DB / reseed (dev): delete `data/app.db` and restart the app — `db.init_db()` will recreate tables and seed demo data.

### Config & secrets (explicit names)
- Gemini / Google API Key:
  - Preferred: `st.secrets['gemini']['api_key']` (app_with_evt_nav.py checks this first)
  - Fallback env var: `GOOGLE_API_KEY`
  - PowerShell example: `$env:GOOGLE_API_KEY = 'your-key'`
- SMTP (for email): `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, optional `SMTP_USE_TLS`
- Twilio (for SMS): `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`

### Important patterns & conventions (project-specific)
- Database: use `db.get_connection()` -> `db.*` helper functions. Prefer helpers like `db.add_service_event(...)`, `db.get_service_by_id(...)` instead of raw SQL.
- Passwords: `app_with_evt_nav.py` uses `db.hash_password`/`db.verify_password`. `app.py` has a plaintext-login helper for the POC — prefer the hashed flow when modifying auth.
- Attachments: saved under `uploads/property_<id>/service_<id>/` or `uploads/ticket_<id>/` and registered via `db.add_service_attachment` / `db.add_ticket_attachment`.
- Excel exports: `generate_property_excel()` and `generate_consolidated_excel()` produce in-memory `BytesIO` and are wired to Streamlit `download_button` controls.
- RAG / Gemini chat:
  - `build_chat_context(user)` assembles structured DB-derived context which is concatenated with user prompts and passed to `call_gemini_backend(...)`.
  - If `GOOGLE_API_KEY` / secrets are not set, the chat returns a friendly warning string.

### Files to edit for common tasks
- Add new DB helpers: `db.py` (follow existing return types — usually list of dicts or sqlite rows).
- Change seeding: `seed_properties`, `seed_price_master`, `seed_property_services_and_users` inside `db.py`.
- Add notifications: edit `send_email_notification` / `send_sms_notification` in `app_with_evt_nav.py` (they already read secrets via `_get_secret`).
- Switch storage to cloud: update upload/save paths in `app_with_evt_nav.py` and `app.py` (search for `uploads/` and `add_service_attachment` calls).

### Tests & checks (manual)
- Smoke test after changes: run `streamlit run app_with_evt_nav.py` and:
  - Login as `admin` / `admin123` (seeded in `db.py`).
  - Create property/service, schedule an event, change status, attach an image.
  - Verify `uploads/` path contains files and DB tables `service_attachments` / `ticket_attachments` have entries.

### Quick examples (copy-paste)
- Get a property's summary from Python REPL:
```py
from db import init_db, get_property_summary
init_db()
print(get_property_summary(1))
```
- Send a test email (PowerShell env + run Streamlit action): set SMTP_* secrets in Streamlit Cloud or locally via PowerShell before starting Streamlit.

### Known quirks / gotchas
- Two app entrypoints exist: `app.py` (simple) and `app_with_evt_nav.py` (recommended). Use the latter for the full feature set.
- `app.py` uses plaintext password checks for quick demos — do not add real accounts relying on it in production.
- DB migrations are handled in-place by `db._upgrade_schema` (it uses `ALTER TABLE ADD COLUMN` where safe). For complex migrations, prefer exporting data and recreating schema.

If anything is unclear or you'd like me to include more code examples (e.g., common db function signatures, sample st.secrets config snippet, or a specific developer checklist), tell me which sections to expand.
