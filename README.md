# Landscaping & Mowing Streamlit App 🌿 (v3)

This is a **full Streamlit web app** for managing landscaping & mowing services
across multiple properties, including:

- Admin dashboard with per-property costs & frequencies
- Central **Price Master** (Frisco-based suggested rates)
- Per-property service schedules
- **Service status updates** (Scheduled / In Progress / Completed / On Hold / Cancelled)
- **Email + SMS notifications** to property owners when status changes
- **Attachments** per service (images, with size limit)
- Ticketing module so property owners can raise requests
- Excel export per property (for both admin and owners)
- **Gemini-powered chat window** that is grounded in DB data (simple RAG)

Designed so you can deploy directly to **Streamlit Cloud**.

---

## 1. Project Structure

```text
landscaping_streamlit_app/
├── app.py                 # Main Streamlit app (UI + routing)
├── db.py                  # SQLite database models & helpers
├── requirements.txt       # Python dependencies
├── README.md              # This file
└── .streamlit/
    └── config.toml        # Optional Streamlit theming
```

A SQLite DB file will be created automatically at:

```text
data/app.db
```

on first run.

> 💡 If you used an older version of this app, the code includes a small
> schema migration to add new columns (status, phone, etc.). In case of
> any migration issues during development, you can delete `data/app.db`
> and let it recreate from scratch.

---

## 2. Local Setup

1. Create and activate a virtual environment:

```bash
cd landscaping_streamlit_app
python -m venv .venv
# Windows:
#   .venv\Scripts\activate
# macOS / Linux:
#   source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. (Optional but recommended) Set your **Gemini API key** as an environment variable:

```bash
# macOS / Linux
export GOOGLE_API_KEY="your-key-here"

# Windows CMD
set GOOGLE_API_KEY="your-key-here"
```

4. Run the app:

```bash
streamlit run app.py
```

---

## 3. Default Demo Logins

> You can change these later directly in the SQLite DB if you want.

- **Admin**
  - Username: `admin`
  - Password: `admin123`

- **Property Owner 1**
  - Username: `owner1`
  - Password: `owner123`
  - Phone (for demo): `+15550000001`

- **Property Owner 2**
  - Username: `owner2`
  - Password: `owner123`
  - Phone (for demo): `+15550000002`

When you log in:

- **Admin** sees:
  - 📊 Admin Dashboard
  - 🏠 Manage Properties & Services
  - 💰 Price Master
  - 🎫 Tickets (all properties)

- **Owners** see:
  - 📊 My Property Dashboard
  - 🎫 My Tickets (only their property)

---

## 4. Service Status, Notifications & Attachments

### 4.1 Status per Service

In **Admin → Manage Properties & Services**:

- You see a table of all services for the selected property, including a **Status** column.
- Below the table, there is a section:
  - **“✏️ Update Service Status & Attachments”**

Steps:

1. Select a service (e.g., `Mowing / Bi-weekly (id=1)`).
2. Choose a new status:
   - `Scheduled`
   - `In Progress`
   - `Completed`
   - `On Hold`
   - `Cancelled`
3. Optionally tick:
   - “Send email to owner(s)”
   - “Send SMS to owner(s) (if configured)”
4. Optionally upload **images** (JPG/PNG, max 3 MB each).
5. Click **“Save status & attachments”**.

The app will:

- Update the status in the DB
- Save any valid images under `uploads/property_<id>/service_<id>/`
- Insert metadata in `service_attachments`
- Send email and/or SMS to all owners mapped to that property (if configured)
- Reflect the status change in both **Admin** and **Owner** dashboards

### 4.2 Viewing Attachments

- **Admin → Manage Properties & Services**
  - Section **“📎 Attachments by Service”** shows expanders per service, with thumbnails.

- **Owner → My Property Dashboard**
  - Same **“📎 Attachments by Service”** section, read-only for owners.

This is ideal for before/after photos, proof of work, inspection screenshots, etc.

> Note: For production use, you may want to move these files to cloud storage
> (e.g., S3 or Azure Blob) instead of local `uploads/` folder.

---

## 5. Email & SMS Configuration

### 5.1 Email (SMTP)

The app uses standard Python `smtplib`. Add the following to **Streamlit Cloud secrets**
(or as environment variables locally):

```toml
SMTP_HOST = "smtp.yourprovider.com"
SMTP_PORT = "587"
SMTP_USERNAME = "your-smtp-username"
SMTP_PASSWORD = "your-smtp-password"
SMTP_FROM = "no-reply@yourdomain.com"
SMTP_USE_TLS = "true"
```

When admin updates a service and chooses **“Send email to owner(s)”**, each owner
with a non-empty `email` will receive an email.

### 5.2 SMS (Twilio, optional)

Install is already handled via `requirements.txt` (`twilio` library).  
Add the following to **secrets** or env:

```toml
TWILIO_ACCOUNT_SID = "your-account-sid"
TWILIO_AUTH_TOKEN  = "your-auth-token"
TWILIO_FROM_NUMBER = "+1XXXXXXXXXX"
```

When admin updates a service and chooses **“Send SMS to owner(s)”**, each owner
with a non-empty `phone` (e.g., `+15550000001`) will receive an SMS.

> If these values are not configured, the app will skip sending and return a friendly message.

---

## 6. Excel Export

Both **Admin** and **Owners** can download an Excel snapshot
for a single property from their dashboards.

The Excel file contains:

- `Summary` sheet — property details, total services, total annual cost
- `Services` sheet — all services for that property with:
  - Category, Frequency
  - No. of Times
  - Each Time Cost
  - Total Cost
  - Status

---

## 7. Gemini Chat (RAG style)

The app contains a **chat window** on:

- Admin Dashboard
- Owner Property Dashboard

The chat:

- Uses the `google-generativeai` client to call **Gemini**.
- Constructs a prompt that includes **live data** from the SQLite DB:
  - For admin: all properties, total services, total costs, frequency summary.
  - For owners: their own property details, services, and costs.
- Asks Gemini to answer **based primarily on this structured data**.
- If no `GOOGLE_API_KEY` is configured, the chat will show a friendly warning
  instead of failing.

To make it work in production:

1. Get a Gemini API key from Google AI Studio.
2. Either:
   - Add `GOOGLE_API_KEY` as an environment variable (local), or
   - Add `GOOGLE_API_KEY` to **Streamlit Cloud secrets**.

---

## 8. Streamlit Cloud Deployment

1. Push this folder to a GitHub repo.
2. On Streamlit Community Cloud:
   - Create new app → point to `app.py`.
   - `requirements.txt` will be used automatically.
   - Configure **secrets** for:
     - `GOOGLE_API_KEY`
     - SMTP settings (if you want email)
     - Twilio settings (if you want SMS)
3. Deploy – Streamlit will:
   - Create the virtualenv
   - Install dependencies
   - Run `app.py`

The SQLite DB (`data/app.db`) will be created in the app’s filesystem.
For long-term persistence you can later move to a hosted DB (e.g., Postgres).

---

## 9. Where to Extend

Some ideas to further turn this into a production-grade tool:

- Replace simple username/password with SSO (Google, Azure AD, etc.).
- Move from SQLite to Postgres or MySQL.
- Add editing & deletion for existing services and price master rows.
- Add per-ticket attachments (images/ PDFs) in the ticket module.
- Export consolidated reports to Excel/PDF for monthly billing.
- Extend the Gemini chat to answer “what-if” scenarios and optimization tips.

For now, this template gives you a **clean, fully working base product** that you
can iterate on quickly.

Enjoy building! 🌱
