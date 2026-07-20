import pandas as pd
import streamlit as st

st.set_page_config(page_title="Session Delta Dashboard", layout="wide")

GITHUB_RAW_URL = "https://raw.githubusercontent.com/anuj-srivastava2024/Session_delta/main/session_delta.csv"

# ---------- data loading ----------

@st.cache_data(ttl=300)
def load_data(source):
    df = pd.read_csv(source)
    df.columns = [c.strip().lower() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["session"] = df["session"].astype(str).str.upper().str.strip()
    return df

with st.sidebar:
    st.header("Data source")
    mode = st.radio("Load from", ["GitHub (repo default)", "Upload CSV"], index=0)
    if mode == "Upload CSV":
        uploaded = st.file_uploader("session_delta.csv", type="csv")
        df = load_data(uploaded) if uploaded else None
    else:
        try:
            df = load_data(GITHUB_RAW_URL)
        except Exception as e:
            st.error(f"Could not load from GitHub: {e}")
            df = None

if df is None or df.empty:
    st.title("Session delta dashboard")
    st.info("Waiting for data. Upload a CSV or check the GitHub source in the sidebar.")
    st.stop()

# ---------- filters ----------

with st.sidebar:
    st.header("Filters")
    products = sorted(df["product_code"].dropna().unique().tolist())
    product_choice = st.selectbox("Product code", ["All"] + products, index=0)

    dates = sorted(df["date"].unique().tolist())
    date_choice = st.selectbox("Session date", dates, index=len(dates) - 1)

    st.caption(f"{len(df)} rows loaded")

filtered = df[df["date"] == date_choice]
if product_choice != "All":
    filtered = filtered[filtered["product_code"] == product_choice]

# ---------- pivot D vs N per instrument ----------

pivot = filtered.pivot_table(
    index=["instrument", "product_code"],
    columns="session",
    values=["total_delta", "total_volume", "trades", "open", "high", "low", "close"],
    aggfunc="first",
)

contracts = []
for (instrument, product_code), _ in pivot.groupby(level=[0, 1]):
    row = pivot.loc[(instrument, product_code)]
    has_d = ("total_delta", "D") in row.index and pd.notna(row[("total_delta", "D")])
    has_n = ("total_delta", "N") in row.index and pd.notna(row[("total_delta", "N")])
    if not (has_d and has_n):
        continue
    d_delta = row[("total_delta", "D")]
    n_delta = row[("total_delta", "N")]
    contracts.append({
        "instrument": instrument,
        "product_code": product_code,
        "d_delta": d_delta,
        "n_delta": n_delta,
        "net_delta": d_delta + n_delta,
        "d_volume": row[("total_volume", "D")],
        "n_volume": row[("total_volume", "N")],
        "d_trades": row[("trades", "D")],
        "n_trades": row[("trades", "N")],
        "d_close": row[("close", "D")],
        "n_close": row[("close", "N")],
    })

contracts_df = pd.DataFrame(contracts)

# ---------- header ----------

st.title("Session delta dashboard")
st.caption(f"{date_choice} · {product_choice if product_choice != 'All' else 'all products'}")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Contracts (D & N)", len(contracts_df))
if not contracts_df.empty:
    c2.metric("Day delta (sum)", f"{contracts_df['d_delta'].sum():,.0f}")
    c3.metric("Night delta (sum)", f"{contracts_df['n_delta'].sum():,.0f}")
    c4.metric("Total volume", f"{(contracts_df['d_volume'].sum() + contracts_df['n_volume'].sum()):,.0f}")
else:
    c2.metric("Day delta (sum)", "-")
    c3.metric("Night delta (sum)", "-")
    c4.metric("Total volume", "-")

st.divider()

if contracts_df.empty:
    st.warning("No instruments have both a D and N session on this date/product selection.")
    st.stop()

# ---------- quadrant split ----------

def quadrant(row):
    d_pos = row["d_delta"] >= 0
    n_pos = row["n_delta"] >= 0
    if d_pos and n_pos:
        return "pp"
    if not d_pos and not n_pos:
        return "nn"
    if d_pos and not n_pos:
        return "pn"
    return "np"

contracts_df["quadrant"] = contracts_df.apply(quadrant, axis=1)

display_cols = {
    "instrument": "Instrument",
    "product_code": "Product",
    "d_delta": "D delta",
    "n_delta": "N delta",
    "net_delta": "Net delta",
    "d_volume": "D vol",
    "n_volume": "N vol",
    "d_trades": "D trades",
    "n_trades": "N trades",
}

def render_quadrant(col, key, title, help_text, color):
    sub = contracts_df[contracts_df["quadrant"] == key].copy()
    sub = sub.reindex(sub["net_delta"].abs().sort_values(ascending=False).index)
    with col:
        st.markdown(f"**:{color}[{title}]**")
        st.caption(f"{help_text} · {len(sub)} contract{'s' if len(sub) != 1 else ''}")
        if sub.empty:
            st.caption("No contracts")
        else:
            show = sub[list(display_cols.keys())].rename(columns=display_cols)
            st.dataframe(
                show.style.format({
                    "D delta": "{:,.0f}", "N delta": "{:,.0f}", "Net delta": "{:,.0f}",
                    "D vol": "{:,.0f}", "N vol": "{:,.0f}",
                    "D trades": "{:,.0f}", "N trades": "{:,.0f}",
                }),
                use_container_width=True,
                hide_index=True,
                height=min(38 * (len(show) + 1) + 3, 380),
            )

row1a, row1b = st.columns(2)
render_quadrant(row1a, "pp", "D+ / N+", "Bullish both sessions", "green")
render_quadrant(row1b, "nn", "D- / N-", "Bearish both sessions", "red")

row2a, row2b = st.columns(2)
render_quadrant(row2a, "pn", "D+ / N-", "Faded into the night", "orange")
render_quadrant(row2b, "np", "D- / N+", "Reversed into the night", "blue")