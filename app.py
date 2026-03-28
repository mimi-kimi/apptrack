# =============================================================================
#  💰 Money Tracker — Cloud Edition
#  Auth : streamlit-authenticator  (credentials in st.secrets)
#  Meta : Firestore                (sheet_id + categories per user)
#  Data : Google Sheets via gspread (one tab = one track)
#  Chart: Plotly grouped bar       (Ideal vs Actual 50/30/20)
# =============================================================================

import streamlit as st
import streamlit_authenticator as stauth
import pandas as pd
import plotly.graph_objects as go
import gspread
from google.cloud import firestore
from google.oauth2 import service_account
from datetime import datetime

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Money Tracker",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Mono:wght@300;400;500&display=swap');

html, body, [class*="css"]  { font-family: 'DM Mono', monospace; }
h1, h2, h3, h4              { font-family: 'Syne', sans-serif !important; }

/* Sidebar */
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

/* Main canvas */
[data-testid="stAppViewContainer"] { background: #0d0d18; }
.main { background: #0d0d18; }

/* Metric card */
.mcard {
    background: #111120; border: 1px solid #1e1e30;
    border-radius: 14px; padding: 20px 22px; text-align: center;
}
.mcard-label { font-size:0.68rem; letter-spacing:0.12em; text-transform:uppercase; color:#44445a; margin-bottom:8px; }
.mcard-value { font-family:'Syne',sans-serif; font-size:1.75rem; font-weight:800; color:#e8e8f8; }
.mcard-sub   { font-size:0.7rem; color:#44445a; margin-top:5px; }

/* Health card */
.hcard { background:#111120; border:1px solid #1e1e30; border-radius:12px; padding:14px 18px; text-align:center; }
.hcard-title  { font-family:'Syne',sans-serif; font-size:0.9rem; font-weight:700; color:#c9c9e0; }
.hcard-sub    { font-size:0.72rem; color:#44445a; margin:4px 0; }
.hcard-status { font-size:0.82rem; font-weight:600; margin-top:6px; }

/* Section title */
.stitle {
    font-family:'Syne',sans-serif; font-size:1rem; font-weight:700;
    color:#888898; letter-spacing:0.06em; text-transform:uppercase;
    border-bottom:1px solid #1e1e30; padding-bottom:8px; margin:28px 0 16px;
}

/* Buttons */
.stButton > button {
    background: #1a1a2e !important; border: 1px solid #2e2e4e !important;
    color: #a0a0c8 !important; border-radius: 10px !important;
    font-family: 'DM Mono', monospace !important; font-size: 0.8rem !important;
    letter-spacing: 0.04em !important; transition: all 0.2s !important;
}
.stButton > button:hover {
    background: #2e2e4e !important; border-color: #5050a0 !important;
    color: #e0e0ff !important;
}

/* Inputs — grey background, white text, blank by default */
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

/* Login form */
div[data-testid="stForm"] {
    background: #111120; border: 1px solid #1e1e30;
    border-radius: 16px; padding: 32px 36px;
    max-width: 440px; margin: 60px auto 0;
}

hr { border-color: #1e1e30 !important; }
</style>
""", unsafe_allow_html=True)


# =============================================================================
#  CONSTANTS
# =============================================================================
IDEAL      = {"Needs": 50, "Wants": 30, "Savings": 20}
BUCKETS    = ["Needs", "Wants", "Savings"]
BUCKET_CLR = {"Needs": "#4ECDC4", "Wants": "#FFE66D", "Savings": "#A8E6CF"}

DEFAULT_CATEGORIES = {
    "Needs":   ["Rent", "Groceries", "Utilities", "Transport", "Insurance", "Healthcare"],
    "Wants":   ["Dining Out", "Entertainment", "Shopping", "Subscriptions", "Travel"],
    "Savings": ["Emergency Fund", "Investments", "Retirement"],
}

GS_COLS = ["date", "sheet_name", "type", "bucket", "category", "amount", "note"]


# =============================================================================
#  SERVICE CLIENTS
# =============================================================================
@st.cache_resource
def get_firestore_client() -> firestore.Client:
    key   = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(
        key, scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    return firestore.Client(project=key["project_id"], credentials=creds)


@st.cache_resource
def get_gspread_client() -> gspread.Client:
    key   = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(
        key,
        scopes=[
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    return gspread.authorize(creds)


# =============================================================================
#  FIRESTORE HELPERS
# =============================================================================
def fs_get_user(username: str) -> dict | None:
    doc = get_firestore_client().collection("users").document(username).get()
    return doc.to_dict() if doc.exists else None


def fs_upsert_user(username: str, email: str, sheet_id: str) -> None:
    get_firestore_client().collection("users").document(username).set(
        {"email": email, "sheet_id": sheet_id, "updated_at": datetime.utcnow()},
        merge=True,
    )


def fs_get_categories(username: str) -> dict:
    doc = (
        get_firestore_client()
        .collection("users").document(username)
        .collection("meta").document("categories")
        .get()
    )
    return doc.to_dict() if doc.exists else dict(DEFAULT_CATEGORIES)


def fs_save_categories(username: str, cats: dict) -> None:
    (
        get_firestore_client()
        .collection("users").document(username)
        .collection("meta").document("categories")
    ).set(cats)


# =============================================================================
#  GOOGLE SHEETS HELPERS
# =============================================================================
def gs_worksheet(sheet_id: str, tab: str) -> gspread.Worksheet:
    book = get_gspread_client().open_by_key(sheet_id)
    try:
        ws = book.worksheet(tab)
    except gspread.WorksheetNotFound:
        ws = book.add_worksheet(title=tab, rows=1000, cols=len(GS_COLS))
        ws.append_row(GS_COLS)
    if ws.row_values(1) != GS_COLS:
        ws.insert_row(GS_COLS, 1)
    return ws


def gs_load(sheet_id: str, tab: str) -> pd.DataFrame:
    rows = gs_worksheet(sheet_id, tab).get_all_records(expected_headers=GS_COLS)
    if not rows:
        return pd.DataFrame(columns=GS_COLS)
    df = pd.DataFrame(rows)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
    return df


def gs_append(sheet_id: str, tab: str, txn: dict) -> None:
    gs_worksheet(sheet_id, tab).append_row(
        [txn.get(c, "") for c in GS_COLS], value_input_option="USER_ENTERED"
    )


def gs_delete_row(sheet_id: str, tab: str, row_1based: int) -> None:
    gs_worksheet(sheet_id, tab).delete_rows(row_1based)


def gs_tabs(sheet_id: str) -> list[str]:
    return [ws.title for ws in get_gspread_client().open_by_key(sheet_id).worksheets()]


def gs_delete_tab(sheet_id: str, tab: str) -> None:
    book = get_gspread_client().open_by_key(sheet_id)
    book.del_worksheet(book.worksheet(tab))


# =============================================================================
#  BUSINESS LOGIC
# =============================================================================
def summarise(df: pd.DataFrame) -> dict:
    income  = df[df["type"] == "Income"]["amount"].sum()
    exp     = df[df["type"] == "Expense"]
    needs   = exp[exp["bucket"] == "Needs"]["amount"].sum()
    wants   = exp[exp["bucket"] == "Wants"]["amount"].sum()
    savings = exp[exp["bucket"] == "Savings"]["amount"].sum()
    total   = needs + wants + savings
    return dict(income=income, needs=needs, wants=wants,
                savings=savings, total_exp=total, balance=income - total)


def pct(v: float, inc: float) -> float:
    return round(v / inc * 100, 1) if inc else 0.0


def hex_to_rgba(h: str, a: float) -> str:
    h = h.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{a})"


# =============================================================================
#  AUTHENTICATION
#
#  Add this to Streamlit Cloud → Settings → Secrets:
#
#  [auth]
#  cookie_name   = "mt_auth"
#  cookie_key    = "any-random-32-char-string"
#  cookie_expiry = 30
#
#  [auth.credentials.usernames.alice]
#  email    = "alice@example.com"
#  name     = "Alice"
#  password = "$2b$12$..."   # generate: stauth.Hasher.hash("plaintext")
# =============================================================================
def build_authenticator() -> stauth.Authenticate:
    cfg   = st.secrets["auth"]
    creds = {"usernames": {}}
    for uname, udata in cfg["credentials"]["usernames"].items():
        creds["usernames"][uname] = {
            "email":    udata["email"],
            "name":     udata["name"],
            "password": udata["password"],
        }
    return stauth.Authenticate(
        credentials=creds,
        cookie_name=cfg["cookie_name"],
        cookie_key=cfg["cookie_key"],
        cookie_expiry_days=int(cfg.get("cookie_expiry", 30)),
    )


authenticator = build_authenticator()

# ── Login gate ────────────────────────────────────────────────────────────────
authenticator.login(location="main")

auth_status = st.session_state.get("authentication_status")
username    = st.session_state.get("username")
name        = st.session_state.get("name")

if auth_status is False:
    st.error("Incorrect username or password.")
    st.stop()

if auth_status is None:
    st.markdown("""
    <div style='text-align:center;margin-top:60px;'>
        <div style='font-size:3rem;'>💰</div>
        <div style='font-family:Syne,sans-serif;font-size:2.2rem;font-weight:800;
                    color:#e8e8f8;margin:10px 0 6px;'>Money Tracker</div>
        <div style='color:#44445a;font-size:0.85rem;'>Sign in to manage your finances.</div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# =============================================================================
#  POST-LOGIN: load or provision user in Firestore
# =============================================================================
user_doc = fs_get_user(username)

if not user_doc or not user_doc.get("sheet_id"):
    st.markdown(f"""
    <div style='text-align:center;margin:50px auto;max-width:520px;'>
        <div style='font-family:Syne,sans-serif;font-size:1.6rem;
                    font-weight:800;color:#e8e8f8;'>👋 Welcome, {name}!</div>
        <div style='color:#55556a;margin-top:10px;font-size:0.85rem;'>
            Paste your <b>Google Sheet ID</b> to get started.<br><br>
            Find it in your Sheet URL:<br>
            <code>docs.google.com/spreadsheets/d/<b>SHEET_ID</b>/edit</code><br><br>
            Share the sheet with the service-account email as <b>Editor</b> first.
        </div>
    </div>
    """, unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        sid_in = st.text_input(
            "Google Sheet ID",
            placeholder="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74…",
        )
        if st.button("Save & Continue", use_container_width=True):
            if sid_in.strip():
                try:
                    get_gspread_client().open_by_key(sid_in.strip())
                    email = st.secrets["auth"]["credentials"]["usernames"][username]["email"]
                    fs_upsert_user(username, email, sid_in.strip())
                    st.success("Saved! Reloading…")
                    st.rerun()
                except gspread.exceptions.SpreadsheetNotFound:
                    st.error("Sheet not found — check the ID and sharing settings.")
                except Exception as e:
                    st.error(f"Error: {e}")
            else:
                st.error("Please enter a Sheet ID.")
    st.stop()

SHEET_ID = user_doc["sheet_id"]


# =============================================================================
#  SESSION STATE
# =============================================================================
if "active_tab" not in st.session_state:
    tabs = gs_tabs(SHEET_ID)
    st.session_state.active_tab = tabs[0] if tabs else None

if "categories" not in st.session_state:
    st.session_state.categories = fs_get_categories(username)


def save_cats():
    fs_save_categories(username, st.session_state.categories)


# =============================================================================
#  SIDEBAR
# =============================================================================
with st.sidebar:

    # ── User badge + sign out ─────────────────────────────────────────────────
    st.markdown(f"""
    <div style='padding:10px 0 14px;'>
        <div style='font-family:Syne,sans-serif;font-size:1.1rem;
                    font-weight:800;color:#e8e8f8;'>💰 Money Tracker</div>
        <div style='font-size:0.75rem;color:#44445a;margin-top:2px;'>
            {name} &nbsp;·&nbsp; @{username}
        </div>
    </div>
    """, unsafe_allow_html=True)

    authenticator.logout(button_name="Sign out", location="sidebar")

    # ── Change Sheet ──────────────────────────────────────────────────────────
    with st.expander("🔗 Change Google Sheet"):
        st.caption(f"Current: `{SHEET_ID[:26]}…`")
        new_sid = st.text_input("New Sheet ID", placeholder="Paste Sheet ID",
                                key="change_sid_input")
        if st.button("Save", key="btn_change_sid"):
            sid = new_sid.strip()
            if not sid:
                st.error("Paste a Sheet ID first.")
            elif sid == SHEET_ID:
                st.info("Already using that sheet.")
            else:
                try:
                    get_gspread_client().open_by_key(sid)
                    email = st.secrets["auth"]["credentials"]["usernames"][username]["email"]
                    fs_upsert_user(username, email, sid)
                    st.session_state.active_tab = None
                    st.success("Updated! Reloading…")
                    st.rerun()
                except gspread.exceptions.SpreadsheetNotFound:
                    st.error("Sheet not found — check sharing settings.")
                except Exception as e:
                    st.error(f"Error: {e}")

    st.markdown("---")

    # Resolve active tab
    all_tabs   = gs_tabs(SHEET_ID)
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

        # Blank amount — user types immediately, no pre-filled 0.00
        amount_raw = st.text_input(
            "Amount ($)", value="", placeholder="e.g. 150.00", key="tx_amount"
        )
        try:
            amount = float(amount_raw.replace(",", ".")) if amount_raw.strip() else 0.0
        except ValueError:
            amount = 0.0
            st.caption("⚠️ Enter a valid number.")

        note = st.text_input("Note (optional)", placeholder="e.g. Netflix", key="tx_note")

        if st.button("Add Transaction ✓", key="btn_add_tx"):
            if selected_cat and amount > 0:
                gs_append(SHEET_ID, active_tab, {
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

        new_cat = st.text_input("Add category", placeholder="e.g. Gym", key="new_cat_input")
        if st.button("Add", key="btn_add_cat"):
            if new_cat and new_cat not in current_cats:
                st.session_state.categories[bucket_edit].append(new_cat)
                save_cats()
                st.rerun()

        if current_cats:
            del_cat = st.selectbox("Remove", ["(select)"] + current_cats, key="del_cat_sel")
            if st.button("Remove", key="btn_del_cat") and del_cat != "(select)":
                st.session_state.categories[bucket_edit].remove(del_cat)
                save_cats()
                st.rerun()

    st.markdown("---")

    # ── 3. Tracks ─────────────────────────────────────────────────────────────
    st.markdown("### 📁 Tracks")

    if all_tabs:
        active_tab = st.selectbox(
            "Active track", options=all_tabs,
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
                        book = get_gspread_client().open_by_key(SHEET_ID)
                        book.worksheet(active_tab).update_title(new_tab_name)
                        st.session_state.active_tab = new_tab_name
                        st.rerun()

    if active_tab:
        with st.expander("🗑️ Delete track"):
            st.markdown(
                f"<div style='color:#FF6B6B;font-size:0.82rem;margin-bottom:10px;'>"
                f"⚠️ Permanently delete <b>{active_tab}</b> and all its rows. "
                f"Cannot be undone.</div>",
                unsafe_allow_html=True,
            )
            confirmed = st.checkbox(f'Yes, delete "{active_tab}"', key="confirm_del_tab")
            if st.button("Delete Track", key="btn_del_tab", disabled=not confirmed):
                gs_delete_tab(SHEET_ID, active_tab)
                remaining = [t for t in all_tabs if t != active_tab]
                st.session_state.active_tab = remaining[-1] if remaining else None
                st.rerun()

    st.markdown("---")

    # ── 4. New Track ──────────────────────────────────────────────────────────
    st.markdown("### ➕ New Track")
    new_tab = st.text_input("Track name", placeholder="e.g. March 2026", key="new_tab_input")
    carry   = st.radio(
        "Starting balance",
        ["Clear Start ($0)", "Carry Over from current track"],
        key="carry_opt",
    )

    if st.button("Create Track", key="btn_create_tab"):
        if not new_tab:
            st.error("Enter a track name.")
        elif new_tab in all_tabs:
            st.error("Name already taken.")
        else:
            gs_worksheet(SHEET_ID, new_tab)
            if "Carry Over" in carry and active_tab:
                s = summarise(gs_load(SHEET_ID, active_tab))
                if s["balance"] > 0:
                    gs_append(SHEET_ID, new_tab, {
                        "date":       datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "sheet_name": new_tab,
                        "type":       "Income",
                        "bucket":     "Income",
                        "category":   "Initial Balance",
                        "amount":     round(s["balance"], 2),
                        "note":       f"Carried over from {active_tab}",
                    })
            st.session_state.active_tab = new_tab
            st.rerun()


# =============================================================================
#  MAIN DASHBOARD
# =============================================================================
if not st.session_state.active_tab:
    st.markdown("""
    <div style='display:flex;flex-direction:column;align-items:center;
                justify-content:center;height:65vh;gap:14px;'>
        <div style='font-size:3.5rem;'>💰</div>
        <div style='font-family:Syne,sans-serif;font-size:2rem;
                    font-weight:800;color:#e8e8f8;'>Money Tracker</div>
        <div style='color:#44445a;'>Create your first track in the sidebar.</div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

with st.spinner("Loading…"):
    df   = gs_load(SHEET_ID, st.session_state.active_tab)
summ = summarise(df)
inc  = summ["income"]

# ── Page header ───────────────────────────────────────────────────────────────
st.markdown(f"""
<div style='margin-bottom:4px;'>
    <span style='font-family:Syne,sans-serif;font-size:2rem;
                 font-weight:800;color:#e8e8f8;'>
        {st.session_state.active_tab}
    </span>
</div>
<div style='color:#44445a;font-size:0.8rem;margin-bottom:24px;'>
    {len(df)} transaction{"s" if len(df) != 1 else ""}
</div>
""", unsafe_allow_html=True)

# ── Summary cards ─────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)

def mcard(col, label, value, sub="", color="#e8e8f8"):
    col.markdown(f"""
    <div class='mcard'>
        <div class='mcard-label'>{label}</div>
        <div class='mcard-value' style='color:{color};'>{value}</div>
        <div class='mcard-sub'>{sub}</div>
    </div>""", unsafe_allow_html=True)

mcard(c1, "Income",  f"${inc:,.2f}")
mcard(c2, "Needs",   f"${summ['needs']:,.2f}",   f"{pct(summ['needs'],   inc)}% of income", "#4ECDC4")
mcard(c3, "Wants",   f"${summ['wants']:,.2f}",   f"{pct(summ['wants'],   inc)}% of income", "#FFE66D")
mcard(c4, "Savings", f"${summ['savings']:,.2f}", f"{pct(summ['savings'], inc)}% of income", "#A8E6CF")
mcard(c5, "Balance", f"${summ['balance']:,.2f}",
      color="#A8E6CF" if summ["balance"] >= 0 else "#FF6B6B")

st.markdown("<br>", unsafe_allow_html=True)

# ── Grouped bar chart: Ideal vs Actual ───────────────────────────────────────
st.markdown("<div class='stitle'>📊 50 / 30 / 20 — Ideal vs Actual</div>",
            unsafe_allow_html=True)

actual = {b: pct(summ[b.lower()], inc) for b in BUCKETS}
bclrs  = [BUCKET_CLR[b] for b in BUCKETS]
fade   = [hex_to_rgba(c, 0.2) for c in bclrs]

fig = go.Figure()
fig.add_trace(go.Bar(
    name="Ideal", x=BUCKETS, y=[IDEAL[b] for b in BUCKETS],
    marker=dict(color=fade, line=dict(color=bclrs, width=2), pattern_shape="/"),
    text=[f"{IDEAL[b]}%" for b in BUCKETS], textposition="outside",
    textfont=dict(size=12, color="#55556a", family="DM Mono"),
    hovertemplate="%{x} ideal: %{y}%<extra></extra>",
))
fig.add_trace(go.Bar(
    name="Actual", x=BUCKETS, y=[actual[b] for b in BUCKETS],
    marker=dict(color=bclrs),
    text=[f"{actual[b]}%" for b in BUCKETS], textposition="outside",
    textfont=dict(size=13, color="#e8e8f8", family="Syne"),
    hovertemplate="%{x} actual: %{y}%<extra></extra>",
))

for b in BUCKETS:
    diff = actual[b] - IDEAL[b]
    if diff == 0:
        continue
    clr = "#FF6B6B" if diff > 5 else "#FFE66D" if diff > 0 else "#A8E6CF"
    fig.add_annotation(
        x=b, y=max(actual[b], IDEAL[b]) + 8,
        text=f"{'+'if diff>0 else ''}{diff:.1f}%",
        showarrow=False, font=dict(size=11, color=clr, family="DM Mono"),
    )

fig.update_layout(
    barmode="group",
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="DM Mono", color="#c9c9e0"),
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=12),
                orientation="h", x=0.5, xanchor="center", y=1.08),
    yaxis=dict(showgrid=True, gridcolor="#1e1e30", ticksuffix="%",
               range=[0, max(max(actual.values(), default=0), 50) + 22],
               zeroline=False),
    xaxis=dict(showgrid=False),
    margin=dict(t=50, b=20, l=0, r=0), height=360,
    bargap=0.25, bargroupgap=0.08,
)
st.plotly_chart(fig, use_container_width=True)

# ── Budget health ─────────────────────────────────────────────────────────────
if inc > 0:
    st.markdown("<div class='stitle'>🩺 Budget Health</div>", unsafe_allow_html=True)
    h1, h2, h3 = st.columns(3)
 
    def hcard(col, bucket):
        a, i      = actual[bucket], IDEAL[bucket]
        diff      = a - i
        ideal_amt = f"${inc * i / 100:,.2f}"
 
        if bucket == "Savings":
            # Saving more than ideal is a good thing
            if abs(diff) <= 5: status, clr = "✅ On Track",                   "#A8E6CF"
            elif diff > 5:     status, clr = f"🌟 Extra by {diff:.1f}%",      "#A8E6CF"
            else:              status, clr = f"⚠️ Short by {abs(diff):.1f}%", "#FF6B6B"
        else:
            # Spending more than ideal on Needs/Wants is a warning
            if abs(diff) <= 5: status, clr = "✅ On Track",                    "#A8E6CF"
            elif diff > 5:     status, clr = f"⚠️ Over by {diff:.1f}%",       "#FF6B6B"
            else:              status, clr = f"💡 Under by {abs(diff):.1f}%",  "#FFE66D"
 
        col.markdown(f"""
        <div class='hcard'>
            <div class='hcard-title'>{bucket}</div>
            <div class='hcard-sub'>Ideal {i}% ({ideal_amt}) · Actual {a:.1f}%</div>
            <div class='hcard-status' style='color:{clr};'>{status}</div>
        </div>""", unsafe_allow_html=True)
 
    hcard(h1, "Needs")
    hcard(h2, "Wants")
    hcard(h3, "Savings")
    st.markdown("<br>", unsafe_allow_html=True)

# ── Transaction log ───────────────────────────────────────────────────────────
st.markdown("<div class='stitle'>📋 Transaction Log</div>", unsafe_allow_html=True)

if df.empty:
    st.markdown(
        "<p style='color:#44445a;text-align:center;padding:40px;'>No transactions yet.</p>",
        unsafe_allow_html=True,
    )
else:
    fc1, fc2, fc3 = st.columns([2, 2, 2])
    with fc1: f_type   = st.selectbox("Filter type",   ["All", "Income", "Expense"], key="f_type")
    with fc2: f_bucket = st.selectbox("Filter bucket", ["All"] + BUCKETS + ["Income"], key="f_bucket")
    with fc3: f_sort   = st.selectbox("Sort", ["Newest first", "Oldest first"], key="f_sort")

    view = df.copy()
    if f_type   != "All": view = view[view["type"]   == f_type]
    if f_bucket != "All": view = view[view["bucket"] == f_bucket]
    if f_sort == "Newest first": view = view.iloc[::-1]

    disp = view[["date", "type", "bucket", "category", "amount", "note"]].copy()
    disp.columns = ["Date", "Type", "Bucket", "Category", "Amount ($)", "Note"]
    disp["Amount ($)"] = disp["Amount ($)"].map(lambda x: f"${x:,.2f}")
    st.dataframe(disp, use_container_width=True, hide_index=True)

    with st.expander("🗑️ Delete a transaction"):
        st.caption("Deletes from Google Sheets. Cannot be undone.")
        labels = {
            f"[{i+1}] {row['date']} — {row['type']} | {row['category']} | ${row['amount']:,.2f}": i
            for i, row in df.iterrows()
        }
        del_choice = st.selectbox("Select row", list(labels.keys()), key="del_tx_select")
        if st.button("Delete Row", key="btn_del_tx"):
            gs_delete_row(SHEET_ID, st.session_state.active_tab, labels[del_choice] + 2)
            st.success("Deleted.")
            st.rerun()

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<div style='text-align:center;color:#2a2a40;font-size:0.72rem;padding:8px 0;'>"
    "Money Tracker · Login via streamlit-authenticator · "
    "Data in Google Sheets · Meta in Firestore</div>",
    unsafe_allow_html=True,
)
