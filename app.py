# =============================================================================
#  💰 Money Tracker — Cloud Edition
#  No login — Sheet ID pasted once per session identifies the user
#  User data: Firestore (stores sheet_id per user)
#  Transactions: Google Sheets via gspread
#  Charts: Plotly grouped bar (Ideal vs Actual 50/30/20)wadadsadasdwasdaw
# =============================================================================

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import gspread
from google.cloud import firestore
from google.oauth2 import service_account
from datetime import datetime

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="Money Tracker",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Mono:wght@300;400;500&display=swap');

html, body, [class*="css"]         { font-family: 'DM Mono', monospace; }
h1, h2, h3, h4, .syne             { font-family: 'Syne', sans-serif !important; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #0a0a0f !important;
    border-right: 1px solid #1e1e2e;
}
[data-testid="stSidebar"] * { color: #c9c9e0 !important; }
[data-testid="stSidebar"] label {
    font-size: 0.72rem !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    color: #55556a !important;
}

/* ── Main canvas ── */
[data-testid="stAppViewContainer"] { background: #0d0d18; }
.main { background: #0d0d18; }

/* ── Metric card ── */
.mcard {
    background: #111120;
    border: 1px solid #1e1e30;
    border-radius: 14px;
    padding: 20px 22px;
    text-align: center;
}
.mcard-label { font-size: 0.68rem; letter-spacing: 0.12em; text-transform: uppercase; color: #44445a; margin-bottom: 8px; }
.mcard-value { font-family: 'Syne', sans-serif; font-size: 1.75rem; font-weight: 800; color: #e8e8f8; }
.mcard-sub   { font-size: 0.7rem; color: #44445a; margin-top: 5px; }

/* ── Health pill ── */
.hcard {
    background: #111120; border: 1px solid #1e1e30;
    border-radius: 12px; padding: 14px 18px; text-align: center;
}
.hcard-title { font-family:'Syne',sans-serif; font-size:0.9rem; font-weight:700; color:#c9c9e0; }
.hcard-sub   { font-size:0.72rem; color:#44445a; margin:4px 0; }
.hcard-status{ font-size:0.82rem; font-weight:600; margin-top:6px; }

/* ── Section title ── */
.stitle {
    font-family:'Syne',sans-serif; font-size:1rem; font-weight:700;
    color:#888898; letter-spacing:0.06em; text-transform:uppercase;
    border-bottom:1px solid #1e1e30; padding-bottom:8px; margin:28px 0 16px;
}

/* ── Buttons ── */
.stButton > button {
    background: #1a1a2e !important;
    border: 1px solid #2e2e4e !important;
    color: #a0a0c8 !important;
    border-radius: 10px !important;
    font-family: 'DM Mono', monospace !important;
    font-size: 0.8rem !important;
    letter-spacing: 0.04em !important;
    transition: all 0.2s !important;
}
.stButton > button:hover {
    background: #2e2e4e !important;
    border-color: #5050a0 !important;
    color: #e0e0ff !important;
}

/* ── Inputs ── */
.stSelectbox > div > div,
.stTextInput > div > div > input,
.stNumberInput > div > div > input {
    background: #2a2a3a !important;
    border: 1px solid #3a3a52 !important;
    border-radius: 9px !important;
    color: #ffffff !important;
    font-family: 'DM Mono', monospace !important;
}
.stTextInput > div > div > input::placeholder { color: #55556a !important; }

hr { border-color: #1e1e30 !important; }
</style>
""", unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ═════════════════════════════════════════════════════════════════════════════
IDEAL       = {"Needs": 50, "Wants": 30, "Savings": 20}
BUCKETS     = ["Needs", "Wants", "Savings"]
BUCKET_CLR  = {"Needs": "#4ECDC4", "Wants": "#FFE66D", "Savings": "#A8E6CF"}

DEFAULT_CATEGORIES = {
    "Needs":   ["Rent", "Groceries", "Utilities", "Transport", "Insurance", "Healthcare"],
    "Wants":   ["Dining Out", "Entertainment", "Shopping", "Subscriptions", "Travel"],
    "Savings": ["Emergency Fund", "Investments", "Retirement"],
}

# Google Sheets column layout
GS_COLS = ["date", "sheet_name", "type", "bucket", "category", "amount", "note"]


# ═════════════════════════════════════════════════════════════════════════════
#  SERVICE CLIENTS  (cached — created once per session)
# ═════════════════════════════════════════════════════════════════════════════
@st.cache_resource
def get_firestore_client() -> firestore.Client:
    """
    Build a Firestore client from service-account credentials stored in
    st.secrets["gcp_service_account"].  The secret must be a TOML table
    matching the fields of a GCP service-account JSON key file.
    """
    key_dict = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(
        key_dict,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    # If your Firestore database is NOT named "(default)", add this line
    # to [gcp_service_account] in secrets.toml:  firestore_database = "your-db-name"
    db_name = key_dict.get("firestore_database", "(default)")
    return firestore.Client(
        project=key_dict["project_id"],
        credentials=creds,
        database=db_name,
    )


@st.cache_resource
def get_gspread_client() -> gspread.Client:
    """
    Build a gspread client from the same service-account credentials.
    The service account must be shared as an Editor on every user's Sheet.
    """
    key_dict = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(
        key_dict,
        scopes=[
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    return gspread.authorize(creds)


# ═════════════════════════════════════════════════════════════════════════════
#  FIRESTORE HELPERS
# ═════════════════════════════════════════════════════════════════════════════
def fs_get_categories(sheet_id: str) -> dict:
    """Load categories from Firestore keyed by sheet_id, falling back to defaults."""
    db  = get_firestore_client()
    ref = db.collection("sheets").document(sheet_id).collection("meta").document("categories")
    doc = ref.get()
    return doc.to_dict() if doc.exists else dict(DEFAULT_CATEGORIES)


def fs_save_categories(sheet_id: str, categories: dict) -> None:
    """Save categories to Firestore keyed by sheet_id."""
    db  = get_firestore_client()
    ref = db.collection("sheets").document(sheet_id).collection("meta").document("categories")
    ref.set(categories)


# ═════════════════════════════════════════════════════════════════════════════
#  GOOGLE SHEETS HELPERS
# ═════════════════════════════════════════════════════════════════════════════
def gs_get_or_create_worksheet(sheet_id: str, tab_name: str) -> gspread.Worksheet:
    """
    Open a Google Spreadsheet by its ID and return the named worksheet,
    creating it (with header row) if it doesn't exist yet.
    """
    gc   = get_gspread_client()
    book = gc.open_by_key(sheet_id)
    try:
        ws = book.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        ws = book.add_worksheet(title=tab_name, rows=1000, cols=len(GS_COLS))
        ws.append_row(GS_COLS)
    # Ensure header exists even on pre-existing sheet
    first = ws.row_values(1)
    if first != GS_COLS:
        ws.insert_row(GS_COLS, 1)
    return ws


def gs_load_transactions(sheet_id: str, tab_name: str) -> pd.DataFrame:
    """Load all transactions from a worksheet into a DataFrame."""
    ws   = gs_get_or_create_worksheet(sheet_id, tab_name)
    rows = ws.get_all_records(expected_headers=GS_COLS)
    if not rows:
        return pd.DataFrame(columns=GS_COLS)
    df = pd.DataFrame(rows)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
    return df


def gs_append_transaction(sheet_id: str, tab_name: str, txn: dict) -> None:
    """Append a single transaction row to the worksheet."""
    ws  = gs_get_or_create_worksheet(sheet_id, tab_name)
    row = [txn.get(col, "") for col in GS_COLS]
    ws.append_row(row, value_input_option="USER_ENTERED")


def gs_delete_row(sheet_id: str, tab_name: str, row_index_1based: int) -> None:
    """Delete a worksheet row by 1-based index (row 1 = header)."""
    ws = gs_get_or_create_worksheet(sheet_id, tab_name)
    ws.delete_rows(row_index_1based)


def gs_list_sheet_tabs(sheet_id: str) -> list[str]:
    """Return all worksheet tab names in the Google Spreadsheet."""
    gc   = get_gspread_client()
    book = gc.open_by_key(sheet_id)
    return [ws.title for ws in book.worksheets()]


def gs_delete_worksheet(sheet_id: str, tab_name: str) -> None:
    """Delete a worksheet tab from the Google Spreadsheet."""
    gc   = get_gspread_client()
    book = gc.open_by_key(sheet_id)
    ws   = book.worksheet(tab_name)
    book.del_worksheet(ws)


# ═════════════════════════════════════════════════════════════════════════════
#  BUSINESS LOGIC
# ═════════════════════════════════════════════════════════════════════════════
def compute_summary(df: pd.DataFrame) -> dict:
    income    = df[df["type"] == "Income"]["amount"].sum()
    exp_df    = df[df["type"] == "Expense"]
    needs     = exp_df[exp_df["bucket"] == "Needs"]["amount"].sum()
    wants     = exp_df[exp_df["bucket"] == "Wants"]["amount"].sum()
    savings   = exp_df[exp_df["bucket"] == "Savings"]["amount"].sum()
    total_exp = needs + wants + savings
    return dict(income=income, needs=needs, wants=wants,
                savings=savings, total_exp=total_exp, balance=income - total_exp)


def pct(value: float, income: float) -> float:
    return round(value / income * 100, 1) if income else 0.0


# ═════════════════════════════════════════════════════════════════════════════
#  SHEET ID GATE
#  Sheet ID is stored in st.query_params so it persists across refreshes and
#  browser restarts. The URL becomes: https://your-app.streamlit.app/?sid=...
#  Clearing ?sid from the URL (or clicking Sign Out) logs the user out.
# ═════════════════════════════════════════════════════════════════════════════

# Seed session_state from query params on every cold load
if "sheet_id" not in st.session_state and "sid" in st.query_params:
    st.session_state.sheet_id = st.query_params["sid"]

if "sheet_id" not in st.session_state:
    st.markdown(
        """
        <div style='text-align:center;margin:60px auto 0;max-width:500px;'>
            <div style='font-size:3rem;margin-bottom:12px;'>💰</div>
            <div style='font-family:Syne,sans-serif;font-size:2rem;font-weight:800;
                        color:#e8e8f8;margin-bottom:8px;'>Money Tracker</div>
            <div style='color:#55556a;font-size:0.85rem;margin-bottom:32px;'>
                Paste your Google Sheet ID to load your data.<br>
                <span style='color:#33334a;font-size:0.75rem;'>
                Found in your Sheet URL:<br>
                docs.google.com/spreadsheets/d/<b style='color:#6666c0'>SHEET_ID</b>/edit
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        sid_input = st.text_input(
            "Sheet ID",
            placeholder="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74…",
            label_visibility="collapsed",
        )
        if st.button("Open My Sheet →", use_container_width=True):
            sid = sid_input.strip()
            if not sid:
                st.error("Please paste your Sheet ID.")
            else:
                try:
                    gc = get_gspread_client()
                    gc.open_by_key(sid)
                    # Persist in both session_state AND the URL query param
                    st.session_state.sheet_id = sid
                    st.query_params["sid"] = sid
                    st.rerun()
                except gspread.exceptions.SpreadsheetNotFound:
                    st.error("Sheet not found — make sure the service account is shared as Editor.")
                except Exception as e:
                    st.error(f"Error: {e}")
    st.stop()

SHEET_ID = st.session_state.sheet_id
# Keep query param in sync (covers the case where session was seeded from URL)
st.query_params["sid"] = SHEET_ID


# ═════════════════════════════════════════════════════════════════════════════
#  SESSION STATE BOOTSTRAP
# ═════════════════════════════════════════════════════════════════════════════
if "active_tab" not in st.session_state:
    tabs = gs_list_sheet_tabs(SHEET_ID)
    st.session_state.active_tab = tabs[0] if tabs else None

if "categories" not in st.session_state:
    st.session_state.categories = fs_get_categories(SHEET_ID)


def save_categories():
    fs_save_categories(SHEET_ID, st.session_state.categories)


# ═════════════════════════════════════════════════════════════════════════════
#  SIDEBAR
# ═════════════════════════════════════════════════════════════════════════════
with st.sidebar:

    # ── App header ───────────────────────────────────────────────────────────
    st.markdown(
        "<div style='padding:10px 0 14px;font-family:Syne,sans-serif;"
        "font-size:1.2rem;font-weight:800;color:#e8e8f8;'>💰 Money Tracker</div>",
        unsafe_allow_html=True,
    )

    # ── Switch / Sign out ─────────────────────────────────────────────────────
    with st.expander("🔗 Switch Sheet"):
        st.caption(f"Active: `{SHEET_ID[:28]}…`")
        new_sid = st.text_input("New Sheet ID", placeholder="Paste Sheet ID", key="switch_sheet_input")
        if st.button("Switch", key="btn_switch_sheet"):
            sid = new_sid.strip()
            if not sid:
                st.error("Paste a Sheet ID first.")
            elif sid == SHEET_ID:
                st.info("Already using that sheet.")
            else:
                try:
                    gc = get_gspread_client()
                    gc.open_by_key(sid)
                    st.session_state.sheet_id   = sid
                    st.session_state.active_tab = None
                    st.session_state.pop("categories", None)
                    st.query_params["sid"] = sid
                    st.rerun()
                except gspread.exceptions.SpreadsheetNotFound:
                    st.error("Sheet not found — check it's shared with the service account.")
                except Exception as e:
                    st.error(f"Error: {e}")
        if st.button("Sign out", key="btn_signout"):
            for k in ["sheet_id", "active_tab", "categories"]:
                st.session_state.pop(k, None)
            st.query_params.clear()
            st.rerun()

    st.markdown("---")

    # Fetch tabs once so all sections below can use active_tab
    all_tabs   = gs_list_sheet_tabs(SHEET_ID)
    active_tab = (
        st.session_state.active_tab
        if st.session_state.active_tab in all_tabs
        else (all_tabs[0] if all_tabs else None)
    )
    st.session_state.active_tab = active_tab

    # ── 1. Add Transaction ────────────────────────────────────────────────────
    if active_tab:
        st.markdown("### 💸 Add Transaction")
        tx_type = st.radio("Type", ["Income", "Expense"], horizontal=True, key="tx_type")

        if tx_type == "Income":
            income_cats  = ["Salary", "Freelance", "Bonus", "Initial Balance", "Other"]
            selected_cat = st.selectbox("Category", income_cats, key="tx_cat_income")
            bucket_sel   = "Income"
        else:
            bucket_sel = st.selectbox("Bucket", BUCKETS, key="tx_bucket")
            cat_list   = st.session_state.categories.get(bucket_sel, [])
            if not cat_list:
                st.warning("No categories — add one below.")
                selected_cat = None
            else:
                selected_cat = st.selectbox("Category", cat_list, key="tx_cat")

        amount_raw = st.text_input("Amount ($)", value="", placeholder="e.g. 150.00", key="tx_amount")
        try:
            amount = float(amount_raw.replace(",", ".")) if amount_raw.strip() else 0.0
        except ValueError:
            amount = 0.0
            st.caption("⚠️ Enter a valid number.")
        note   = st.text_input("Note (optional)", placeholder="e.g. Netflix", key="tx_note")

        if st.button("Add Transaction ✓", key="btn_add_tx"):
            if selected_cat and amount > 0:
                gs_append_transaction(SHEET_ID, active_tab, {
                    "date":       datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "sheet_name": active_tab,
                    "type":       tx_type,
                    "bucket":     bucket_sel,
                    "category":   selected_cat,
                    "amount":     round(amount, 2),
                    "note":       note,
                })
                st.success("Added!")
                st.rerun()
            else:
                st.error("Fill in all required fields.")
    else:
        st.info("Create a track below to start adding transactions.")

    st.markdown("---")

    # ── 2. Manage Categories ──────────────────────────────────────────────────
    with st.expander("🏷️ Manage Categories"):
        bucket_edit  = st.selectbox("Bucket", BUCKETS, key="cat_bucket_edit")
        current_cats = st.session_state.categories.get(bucket_edit, [])
        st.caption(f"Current: {', '.join(current_cats) or 'none'}")

        new_cat = st.text_input("Add category", key="new_cat_input", placeholder="e.g. Gym")
        if st.button("Add", key="btn_add_cat"):
            if new_cat and new_cat not in current_cats:
                st.session_state.categories[bucket_edit].append(new_cat)
                save_categories()
                st.rerun()

        if current_cats:
            del_cat = st.selectbox("Remove", ["(select)"] + current_cats, key="del_cat_sel")
            if st.button("Remove", key="btn_del_cat") and del_cat != "(select)":
                st.session_state.categories[bucket_edit].remove(del_cat)
                save_categories()
                st.rerun()

    st.markdown("---")

    # ── 3. Track selector + Rename + Delete ───────────────────────────────────
    st.markdown("### 📁 Tracks")

    if all_tabs:
        active_tab = st.selectbox(
            "Active track",
            options=all_tabs,
            index=all_tabs.index(st.session_state.active_tab)
                  if st.session_state.active_tab in all_tabs else 0,
            key="tab_selector",
        )
        st.session_state.active_tab = active_tab
    else:
        active_tab = None
        st.info("No tracks yet — create one below.")

    if active_tab:
        with st.expander("✏️ Rename track"):
            new_tab_name = st.text_input("New name", value=active_tab, key="rename_tab")
            if st.button("Rename", key="btn_rename"):
                if new_tab_name and new_tab_name != active_tab:
                    if new_tab_name in all_tabs:
                        st.error("Name already taken.")
                    else:
                        gc   = get_gspread_client()
                        book = gc.open_by_key(SHEET_ID)
                        ws   = book.worksheet(active_tab)
                        ws.update_title(new_tab_name)
                        st.session_state.active_tab = new_tab_name
                        st.rerun()

    if active_tab:
        with st.expander("🗑️ Delete track"):
            st.markdown(
                f"<div style='color:#FF6B6B;font-size:0.82rem;margin-bottom:10px;'>"
                f"⚠️ Permanently delete <b>{active_tab}</b> and all its rows.<br>"
                f"This cannot be undone.</div>",
                unsafe_allow_html=True,
            )
            confirmed = st.checkbox(f'Yes, delete "{active_tab}"', key="confirm_del_tab")
            if st.button("Delete Track", key="btn_del_tab", disabled=not confirmed):
                gs_delete_worksheet(SHEET_ID, active_tab)
                remaining = [t for t in all_tabs if t != active_tab]
                st.session_state.active_tab = remaining[-1] if remaining else None
                st.rerun()

    st.markdown("---")

    # ── 4. New Track ──────────────────────────────────────────────────────────
    st.markdown("### ➕ New Track")
    new_tab_input = st.text_input("Track name", placeholder="e.g. March 2026", key="new_tab_input")
    carry_opt     = st.radio(
        "Starting balance",
        ["Clear Start ($0)", "Carry Over from current track"],
        key="carry_opt",
    )

    if st.button("Create Track", key="btn_create_tab"):
        if not new_tab_input:
            st.error("Enter a track name.")
        elif new_tab_input in all_tabs:
            st.error("A track with that name already exists.")
        else:
            gs_get_or_create_worksheet(SHEET_ID, new_tab_input)
            if "Carry Over" in carry_opt and active_tab:
                df_cur = gs_load_transactions(SHEET_ID, active_tab)
                s      = compute_summary(df_cur)
                if s["balance"] > 0:
                    gs_append_transaction(SHEET_ID, new_tab_input, {
                        "date":       datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "sheet_name": new_tab_input,
                        "type":       "Income",
                        "bucket":     "Income",
                        "category":   "Initial Balance",
                        "amount":     round(s["balance"], 2),
                        "note":       f"Carried over from {active_tab}",
                    })
            st.session_state.active_tab = new_tab_input
            st.rerun()



# ═════════════════════════════════════════════════════════════════════════════
#  MAIN DASHBOARD
# ═════════════════════════════════════════════════════════════════════════════
if not st.session_state.active_tab:
    st.markdown("""
    <div style='display:flex;flex-direction:column;align-items:center;
                justify-content:center;height:65vh;gap:14px;'>
        <div style='font-size:3.5rem;'>💰</div>
        <div style='font-family:Syne,sans-serif;font-size:2rem;font-weight:800;color:#e8e8f8;'>
            Money Tracker
        </div>
        <div style='color:#44445a;'>Create your first track in the sidebar.</div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ── Load data from Google Sheets ──────────────────────────────────────────────
with st.spinner("Loading transactions…"):
    df = gs_load_transactions(SHEET_ID, st.session_state.active_tab)

summ = compute_summary(df)

# ── Page header ───────────────────────────────────────────────────────────────
st.markdown(f"""
<div style='margin-bottom:4px;'>
    <span style='font-family:Syne,sans-serif;font-size:2rem;font-weight:800;color:#e8e8f8;'>
        {st.session_state.active_tab}
    </span>
</div>
<div style='color:#44445a;font-size:0.8rem;margin-bottom:24px;'>
    {len(df)} transaction{"s" if len(df) != 1 else ""}  ·  Sheet ID: <code>{SHEET_ID[:20]}…</code>
</div>
""", unsafe_allow_html=True)

# ── Summary cards ─────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)

def metric_card(col, label: str, value: str, sub: str = "", color: str = "#e8e8f8"):
    col.markdown(f"""
    <div class='mcard'>
        <div class='mcard-label'>{label}</div>
        <div class='mcard-value' style='color:{color};'>{value}</div>
        <div class='mcard-sub'>{sub}</div>
    </div>""", unsafe_allow_html=True)

inc = summ["income"]
metric_card(c1, "Income",  f"${inc:,.2f}",                                          color="#e8e8f8")
metric_card(c2, "Needs",   f"${summ['needs']:,.2f}",   f"{pct(summ['needs'],   inc)}% of income", color="#4ECDC4")
metric_card(c3, "Wants",   f"${summ['wants']:,.2f}",   f"{pct(summ['wants'],   inc)}% of income", color="#FFE66D")
metric_card(c4, "Savings", f"${summ['savings']:,.2f}", f"{pct(summ['savings'], inc)}% of income", color="#A8E6CF")

bal_color = "#A8E6CF" if summ["balance"] >= 0 else "#FF6B6B"
metric_card(c5, "Balance", f"${summ['balance']:,.2f}", color=bal_color)

st.markdown("<br>", unsafe_allow_html=True)

# ── Plotly grouped bar chart: Ideal vs Actual ─────────────────────────────────
st.markdown("<div class='stitle'>📊 50 / 30 / 20 Budget — Ideal vs Actual</div>", unsafe_allow_html=True)

actual_pcts = {b: pct(summ[b.lower()], inc) for b in BUCKETS}
ideal_pcts  = {b: IDEAL[b] for b in BUCKETS}

bar_colors  = [BUCKET_CLR[b] for b in BUCKETS]

def hex_to_rgba(hex_color: str, alpha: float) -> str:
    """Convert a 6-digit hex color to an rgba() string Plotly accepts."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"

fade_colors = [hex_to_rgba(c, 0.2) for c in bar_colors]   # 20% opacity for ideal bars

fig = go.Figure()

fig.add_trace(go.Bar(
    name="Ideal",
    x=BUCKETS,
    y=[ideal_pcts[b] for b in BUCKETS],
    marker=dict(
        color=fade_colors,
        line=dict(color=bar_colors, width=2),
        pattern_shape="/",
    ),
    text=[f"{ideal_pcts[b]}%" for b in BUCKETS],
    textposition="outside",
    textfont=dict(size=12, color="#55556a", family="DM Mono"),
    hovertemplate="%{x} ideal: %{y}%<extra></extra>",
))

fig.add_trace(go.Bar(
    name="Actual",
    x=BUCKETS,
    y=[actual_pcts[b] for b in BUCKETS],
    marker=dict(color=bar_colors),
    text=[f"{actual_pcts[b]}%" for b in BUCKETS],
    textposition="outside",
    textfont=dict(size=13, color="#e8e8f8", family="Syne"),
    hovertemplate="%{x} actual: %{y}%<extra></extra>",
))

# Annotate over/under per bucket
for i, b in enumerate(BUCKETS):
    diff = actual_pcts[b] - ideal_pcts[b]
    if diff == 0:
        continue
    sign  = "+" if diff > 0 else ""
    clr   = "#FF6B6B" if diff > 5 else "#FFE66D" if diff > 0 else "#A8E6CF"
    label = f"{sign}{diff:.1f}%"
    fig.add_annotation(
        x=b, y=max(actual_pcts[b], ideal_pcts[b]) + 8,
        text=label, showarrow=False,
        font=dict(size=11, color=clr, family="DM Mono"),
    )

fig.update_layout(
    barmode="group",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="DM Mono", color="#c9c9e0"),
    legend=dict(
        bgcolor="rgba(0,0,0,0)",
        font=dict(size=12),
        orientation="h",
        x=0.5, xanchor="center",
        y=1.08,
    ),
    yaxis=dict(
        showgrid=True,
        gridcolor="#1e1e30",
        ticksuffix="%",
        range=[0, max(max(actual_pcts.values(), default=0),
                      max(ideal_pcts.values())) + 22],
        zeroline=False,
    ),
    xaxis=dict(showgrid=False),
    margin=dict(t=50, b=20, l=0, r=0),
    height=360,
    bargap=0.25,
    bargroupgap=0.08,
)

st.plotly_chart(fig, use_container_width=True)

# ── Budget health row ─────────────────────────────────────────────────────────
if inc > 0:
    st.markdown("<div class='stitle'>🩺 Budget Health</div>", unsafe_allow_html=True)
    h1, h2, h3 = st.columns(3)

    def health_card(col, bucket: str):
        a, i = actual_pcts[bucket], ideal_pcts[bucket]
        diff  = a - i
        if abs(diff) <= 5:
            status, clr = "✅ On Track",                "#A8E6CF"
        elif diff > 5:
            status, clr = f"⚠️ Over by {diff:.1f}%",   "#FF6B6B"
        else:
            status, clr = f"💡 Under by {abs(diff):.1f}%", "#FFE66D"

        col.markdown(f"""
        <div class='hcard'>
            <div class='hcard-title'>{bucket}</div>
            <div class='hcard-sub'>Ideal {i}%  ·  Actual {a:.1f}%</div>
            <div class='hcard-status' style='color:{clr};'>{status}</div>
        </div>""", unsafe_allow_html=True)

    health_card(h1, "Needs")
    health_card(h2, "Wants")
    health_card(h3, "Savings")
    st.markdown("<br>", unsafe_allow_html=True)

# ── Transaction log ───────────────────────────────────────────────────────────
st.markdown("<div class='stitle'>📋 Transaction Log</div>", unsafe_allow_html=True)

if df.empty:
    st.markdown("<p style='color:#44445a;text-align:center;padding:40px;'>No transactions yet.</p>",
                unsafe_allow_html=True)
else:
    fc1, fc2, fc3 = st.columns([2, 2, 2])
    with fc1:
        f_type   = st.selectbox("Filter type",   ["All", "Income", "Expense"], key="f_type")
    with fc2:
        f_bucket = st.selectbox("Filter bucket", ["All"] + BUCKETS + ["Income"], key="f_bucket")
    with fc3:
        f_sort   = st.selectbox("Sort", ["Newest first", "Oldest first"], key="f_sort")

    view = df.copy()
    if f_type   != "All": view = view[view["type"]   == f_type]
    if f_bucket != "All": view = view[view["bucket"] == f_bucket]
    if f_sort == "Newest first": view = view.iloc[::-1]

    display = view[["date", "type", "bucket", "category", "amount", "note"]].copy()
    display.columns = ["Date", "Type", "Bucket", "Category", "Amount ($)", "Note"]
    display["Amount ($)"] = display["Amount ($)"].map(lambda x: f"${x:,.2f}")

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Date":       st.column_config.TextColumn(width="medium"),
            "Type":       st.column_config.TextColumn(width="small"),
            "Bucket":     st.column_config.TextColumn(width="small"),
            "Category":   st.column_config.TextColumn(width="medium"),
            "Amount ($)": st.column_config.TextColumn(width="small"),
            "Note":       st.column_config.TextColumn(width="large"),
        },
    )

    # ── Delete a transaction ──────────────────────────────────────────────────
    with st.expander("🗑️ Delete a transaction"):
        st.caption("Deletes from the Google Sheet. Cannot be undone.")
        # Build label → original DataFrame index mapping
        labels = {
            f"[{i+1}] {row['date']} — {row['type']} | {row['category']} | ${row['amount']:,.2f}": i
            for i, row in df.iterrows()
        }
        del_choice = st.selectbox("Select row to delete", list(labels.keys()), key="del_tx_select")
        if st.button("Delete Row", key="btn_del_tx"):
            orig_idx    = labels[del_choice]
            # +2 because Sheets rows are 1-based and row 1 is the header
            sheet_row   = orig_idx + 2
            gs_delete_row(SHEET_ID, st.session_state.active_tab, sheet_row)
            st.success("Row deleted.")
            st.rerun()

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("""
<div style='text-align:center;color:#2a2a40;font-size:0.72rem;padding:8px 0;'>
    Money Tracker · No login required · Data in Google Sheets · Categories in Firestore
</div>
""", unsafe_allow_html=True)
