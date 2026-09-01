"""
Groq-powered "Ask AI" chat over the dashboard's current filtered data.

Never sends raw row-level data to the model - Stock Movement alone can be
13,000+ rows for the full range, which would blow the context window and
cost real money on every question. Instead build_context() produces a
compact aggregated digest (KPIs, top items, breakdowns, a daily trend) from
whatever's currently filtered, so token usage stays bounded regardless of
date range or filters, and the model only ever sees numbers already surfaced
elsewhere in the dashboard.

Coverage is deliberately not exhaustive - this is a testing-phase digest
built against a small demo dataset. When real, larger data comes in, this
should be revisited rather than assumed to already cover everything.

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


def _headline_kpis(Fx: dict) -> dict:
    """Just the top-level numbers for one period. Used both for the main
    digest and (compact, no item-level detail) for a comparison period -
    sending the full breakdown twice would double the digest's size for
    every question asked while comparison mode is on."""
    out = {}
    cr = Fx.get("complete_report", pd.DataFrame())
    if not cr.empty:
        stats = cr[(cr["Section"] == "Statistics") & (cr["Row_Type"] == "Detail")]
        for desc in ["Net Sales", "Gross Sales", "Number of Customers"]:
            out[desc] = stats[stats["Description"] == desc]["Total"].sum()
    else:
        out["Net Sales"] = out["Gross Sales"] = out["Number of Customers"] = 0

    disc_all = Fx.get("discount_by_invoice", pd.DataFrame())
    out["Discounts Given"] = (
        disc_all[disc_all["Row_Type"] == "Total"]["Discount_Amount"].sum() if not disc_all.empty else 0
    )

    purch = Fx.get("purchase", pd.DataFrame())
    pd_d = purch[purch["Row_Type"] == "Detail"] if not purch.empty else purch
    out["Purchases"] = pd_d["Total"].sum() if not pd_d.empty else 0

    siw = Fx.get("sales_item_wastage", pd.DataFrame())
    wr = Fx.get("wastage_report", pd.DataFrame())
    wcost = 0
    if not siw.empty:
        wcost += siw[siw["Row_Type"] == "Detail"]["Total Cost"].sum()
    if not wr.empty:
        wcost += wr[wr["Row_Type"] == "Detail"]["Total Cost"].sum()
    out["Wastage Cost"] = wcost

    voids = Fx.get("summary_of_voids", pd.DataFrame())
    v_d = voids[voids["Row_Type"] == "Detail"] if not voids.empty else voids
    out["Void Value"] = v_d["Value"].sum() if not v_d.empty else 0
    out["Void Count"] = len(v_d) if not v_d.empty else 0

    tt = Fx.get("transaction_by_time", pd.DataFrame())
    tot = tt[tt["Row_Type"] == "Total"] if not tt.empty else tt
    out["Total Transactions"] = tot["Count_1"].sum() if not tot.empty else 0

    return out


def build_context(
    F, start_date, end_date, weekday_filter=None,
    Fp=None, prev_start=None, prev_end=None,
) -> str:
    """Compact text digest of the currently-filtered data, for the model's
    system prompt. Mirrors the numbers already shown on the dashboard pages -
    the assistant should never see, and therefore never invent, anything the
    user couldn't also see themselves.

    weekday_filter: the sidebar's active Day-of-week selection, if any - the
        digest already reflects it in every number below, but the assistant
        needs to be TOLD it's active, or a "why is this low" question gets
        answered without the one piece of context that explains it.
    Fp/prev_start/prev_end: the comparison period's filtered data, if compare
        mode is on - without this, "how does this compare to last month" is
        unanswerable even when the dashboard itself is showing the comparison.
    """
    lines = [f"Date range: {start_date} to {end_date}"]
    lines.append(
        f"Active filters: Day of week = {', '.join(weekday_filter)}"
        if weekday_filter else "Active filters: none (viewing every day of the week)"
    )

    cr = F.get("complete_report", pd.DataFrame())
    if not cr.empty:
        stats = cr[(cr["Section"] == "Statistics") & (cr["Row_Type"] == "Detail")]
        lines.append("\n== Headline KPIs ==")
        # Net Sales / Gross Sales / Number of Customers come from the same
        # Statistics section the Overview page reads. Deliberately NOT using
        # Statistics' own "Discount" figure here - it's a different number
        # from what Overview shows (which sums discount_by_invoice's actual
        # Total rows). Both are surfaced further down, clearly labeled, so
        # the assistant can explain the discrepancy instead of picking one
        # silently.
        for desc in ["Net Sales", "Gross Sales", "Tax", "Number of Customers"]:
            v = stats[stats["Description"] == desc]["Total"].sum()
            lines.append(f"{desc}: {v:,.0f}")
        disc_all = F.get("discount_by_invoice", pd.DataFrame())
        if not disc_all.empty:
            disc_total = disc_all[disc_all["Row_Type"] == "Total"]["Discount_Amount"].sum()
            lines.append(f"Discounts Given (from Discount by Invoice report): {disc_total:,.0f}")
        internal_disc = stats[stats["Description"].str.contains("Discount", case=False, na=False)]["Total"].sum()
        if internal_disc:
            lines.append(
                f"Complete Report's own internal 'Discount' statistic: {internal_disc:,.0f} "
                f"(a different figure from the same POS's own summary section - if asked, "
                f"note both exist and may not match)"
            )

        divs = _section(cr, "Summary Of Sales By Divisions")
        divs = divs[divs["Row_Type"] == "Detail"] if not divs.empty else divs
        if not divs.empty:
            lines.append("\n== Sales by Division ==")
            by_div = divs.groupby("Description")["Total"].sum().sort_values(ascending=False)
            for desc, total in by_div.items():
                lines.append(f"{desc}: {total:,.0f}")

        cats = _section(cr, "Summary Of Sales By Categories")
        cats = cats[cats["Row_Type"] == "Detail"] if not cats.empty else cats
        if not cats.empty:
            lines.append("\n== Sales by Category (Complete Report) ==")
            by_catsec = cats.groupby("Description")["Total"].sum().sort_values(ascending=False)
            for desc, total in by_catsec.items():
                lines.append(f"{desc}: {total:,.0f}")

        pay = _section(cr, "Summary of Payments")
        pay = pay[pay["Row_Type"] == "Detail"] if not pay.empty else pay
        if not pay.empty:
            lines.append("\n== Payment / Table Groups ==")
            by_pay = pay.groupby("Description")["Total"].sum().sort_values(ascending=False).head(10)
            for desc, total in by_pay.items():
                lines.append(f"{desc}: {total:,.0f}")

        servers = _section(cr, "Summary of Servers")
        servers = servers[servers["Row_Type"] == "Detail"] if not servers.empty else servers
        if not servers.empty:
            lines.append("\n== Summary of Servers (Complete Report) ==")
            by_srv = servers.groupby("Description")["Total"].sum().sort_values(ascending=False)
            for desc, total in by_srv.items():
                lines.append(f"{desc}: {total:,.0f}")

        tax = _section(cr, "Tax Report")
        tax = tax[tax["Row_Type"] == "Detail"] if not tax.empty else tax
        by_tax = tax.groupby("Description")["Total"].sum().sort_values(ascending=False) if not tax.empty else pd.Series(dtype=float)
        if not by_tax.empty:
            lines.append("\n== Tax Report (Complete Report) ==")
            for desc, total in by_tax.items():
                lines.append(f"{desc}: {total:,.0f}")
        else:
            lines.append("\n== Tax Report: no tax data recorded for this business (no VAT/tax configured) ==")

        daily = stats[stats["Description"] == "Net Sales"].groupby("Report_Date")["Total"].sum().sort_index()
        if not daily.empty:
            lines.append("\n== Net Sales by Day ==")
            for d, v in daily.items():
                lines.append(f"{d.date()}: {v:,.0f}")

    tt = F.get("transaction_by_time", pd.DataFrame())
    if not tt.empty:
        tot = tt[tt["Row_Type"] == "Total"]
        det = tt[tt["Row_Type"] == "Detail"].copy()
        total_txn = tot["Count_1"].sum() if not tot.empty else 0
        lines.append(f"\n== Transactions by Time: {total_txn:,.0f} total transactions ==")
        if not det.empty:
            # split on ':' rather than slicing the first 2 chars - a single-
            # digit hour like "9:14" has no leading zero, so slice(0,2) grabs
            # "9:" instead of the hour, producing a garbled "9::00" label.
            det["Hour"] = det["Time_Label"].astype(str).str.split(":").str[0].str.zfill(2)
            by_hour = det.groupby("Hour")["Count_1"].sum().sort_index()
            lines.append("By hour of day (24h, summed across the whole range):")
            for hr, c in by_hour.items():
                lines.append(f"{hr}:00 - {c:,.0f} transactions")
        if not tot.empty:
            daily_txn = tot.groupby("Report_Date")["Count_1"].sum().sort_index()
            lines.append("By day:")
            for d, c in daily_txn.items():
                lines.append(f"{d.date()}: {c:,.0f} transactions")

    me = F.get("menu_engineering", pd.DataFrame())
    if not me.empty:
        me_d = me[me["Row_Type"] == "Detail"]
        by_item = me_d.groupby("Menu Item")["Tot Revenue"].sum().sort_values(ascending=False)
        top_n = 25
        top = by_item.head(top_n)
        lines.append(f"\n== Top {min(top_n, len(by_item))} Menu Items by Revenue ==")
        for item, rev in top.items():
            lines.append(f"{item}: {rev:,.0f}")
        if len(by_item) > top_n:
            rest_rev = by_item.iloc[top_n:].sum()
            total_rev = by_item.sum()
            lines.append(
                f"...plus {len(by_item) - top_n} more menu items not listed individually, "
                f"totaling {rest_rev:,.0f} ({rest_rev / total_rev * 100:.1f}% of menu revenue) "
                f"- if asked about one of them by name, say the total is known but this item "
                f"isn't broken out, rather than guessing its individual figure."
            )

        by_cat = me_d.groupby("Category")["Tot Revenue"].sum().sort_values(ascending=False)
        if not by_cat.empty:
            lines.append("\n== Revenue by Menu Category ==")
            for cat, rev in by_cat.items():
                lines.append(f"{cat}: {rev:,.0f}")

        if "Menu Item Class" in me_d.columns:
            by_class = me_d.groupby("Menu Item Class").agg(
                Items=("Menu Item", "nunique"), Revenue=("Tot Revenue", "sum"), Profit=("Tot Profit", "sum"),
            ).sort_values("Revenue", ascending=False)
            if not by_class.empty:
                lines.append(
                    "\n== Menu Engineering Classification (Star=high popularity+high profit, "
                    "Workhorse=high popularity+low profit, Challenge=low popularity+high profit, "
                    "Dog=low popularity+low profit) =="
                )
                for cls, row in by_class.iterrows():
                    lines.append(f"{cls}: {row['Items']:.0f} distinct items, revenue {row['Revenue']:,.0f}, profit {row['Profit']:,.0f}")

        # Per-day top seller - without this, "what sold best on <date>" is
        # unanswerable from the totals-only sections above (confirmed: an
        # earlier version of this digest caused the assistant to wrongly
        # claim per-day item data didn't exist, when it just wasn't included
        # here). One short line per day stays cheap even across a full range.
        top_by_day = (
            me_d.sort_values("Qty", ascending=False)
            .drop_duplicates(subset="Report_Date", keep="first")[["Report_Date", "Menu Item", "Qty"]]
            .sort_values("Report_Date")
        )
        if not top_by_day.empty:
            lines.append("\n== Top-Selling Item by Day (by quantity sold) ==")
            for _, r in top_by_day.iterrows():
                lines.append(f"{r['Report_Date'].date()}: {r['Menu Item']} ({r['Qty']:.0f} sold)")

    purch = F.get("purchase", pd.DataFrame())
    if not purch.empty:
        pd_d = purch[purch["Row_Type"] == "Detail"]
        if not pd_d.empty:
            lines.append(f"\n== Purchases: total spend {pd_d['Total'].sum():,.0f}, {len(pd_d)} line items ==")
            by_sup = pd_d.groupby("Supplier")["Total"].sum().sort_values(ascending=False)
            lines.append("By supplier:")
            for sup, total in by_sup.items():
                lines.append(f"{sup}: {total:,.0f}")
            by_prod = pd_d.groupby("Product Description")["Total"].sum().sort_values(ascending=False).head(15)
            lines.append("Top 15 products by purchase spend:")
            for prod, total in by_prod.items():
                lines.append(f"{prod}: {total:,.0f}")

    siw = F.get("sales_item_wastage", pd.DataFrame())
    wr = F.get("wastage_report", pd.DataFrame())
    siw_d = siw[siw["Row_Type"] == "Detail"] if not siw.empty else siw
    wr_d = wr[wr["Row_Type"] == "Detail"] if not wr.empty else wr
    wcost = (siw_d["Total Cost"].sum() if not siw_d.empty else 0) + (wr_d["Total Cost"].sum() if not wr_d.empty else 0)
    lines.append(f"\n== Total Wastage Cost: {wcost:,.0f} ==")
    if not siw_d.empty:
        lines.append("Sales-item wastage (given away / comped) by reason:")
        by_remark = siw_d.groupby("Remark")["Total Cost"].sum().sort_values(ascending=False)
        for remark, cost in by_remark.items():
            lines.append(f"{remark}: {cost:,.0f}")
        top_siw = siw_d.groupby("Product Description")["Total Cost"].sum().sort_values(ascending=False).head(10)
        lines.append("Top 10 sales-item wastage products:")
        for p, c in top_siw.items():
            lines.append(f"{p}: {c:,.0f}")
    if not wr_d.empty:
        top_wr = wr_d.groupby("Product Description")["Total Cost"].sum().sort_values(ascending=False).head(10)
        lines.append("Top 10 inventory wastage products (Wastage Report):")
        for p, c in top_wr.items():
            lines.append(f"{p}: {c:,.0f}")

    voids = F.get("summary_of_voids", pd.DataFrame())
    if not voids.empty:
        v_d = voids[voids["Row_Type"] == "Detail"]
        if not v_d.empty:
            lines.append(f"\n== Voids: {len(v_d)} voids, total value {v_d['Value'].sum():,.0f} ==")
            by_server = v_d.groupby("Server")["Value"].sum().sort_values(ascending=False)
            lines.append("By server:")
            for s, v in by_server.items():
                lines.append(f"{s}: {v:,.0f}")
            if "Description" in v_d.columns:
                by_reason = v_d.groupby("Description")["Value"].agg(["count", "sum"]).sort_values("sum", ascending=False).head(10)
                lines.append("Top 10 voided items / reasons:")
                for desc, row in by_reason.iterrows():
                    lines.append(f"{desc}: {int(row['count'])} times, {row['sum']:,.0f}")

    disc = F.get("discount_by_invoice", pd.DataFrame())
    if not disc.empty:
        d_inv = disc[disc["Row_Type"] == "Invoice"]
        if not d_inv.empty:
            lines.append(f"\n== Discounts: {len(d_inv)} invoices discounted, total {d_inv['Discount_Amount'].sum():,.0f} ==")
            by_emp = d_inv.groupby("Employee")["Discount_Amount"].sum().sort_values(ascending=False)
            lines.append("By employee:")
            for e, v in by_emp.items():
                lines.append(f"{e}: {v:,.0f}")
        d_lines = disc[disc["Row_Type"] == "Detail"]
        if not d_lines.empty and "Product_Description" in d_lines.columns:
            by_prod = d_lines.groupby("Product_Description")["Qty"].sum().sort_values(ascending=False).head(10)
            lines.append("Top 10 discounted products by quantity:")
            for p, q in by_prod.items():
                lines.append(f"{p}: {q:,.0f} units")

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
        by_cat_sm = sm.groupby("Category")["Consumption"].sum().sort_values(ascending=False)
        if not by_cat_sm.empty:
            lines.append("Consumption by stock category:")
            for cat, c in by_cat_sm.items():
                lines.append(f"{cat}: {c:,.0f}")
        by_div_sm = sm.groupby("Division")["Consumption"].sum().sort_values(ascending=False).head(15)
        if not by_div_sm.empty:
            lines.append("Consumption by division (top 15):")
            for div, c in by_div_sm.items():
                lines.append(f"{div}: {c:,.0f}")

    if Fp is not None:
        cur_kpi = _headline_kpis(F)
        prev_kpi = _headline_kpis(Fp)
        lines.append(f"\n== Comparison Period: {prev_start} to {prev_end} (headline KPIs only, no item-level breakdown) ==")
        for k in cur_kpi:
            cv, pv = cur_kpi[k], prev_kpi.get(k, 0)
            delta = f", change {(cv - pv) / pv * 100:+.1f}%" if pv else ""
            lines.append(f"{k}: current period {cv:,.0f}, comparison period {pv:,.0f}{delta}")

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
