"""
Groq-powered "Ask AI" chat over the dashboard's current filtered data.

Never sends raw row-level data to the model - Stock Movement alone can be
13,000+ rows for the full range, which would blow the context window and
cost real money on every question. Instead build_context() produces a
compact aggregated digest (KPIs, top items, breakdowns, a daily trend) from
whatever's currently filtered, so token usage stays bounded regardless of
date range or filters, and the model only ever sees numbers already surfaced
elsewhere in the dashboard.

API key comes from st.secrets["GROQ_API_KEY"] - never hardcoded, never
committed. See .streamlit/secrets.toml.example and README.md for setup.
"""
import pandas as pd
import streamlit as st

# Groq retires/renames models without much notice, and which ones an
# account/tier can actually reach varies. Rather than hardcode one and break
# on the next deprecation, try each in order and stick with the first that
# works, cached per session so it's only re-probed once.
CANDIDATE_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "gemma2-9b-it",
]


def get_client():
    """A Groq client, or None if no key is configured."""
    try:
        api_key = st.secrets.get("GROQ_API_KEY")
    except Exception:
        api_key = None
    if not api_key:
        return None
    from groq import Groq
    return Groq(api_key=api_key)


def _section(df, name):
    return df[df["Section"] == name] if not df.empty else df


def build_context(F, start_date, end_date) -> str:
    """Compact text digest of the currently-filtered data, for the model's
    system prompt. Mirrors the numbers already shown on the dashboard pages -
    the assistant should never see, and therefore never invent, anything the
    user couldn't also see themselves."""
    lines = [f"Date range: {start_date} to {end_date}"]

    cr = F.get("complete_report", pd.DataFrame())
    if not cr.empty:
        stats = cr[(cr["Section"] == "Statistics") & (cr["Row_Type"] == "Detail")]
        lines.append("\n== Headline KPIs ==")
        # Net Sales / Gross Sales / Number of Customers come from the same
        # Statistics section the Overview page reads. Deliberately NOT using
        # Statistics' own "Discount" figure here - it's a different number
        # from what Overview shows (which sums discount_by_invoice's actual
        # Total rows), and showing both would give the assistant two
        # conflicting "discount" numbers for the same period.
        for desc in ["Net Sales", "Gross Sales", "Tax", "Number of Customers"]:
            v = stats[stats["Description"] == desc]["Total"].sum()
            lines.append(f"{desc}: {v:,.0f}")
        disc_all = F.get("discount_by_invoice", pd.DataFrame())
        if not disc_all.empty:
            disc_total = disc_all[disc_all["Row_Type"] == "Total"]["Discount_Amount"].sum()
            lines.append(f"Discounts Given: {disc_total:,.0f}")

        divs = _section(cr, "Summary Of Sales By Divisions")
        divs = divs[divs["Row_Type"] == "Detail"] if not divs.empty else divs
        if not divs.empty:
            lines.append("\n== Sales by Division ==")
            by_div = divs.groupby("Description")["Total"].sum().sort_values(ascending=False)
            for desc, total in by_div.items():
                lines.append(f"{desc}: {total:,.0f}")

        pay = _section(cr, "Summary of Payments")
        pay = pay[pay["Row_Type"] == "Detail"] if not pay.empty else pay
        if not pay.empty:
            lines.append("\n== Payment / Table Groups ==")
            by_pay = pay.groupby("Description")["Total"].sum().sort_values(ascending=False).head(10)
            for desc, total in by_pay.items():
                lines.append(f"{desc}: {total:,.0f}")

        daily = stats[stats["Description"] == "Net Sales"].groupby("Report_Date")["Total"].sum().sort_index()
        if not daily.empty:
            lines.append("\n== Net Sales by Day ==")
            for d, v in daily.items():
                lines.append(f"{d.date()}: {v:,.0f}")

    me = F.get("menu_engineering", pd.DataFrame())
    if not me.empty:
        me_d = me[me["Row_Type"] == "Detail"]
        top = me_d.groupby("Menu Item")["Tot Revenue"].sum().sort_values(ascending=False).head(15)
        lines.append("\n== Top 15 Menu Items by Revenue ==")
        for item, rev in top.items():
            lines.append(f"{item}: {rev:,.0f}")
        by_cat = me_d.groupby("Category")["Tot Revenue"].sum().sort_values(ascending=False)
        if not by_cat.empty:
            lines.append("\n== Revenue by Menu Category ==")
            for cat, rev in by_cat.items():
                lines.append(f"{cat}: {rev:,.0f}")

    purch = F.get("purchase", pd.DataFrame())
    if not purch.empty:
        pd_d = purch[purch["Row_Type"] == "Detail"]
        if not pd_d.empty:
            lines.append(f"\n== Purchases: total spend {pd_d['Total'].sum():,.0f}, {len(pd_d)} line items ==")
            by_sup = pd_d.groupby("Supplier")["Total"].sum().sort_values(ascending=False)
            for sup, total in by_sup.items():
                lines.append(f"{sup}: {total:,.0f}")

    siw = F.get("sales_item_wastage", pd.DataFrame())
    wr = F.get("wastage_report", pd.DataFrame())
    wcost = 0
    if not siw.empty:
        wcost += siw[siw["Row_Type"] == "Detail"]["Total Cost"].sum()
    if not wr.empty:
        wcost += wr[wr["Row_Type"] == "Detail"]["Total Cost"].sum()
    lines.append(f"\n== Total Wastage Cost: {wcost:,.0f} ==")

    voids = F.get("summary_of_voids", pd.DataFrame())
    if not voids.empty:
        v_d = voids[voids["Row_Type"] == "Detail"]
        if not v_d.empty:
            lines.append(f"\n== Voids: {len(v_d)} voids, total value {v_d['Value'].sum():,.0f} ==")
            by_server = v_d.groupby("Server")["Value"].sum().sort_values(ascending=False)
            for s, v in by_server.items():
                lines.append(f"{s}: {v:,.0f}")

    disc = F.get("discount_by_invoice", pd.DataFrame())
    if not disc.empty:
        d_inv = disc[disc["Row_Type"] == "Invoice"]
        if not d_inv.empty:
            lines.append(f"\n== Discounts: {len(d_inv)} invoices discounted, total {d_inv['Discount_Amount'].sum():,.0f} ==")
            by_emp = d_inv.groupby("Employee")["Discount_Amount"].sum().sort_values(ascending=False)
            for e, v in by_emp.items():
                lines.append(f"{e}: {v:,.0f}")

    sm = F.get("stock_movement", pd.DataFrame())
    if not sm.empty:
        lines.append(
            f"\n== Stock Movement: {sm['Purchases'].sum():,.0f} purchased, "
            f"{sm['Sales'].sum():,.0f} sold, {sm['Consumption'].sum():,.0f} consumed "
            f"(units), ending stock value {sm['E.S Value'].sum():,.0f} =="
        )
        top_consumed = sm.groupby("Product")["Consumption"].sum().sort_values(ascending=False).head(10)
        lines.append("Top 10 products by consumption:")
        for p, c in top_consumed.items():
            lines.append(f"{p}: {c:,.0f}")

    return "\n".join(lines)


