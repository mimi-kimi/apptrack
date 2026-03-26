import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import json
import os
from datetime import datetime
from copy import deepcopy

# ── Constants ──────────────────────────────────────────────────────────────────
DATA_FILE = "money_tracker_data.json"

DEFAULT_CATEGORIES = {
    "Needs":   ["Rent", "Groceries", "Utilities", "Transport", "Insurance", "Healthcare"],
    "Wants":   ["Dining Out", "Entertainment", "Shopping", "Subscriptions", "Travel"],
    "Savings": ["Emergency Fund", "Investments", "Retirement", "Side Hustle"],
}

BUCKET_COLORS = {
    "Needs":   "#4ECDC4",
    "Wants":   "#FFE66D",
    "Savings": "#A8E6CF",
}

IDEAL = {"Needs": 50, "Wants": 30, "Savings": 20}

# ── Persistence ────────────────────────────────────────────────────────────────
def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    # Fresh scaffold
    return {
        "categories": deepcopy(DEFAULT_CATEGORIES),
        "sheets": {},
        "active_sheet": None,
    }


def save_data(data: dict):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ── Sheet helpers ──────────────────────────────────────────────────────────────
def new_sheet(name: str, carry_balance: float = 0.0) -> dict:
    sheet: dict = {"name": name, "transactions": []}
    if carry_balance:
        sheet["transactions"].append({
            "type": "Income",
            "category": "Initial Balance",
            "bucket": "Savings",
            "amount": round(carry_balance, 2),
            "note": "Carried over from previous month",
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
    return sheet


def sheet_summary(sheet: dict) -> dict:
    txns = sheet["transactions"]
    income   = sum(t["amount"] for t in txns if t["type"] == "Income")
    expenses = [t for t in txns if t["type"] == "Expense"]
    needs    = sum(t["amount"] for t in expenses if t["bucket"] == "Needs")
    wants    = sum(t["amount"] for t in expenses if t["bucket"] == "Wants")
    savings  = sum(t["amount"] for t in expenses if t["bucket"] == "Savings")
    total_exp = needs + wants + savings
    balance   = income - total_exp
    return dict(income=income, needs=needs, wants=wants,
                savings=savings, total_exp=total_exp, balance=balance)


# ── App init ───────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Money Tracker",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Inject custom CSS
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1, h2, h3, h4 { font-family: 'Syne', sans-serif !important; }

/* Sidebar */
[data-testid="stSidebar"] {
    background: linear-gradient(160deg, #0f0c29, #302b63, #24243e) !important;
    border-right: 1px solid rgba(255,255,255,0.07);
}
[data-testid="stSidebar"] * { color: #e8e8f0 !important; }
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stTextInput label,
[data-testid="stSidebar"] .stNumberInput label,
[data-testid="stSidebar"] .stRadio label { color: #b0aecf !important; font-size: 0.78rem; letter-spacing: 0.06em; text-transform: uppercase; }

/* Main area */
.main { background: #0d0d1a; }
[data-testid="stAppViewContainer"] { background: #0d0d1a; }

/* Metric cards */
.metric-card {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px;
    padding: 20px 24px;
    text-align: center;
    backdrop-filter: blur(8px);
}
.metric-label { font-size: 0.72rem; letter-spacing: 0.1em; text-transform: uppercase; color: #7070a0; margin-bottom: 6px; }
.metric-value { font-family: 'Syne', sans-serif; font-size: 1.9rem; font-weight: 800; color: #fff; }
.metric-sub   { font-size: 0.75rem; color: #7070a0; margin-top: 4px; }

/* Transaction table */
.tx-row {
    display: flex; align-items: center; justify-content: space-between;
    padding: 10px 14px; border-radius: 10px; margin-bottom: 6px;
    background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06);
}

/* Pill badge */
.badge {
    font-size: 0.68rem; font-weight: 600; padding: 3px 10px; border-radius: 20px;
    letter-spacing: 0.05em; text-transform: uppercase;
}
.badge-income   { background: rgba(78,205,196,0.15); color: #4ECDC4; }
.badge-expense  { background: rgba(255,107,107,0.15); color: #FF6B6B; }
.badge-needs    { background: rgba(78,205,196,0.15);  color: #4ECDC4; }
.badge-wants    { background: rgba(255,230,109,0.15); color: #FFE66D; }
.badge-savings  { background: rgba(168,230,207,0.15); color: #A8E6CF; }

/* Section title */
.section-title {
    font-family: 'Syne', sans-serif; font-size: 1.1rem; font-weight: 700;
    color: #c8c8e8; letter-spacing: 0.04em; border-bottom: 1px solid rgba(255,255,255,0.07);
    padding-bottom: 8px; margin: 24px 0 16px;
}

/* Divider */
hr { border-color: rgba(255,255,255,0.06) !important; }

/* Streamlit button overrides */
.stButton > button {
    background: linear-gradient(135deg, #667eea, #764ba2) !important;
    color: #fff !important; border: none !important;
    border-radius: 10px !important; font-family: 'Syne', sans-serif !important;
    font-weight: 600 !important; letter-spacing: 0.04em !important;
    transition: opacity .2s !important;
}
.stButton > button:hover { opacity: 0.85 !important; }

/* Selectbox / inputs */
.stSelectbox > div > div,
.stTextInput > div > div > input,
.stNumberInput > div > div > input {
    background: rgba(255,255,255,0.06) !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 10px !important; color: #fff !important;
}

/* Radio */
.stRadio > div { flex-direction: row; gap: 12px; }
</style>
""", unsafe_allow_html=True)

# ── Session state bootstrap ────────────────────────────────────────────────────
if "data" not in st.session_state:
    st.session_state.data = load_data()

data = st.session_state.data


def persist():
    save_data(st.session_state.data)


# ── SIDEBAR ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 💰 Money Tracker")
    st.markdown("---")

    # ── Sheet selector ──────────────────────────────────────────────────────
    sheet_names = list(data["sheets"].keys())

    st.markdown("### 📁 Tracks")

    if sheet_names:
        selected_sheet_key = st.selectbox(
            "Active track",
            options=sheet_names,
            index=sheet_names.index(data["active_sheet"]) if data["active_sheet"] in sheet_names else 0,
            key="sheet_select",
        )
        data["active_sheet"] = selected_sheet_key
    else:
        selected_sheet_key = None
        st.info("No tracks yet. Create one below ↓")

    # Rename & Delete track
    if selected_sheet_key:
        with st.expander("✏️ Rename this track"):
            new_name = st.text_input("New name", value=selected_sheet_key, key="rename_input")
            if st.button("Rename"):
                if new_name and new_name != selected_sheet_key and new_name not in data["sheets"]:
                    data["sheets"][new_name] = data["sheets"].pop(selected_sheet_key)
                    data["active_sheet"] = new_name
                    persist()
                    st.rerun()
                elif new_name in data["sheets"]:
                    st.error("Name already taken.")

        with st.expander("🗑️ Delete this track"):
            tx_count = len(data["sheets"][selected_sheet_key]["transactions"])
            st.markdown(
                f"<div style='color:#FF6B6B;font-size:0.85rem;margin-bottom:10px;'>"
                f"⚠️ This will permanently delete <b>{selected_sheet_key}</b> "
                f"and its <b>{tx_count} transaction{'s' if tx_count != 1 else ''}</b>. "
                f"This cannot be undone.</div>",
                unsafe_allow_html=True,
            )
            confirm_delete = st.checkbox(
                f'Yes, delete "{selected_sheet_key}"', key="confirm_delete_sheet"
            )
            if st.button("Delete Track", key="delete_sheet_btn", disabled=not confirm_delete):
                del data["sheets"][selected_sheet_key]
                remaining = list(data["sheets"].keys())
                data["active_sheet"] = remaining[-1] if remaining else None
                persist()
                st.rerun()

    st.markdown("---")

    # ── Create new month ────────────────────────────────────────────────────
    st.markdown("### ➕ New Track")
    new_sheet_name = st.text_input("Track name", placeholder="e.g. March 2026", key="new_sheet_name")
    carry_opt = st.radio("Starting balance", ["Clear Start ($0)", "Carry Over from current track"], key="carry_opt")

    if st.button("Create Track", key="create_sheet_btn"):
        if not new_sheet_name:
            st.error("Please enter a track name.")
        elif new_sheet_name in data["sheets"]:
            st.error("A track with that name already exists.")
        else:
            carry = 0.0
            if "Carry Over" in carry_opt and selected_sheet_key:
                carry = sheet_summary(data["sheets"][selected_sheet_key])["balance"]
            data["sheets"][new_sheet_name] = new_sheet(new_sheet_name, carry)
            data["active_sheet"] = new_sheet_name
            persist()
            st.rerun()

    st.markdown("---")

    # ── Add Transaction ─────────────────────────────────────────────────────
    if selected_sheet_key:
        st.markdown("### 💸 Add Transaction")

        tx_type = st.radio("Type", ["Income", "Expense"], horizontal=True, key="tx_type")

        # Build flat category list
        all_cats = [
            (bucket, cat)
            for bucket, cats in data["categories"].items()
            for cat in cats
        ]
        # For income, show Income-specific categories + all
        if tx_type == "Income":
            income_cats = ["Salary", "Freelance", "Initial Balance"] + [c for _, c in all_cats if _ == "Savings"]
            cat_options = list(dict.fromkeys(income_cats))  # dedupe
            bucket_for_income = "Savings"
            selected_cat = st.selectbox("Category", cat_options, key="tx_cat_income")
            bucket_sel = "Savings"
        else:
            # For expenses, group by bucket
            bucket_sel = st.selectbox("Bucket (50/30/20)", ["Needs", "Wants", "Savings"], key="tx_bucket")
            cat_options = data["categories"].get(bucket_sel, [])
            selected_cat = st.selectbox("Category", cat_options, key="tx_cat_expense") if cat_options else None
            if not cat_options:
                st.warning("No categories in this bucket. Add one below.")

        amount = st.number_input("Amount ($)", min_value=0.01, step=0.01, format="%.2f", key="tx_amount")
        note   = st.text_input("Note (optional)", placeholder="e.g. Netflix subscription", key="tx_note")

        if st.button("Add Transaction ✓", key="add_tx_btn"):
            if selected_cat and amount > 0:
                txn = {
                    "type":     tx_type,
                    "category": selected_cat,
                    "bucket":   bucket_sel if tx_type == "Expense" else "Income",
                    "amount":   round(amount, 2),
                    "note":     note,
                    "date":     datetime.now().strftime("%Y-%m-%d %H:%M"),
                }
                data["sheets"][selected_sheet_key]["transactions"].append(txn)
                persist()
                st.success("Transaction added!")
                st.rerun()
            else:
                st.error("Please fill in all required fields.")

    st.markdown("---")

    # ── Category Management ─────────────────────────────────────────────────
    with st.expander("🏷️ Manage Categories"):
        bucket_edit = st.selectbox("Bucket", ["Needs", "Wants", "Savings"], key="cat_bucket")
        current_cats = data["categories"].get(bucket_edit, [])

        st.markdown(f"**Current:** {', '.join(current_cats) if current_cats else 'None'}")

        new_cat = st.text_input("Add new category", placeholder="e.g. Gym", key="new_cat_input")
        if st.button("Add Category", key="add_cat_btn"):
            if new_cat and new_cat not in current_cats:
                data["categories"][bucket_edit].append(new_cat)
                persist()
                st.success(f"Added '{new_cat}' to {bucket_edit}")
                st.rerun()

        del_cat = st.selectbox("Remove category", ["(select)"] + current_cats, key="del_cat_sel")
        if st.button("Remove", key="del_cat_btn") and del_cat != "(select)":
            data["categories"][bucket_edit].remove(del_cat)
            persist()
            st.rerun()


# ── MAIN AREA ─────────────────────────────────────────────────────────────────
active_key = data.get("active_sheet")

if not active_key or active_key not in data["sheets"]:
    st.markdown("""
    <div style='display:flex;flex-direction:column;align-items:center;justify-content:center;
                height:70vh;gap:16px;'>
        <div style='font-size:4rem;'>💰</div>
        <div style='font-family:Syne,sans-serif;font-size:2rem;font-weight:800;color:#c8c8e8;'>
            Money Tracker
        </div>
        <div style='color:#7070a0;font-size:1rem;'>
            Create your first track in the sidebar to get started.
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

sheet  = data["sheets"][active_key]
txns   = sheet["transactions"]
summ   = sheet_summary(sheet)

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style='margin-bottom:8px;'>
    <span style='font-family:Syne,sans-serif;font-size:2.2rem;font-weight:800;
                 background:linear-gradient(90deg,#667eea,#a78bfa);
                 -webkit-background-clip:text;-webkit-text-fill-color:transparent;'>
        {active_key}
    </span>
</div>
<div style='color:#7070a0;font-size:0.85rem;margin-bottom:24px;'>
    {len(txns)} transaction{"s" if len(txns)!=1 else ""} recorded
</div>
""", unsafe_allow_html=True)

# ── Summary cards ──────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)

def card(col, label, value, sub="", color="#fff"):
    col.markdown(f"""
    <div class='metric-card'>
        <div class='metric-label'>{label}</div>
        <div class='metric-value' style='color:{color};'>{value}</div>
        <div class='metric-sub'>{sub}</div>
    </div>""", unsafe_allow_html=True)

card(c1, "Total Income",  f"${summ['income']:,.2f}",   color="#4ECDC4")
card(c2, "Needs",         f"${summ['needs']:,.2f}",    f"{summ['needs']/summ['income']*100:.1f}% of income" if summ['income'] else "—", color="#4ECDC4")
card(c3, "Wants",         f"${summ['wants']:,.2f}",    f"{summ['wants']/summ['income']*100:.1f}% of income" if summ['income'] else "—", color="#FFE66D")
card(c4, "Savings",       f"${summ['savings']:,.2f}",  f"{summ['savings']/summ['income']*100:.1f}% of income" if summ['income'] else "—", color="#A8E6CF")
card(c5, "Balance",       f"${summ['balance']:,.2f}",  color="#FF6B6B" if summ['balance'] < 0 else "#A8E6CF")

st.markdown("<br>", unsafe_allow_html=True)

# ── Charts ─────────────────────────────────────────────────────────────────────
left_col, right_col = st.columns([3, 2], gap="large")

with left_col:
    st.markdown("<div class='section-title'>📊 50 / 30 / 20 Budget Analysis</div>", unsafe_allow_html=True)

    income = summ["income"]
    actual = {
        "Needs":   (summ["needs"]   / income * 100) if income else 0,
        "Wants":   (summ["wants"]   / income * 100) if income else 0,
        "Savings": (summ["savings"] / income * 100) if income else 0,
    }

    buckets = ["Needs", "Wants", "Savings"]
    ideal_vals  = [IDEAL[b]  for b in buckets]
    actual_vals = [actual[b] for b in buckets]
    colors = [BUCKET_COLORS[b] for b in buckets]

    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(
        name="Ideal",
        x=buckets,
        y=ideal_vals,
        marker_color=["rgba(78,205,196,0.3)", "rgba(255,230,109,0.3)", "rgba(168,230,207,0.3)"],
        marker_line_color=colors,
        marker_line_width=2,
        text=[f"{v}%" for v in ideal_vals],
        textposition="outside",
        textfont=dict(color="#7070a0", size=12),
    ))
    fig_bar.add_trace(go.Bar(
        name="Actual",
        x=buckets,
        y=actual_vals,
        marker_color=colors,
        text=[f"{v:.1f}%" for v in actual_vals],
        textposition="outside",
        textfont=dict(color="#fff", size=13, family="Syne"),
    ))

    fig_bar.update_layout(
        barmode="group",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Sans", color="#c8c8e8"),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=12)),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)",
                   ticksuffix="%", range=[0, max(max(ideal_vals), max(actual_vals) if any(actual_vals) else 0) + 15]),
        xaxis=dict(showgrid=False),
        margin=dict(t=20, b=20, l=0, r=0),
        height=320,
    )
    st.plotly_chart(fig_bar, use_container_width=True)

with right_col:
    st.markdown("<div class='section-title'>🍩 Spending Breakdown</div>", unsafe_allow_html=True)

    donut_labels = ["Needs", "Wants", "Savings", "Unspent"]
    donut_vals = [
        summ["needs"], summ["wants"], summ["savings"],
        max(0, summ["balance"])
    ]
    donut_colors = ["#4ECDC4", "#FFE66D", "#A8E6CF", "rgba(255,255,255,0.08)"]

    fig_donut = go.Figure(go.Pie(
        labels=donut_labels,
        values=donut_vals,
        hole=0.62,
        marker=dict(colors=donut_colors, line=dict(color="#0d0d1a", width=3)),
        textinfo="label+percent",
        textfont=dict(family="DM Sans", size=12, color="#fff"),
        hovertemplate="%{label}: $%{value:,.2f}<extra></extra>",
    ))
    fig_donut.add_annotation(
        text=f"${income:,.0f}<br><span style='font-size:10px'>Income</span>",
        x=0.5, y=0.5, showarrow=False,
        font=dict(family="Syne", size=18, color="#fff"),
    )
    fig_donut.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        margin=dict(t=10, b=10, l=10, r=10),
        height=320,
    )
    st.plotly_chart(fig_donut, use_container_width=True)

# ── Budget health indicator ────────────────────────────────────────────────────
if income > 0:
    st.markdown("<div class='section-title'>🩺 Budget Health</div>", unsafe_allow_html=True)
    h1, h2, h3 = st.columns(3)

    def health_pill(col, bucket, actual_pct, ideal_pct):
        diff = actual_pct - ideal_pct
        if abs(diff) <= 5:
            status, clr = "✅ On Track", "#A8E6CF"
        elif diff > 5:
            status, clr = f"⚠️ Over by {diff:.1f}%", "#FF6B6B"
        else:
            status, clr = f"💡 Under by {abs(diff):.1f}%", "#FFE66D"
        col.markdown(f"""
        <div style='background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);
                    border-radius:12px;padding:16px;text-align:center;'>
            <div style='font-family:Syne;font-size:1rem;font-weight:700;color:#c8c8e8;'>{bucket}</div>
            <div style='font-size:0.75rem;color:#7070a0;margin:4px 0;'>Ideal: {ideal_pct}%  |  Actual: {actual_pct:.1f}%</div>
            <div style='font-size:0.9rem;font-weight:600;color:{clr};'>{status}</div>
        </div>""", unsafe_allow_html=True)

    health_pill(h1, "Needs",   actual["Needs"],   50)
    health_pill(h2, "Wants",   actual["Wants"],   30)
    health_pill(h3, "Savings", actual["Savings"], 20)
    st.markdown("<br>", unsafe_allow_html=True)

# ── Transaction log ────────────────────────────────────────────────────────────
st.markdown("<div class='section-title'>📋 Transaction Log</div>", unsafe_allow_html=True)

if not txns:
    st.markdown("<p style='color:#7070a0;text-align:center;padding:32px;'>No transactions yet. Add one in the sidebar.</p>", unsafe_allow_html=True)
else:
    # Filter controls
    fc1, fc2, fc3 = st.columns([2, 2, 1])
    with fc1:
        filter_type = st.selectbox("Filter by type", ["All", "Income", "Expense"], key="filter_type")
    with fc2:
        filter_bucket = st.selectbox("Filter by bucket", ["All", "Needs", "Wants", "Savings", "Income"], key="filter_bucket")
    with fc3:
        sort_dir = st.selectbox("Sort", ["Newest first", "Oldest first"], key="sort_dir")

    filtered = [t for t in txns
                if (filter_type == "All" or t["type"] == filter_type)
                and (filter_bucket == "All" or t["bucket"] == filter_bucket)]

    if sort_dir == "Newest first":
        filtered = list(reversed(filtered))

    # Render as styled table
    df = pd.DataFrame(filtered)
    if not df.empty:
        df = df[["date", "type", "bucket", "category", "amount", "note"]]
        df.columns = ["Date", "Type", "Bucket", "Category", "Amount ($)", "Note"]
        df["Amount ($)"] = df["Amount ($)"].map(lambda x: f"${x:,.2f}")

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Date":       st.column_config.TextColumn("Date",       width="medium"),
                "Type":       st.column_config.TextColumn("Type",       width="small"),
                "Bucket":     st.column_config.TextColumn("Bucket",     width="small"),
                "Category":   st.column_config.TextColumn("Category",   width="medium"),
                "Amount ($)": st.column_config.TextColumn("Amount",     width="small"),
                "Note":       st.column_config.TextColumn("Note",       width="large"),
            }
        )

    # Delete last transaction
    if txns:
        with st.expander("🗑️ Delete a transaction"):
            del_idx_options = {
                f"[{i+1}] {t['date']} — {t['type']} | {t['category']} | ${t['amount']:.2f}": i
                for i, t in enumerate(txns)
            }
            del_choice = st.selectbox("Select transaction to delete", list(del_idx_options.keys()), key="del_tx")
            if st.button("Delete", key="del_tx_btn"):
                idx = del_idx_options[del_choice]
                data["sheets"][active_key]["transactions"].pop(idx)
                persist()
                st.rerun()

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("""
<div style='text-align:center;color:#3a3a5c;font-size:0.75rem;padding:8px 0;'>
    Money Tracker · Built with Streamlit & Plotly · Data saved locally to <code>money_tracker_data.json</code>
</div>
""", unsafe_allow_html=True)
