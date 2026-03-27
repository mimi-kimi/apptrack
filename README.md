# 💰 Money Tracker — Cloud Edition · Setup Guide

## Stack Overview

```
streamlit-authenticator  →  Login (credentials in st.secrets)
         ↓
Firestore                →  Stores sheet_id per user + custom categories
         ↓
gspread (Google Sheets)  →  Stores all transactions (one tab = one track)
         ↓
Plotly                   →  Grouped bar chart: Ideal vs Actual 50/30/20
```

---

## Prerequisites

- Python 3.10+
- A Google account
- A Google Cloud project (free tier is fine)

---

## Step 1 — Install dependencies

```bash
pip install -r requirements.txt
```

---

## Step 2 — Set up Google Cloud

### 2a. Enable APIs
In the [Google Cloud Console](https://console.cloud.google.com):

1. Go to **APIs & Services → Library**
2. Enable **Cloud Firestore API**
3. Enable **Google Sheets API**
4. Enable **Google Drive API**

### 2b. Create a Firestore database
1. Go to **Firestore → Create Database**
2. Choose **Native mode**
3. Pick any region (e.g. `us-central`)

### 2c. Create a Service Account
1. Go to **IAM & Admin → Service Accounts → Create Service Account**
2. Name it e.g. `money-tracker-sa`
3. Grant it the role **Cloud Datastore User** (for Firestore)
4. Click **Done**
5. Open the service account → **Keys → Add Key → JSON**
6. Download the JSON file — you'll paste its fields into `secrets.toml`

---

## Step 3 — Hash passwords

Run this once in a Python shell to generate bcrypt hashes for each user:

```python
import streamlit_authenticator as stauth

# Replace with your actual plaintext passwords
hashed = stauth.Hasher(["alice_password", "bob_password"]).generate()
print(hashed)
# ['$2b$12$...', '$2b$12$...']
```

Copy each hash into the corresponding `[auth.credentials.usernames.X]` block in `secrets.toml`.

---

## Step 4 — Configure secrets

```bash
mkdir -p .streamlit
cp secrets.toml.template .streamlit/secrets.toml
```

Edit `.streamlit/secrets.toml`:

| Field | Where to find it |
|---|---|
| `cookie_key` | Any random 32-char string (e.g. run `python -c "import secrets; print(secrets.token_hex(16))"`) |
| `[auth.credentials.usernames.*]` | Fill in names, emails, hashed passwords from Step 3 |
| `[gcp_service_account]` | Copy every field from the downloaded service-account JSON |

> ⚠️ **Never commit `.streamlit/secrets.toml` to Git.**
> Add it to `.gitignore` immediately.

```bash
echo ".streamlit/secrets.toml" >> .gitignore
```

---

## Step 5 — Share the Google Sheet with the service account

Each user needs a Google Sheet to store their transactions.

1. Create a new Google Sheet (or use an existing one)
2. Copy the **Sheet ID** from the URL:
   `docs.google.com/spreadsheets/d/**SHEET_ID**/edit`
3. Click **Share** and add the service account email
   (`your-sa@your-project.iam.gserviceaccount.com`) as an **Editor**

The app will ask each user to paste their Sheet ID on first login.

---

## Step 6 — Run the app

```bash
streamlit run app.py
```

Open `http://localhost:8501` in your browser.

---

## Firestore Data Model

```
users/
  {username}/
    email:      "alice@example.com"
    sheet_id:   "1BxiMVs0XRA5nFMd..."
    updated_at: <timestamp>

    meta/
      categories/
        Needs:   ["Rent", "Groceries", ...]
        Wants:   ["Dining Out", ...]
        Savings: ["Emergency Fund", ...]
```

---

## Google Sheet Structure

Each **tab** = one track (e.g. "March 2026").
Each tab has this header row (auto-created by the app):

| date | sheet_name | type | bucket | category | amount | note |
|---|---|---|---|---|---|---|
| 2026-03-01 14:22 | March 2026 | Expense | Needs | Rent | 1200 | Monthly rent |

---

## Deploying to Streamlit Cloud

1. Push your repo to GitHub (make sure `secrets.toml` is in `.gitignore`)
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your repo → set `app.py` as the entrypoint
4. Go to **Settings → Secrets** and paste the full contents of your `secrets.toml`

---

## Troubleshooting

| Error | Fix |
|---|---|
| `google.auth.exceptions.DefaultCredentialsError` | Check all fields in `[gcp_service_account]` in secrets.toml |
| `gspread.exceptions.SpreadsheetNotFound` | Verify the Sheet ID and that the service account is an Editor |
| `KeyError: 'auth'` | Make sure `secrets.toml` is in the `.streamlit/` folder |
| `StreamlitAuthenticator` cookie errors | Ensure `cookie_key` is at least 16 characters |
| Firestore permission denied | Ensure the service account has **Cloud Datastore User** role |