def ask(question: str, context: str, history: list[tuple[str, str]]):
    """Returns (answer, error) - exactly one is None."""
    client = get_client()
    if client is None:
        return None, (
            "No Groq API key configured. Add `GROQ_API_KEY` to "
            "`.streamlit/secrets.toml` locally, or under **App settings → "
            "Secrets** on Streamlit Community Cloud."
        )

    system = (
        "You are a data analyst assistant embedded in a coffee shop's operations "
        "dashboard. Answer questions using ONLY the summarized data below - never "
        "invent or estimate a number that isn't there. If the data doesn't cover "
        "what's asked, say so plainly rather than guessing. Be concise, cite the "
        "actual figures, and format money with thousands separators.\n\n"
        f"=== CURRENT DASHBOARD DATA (already filtered to the user's selected "
        f"date range and filters) ===\n{context}"
    )
    messages = [{"role": "system", "content": system}]
    for role, content in history:
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": question})

    working_model = st.session_state.get("_groq_working_model")
    models_to_try = [working_model] if working_model else CANDIDATE_MODELS
    last_error = None

    for model in models_to_try:
        try:
            resp = client.chat.completions.create(
                model=model, messages=messages, temperature=0.2, max_tokens=800,
            )
            st.session_state["_groq_working_model"] = model
            return resp.choices[0].message.content, None
        except Exception as e:
            last_error = e
            msg = str(e).lower()
            if "model_not_found" in msg or "does not exist" in msg:
                continue  # try the next candidate
            break  # a different kind of failure (auth, rate limit, network) - stop trying models

    return None, f"Groq request failed: {last_error}"
