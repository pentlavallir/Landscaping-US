
Landscaping & Mowing Manager – Quote Builder Edition
====================================================

How to run locally
------------------

1. Create and activate a virtual environment:

   Windows (PowerShell):

       python -m venv .venv
       .venv\Scripts\activate

   macOS / Linux:

       python -m venv .venv
       source .venv/bin/activate

2. Install dependencies:

       pip install -r requirements.txt

3. (Optional) Configure Gemini API key for AI chat:

   Create a `.streamlit/secrets.toml` file with:

       GEMINI_API_KEY = "your-real-gemini-api-key-here"

   Or set an environment variable:

       set GEMINI_API_KEY=your-real-gemini-api-key-here    # Windows
       export GEMINI_API_KEY=your-real-gemini-api-key-here # macOS / Linux

4. Run the app:

       streamlit run app.py

5. Logins:

   - Admin:  username `admin`, password `admin123`
   - Owners: username `owner1` .. `owner10`, password `owner123`

This version includes:

- Admin dashboard with portfolio metrics, module health, fulfilment overview, and Gemini chat.
- Full property & services management with per-service fulfilment and Excel export.
- Event scheduler for service activities.
- Price master and service personnel directories.
- Ticketing for owner communication with attachments.
- Owner dashboard + tickets.
- New **Quote Builder** module:

  - Region-based rate selection (TX / Frisco / Small Industrial seeded).
  - Standard package services:
    * Weed Control Spraying (3x/year)
    * Mowing (22 visits)
    * Blowing & Trash Cleanup (22 visits)
    * Fertilizer (5x/year)
    * Tree & Shrub Care (2x/year)
    * Mulch (2x/year, every 6 months)
  - Editable times/year & price/visit for each line.
  - Automatic annual, monthly, and estimated margin calculation.
