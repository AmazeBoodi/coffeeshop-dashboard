"""
Stream Coffeeshop - Operations Dashboard

Run locally with:
    streamlit run app.py

Reads the cleaned report snapshot bundled in data/ (see data_loader.py).
This is a static demo snapshot, not a live feed - see README.md for how
to refresh it.
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from data_loader import load_all, date_bounds, filter_dates

st.set_page_config(page_title="Stream Coffeeshop Dashboard", page_icon="☕", layout="wide")

# ---------------------------------------------------------------- data ----
dfs = load_all()

with st.sidebar:
    st.title("☕ Stream Coffeeshop")
    if st.button("🔄 Refresh data", use_container_width=True):
        load_all.clear()
        st.rerun()

    min_d, max_d = date_bounds(dfs)
    if min_d is None:
        st.error("No data bundled in data/. See README.md.")
        st.stop()

    st.caption(f"Data available: {min_d} → {max_d}")
    date_range = st.date_input(
        "Date range", value=(min_d, max_d), min_value=min_d, max_value=max_d
    )
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date, end_date = min_d, max_d

    page = st.radio(
        "Section",
        [
            "Overview",
            "Sales & Menu",
            "Complete Report Explorer",
            "Stock Movement",
            "Purchases",
            "Wastage",
            "Voids & Discounts",
            "Transactions by Time",
            "Raw Data Explorer",
        ],
    )

F = {key: filter_dates(df, start_date, end_date) for key, df in dfs.items()}
cr = F["complete_report"]


def money(x):
    if pd.isna(x):
        return "—"
    return f"{x:,.0f}"


def section(df, name):
    return df[df["Section"] == name] if not df.empty else df


# ------------------------------------------------------------- Overview ---
if page == "Overview":
    st.title("Overview")
    st.caption(f"{start_date} → {end_date}")

    stats = section(cr, "Statistics")
    net_sales = stats[(stats["Row_Type"] == "Detail") & (stats["Description"] == "Net Sales")]["Total"].sum() if not stats.empty else 0
    gross_sales = stats[(stats["Row_Type"] == "Detail") & (stats["Description"] == "Gross Sales")]["Total"].sum() if not stats.empty else 0
    n_customers = stats[(stats["Row_Type"] == "Detail") & (stats["Description"] == "Number of Customers")]["Total"].sum() if not stats.empty else 0

    disc = F["discount_by_invoice"]
    total_discounts = disc[disc["Row_Type"] == "Total"]["Discount_Amount"].sum() if not disc.empty else 0

    purch = F["purchase"]
    total_purchases = purch[purch["Row_Type"] == "Detail"]["Total"].sum() if not purch.empty else 0

    siw = F["sales_item_wastage"]
    wr = F["wastage_report"]
    wastage_cost = 0
    if not siw.empty:
        wastage_cost += siw[siw["Row_Type"] == "Detail"]["Total Cost"].sum()
    if not wr.empty:
        wastage_cost += wr[wr["Row_Type"] == "Detail"]["Total Cost"].sum()

    voids = F["summary_of_voids"]
    void_value = voids[voids["Row_Type"] == "Detail"]["Value"].sum() if not voids.empty else 0
    void_count = len(voids[voids["Row_Type"] == "Detail"]) if not voids.empty else 0

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Net Sales", money(net_sales))
    c2.metric("Gross Sales", money(gross_sales))
    c3.metric("Customers", money(n_customers))
    c4.metric("Discounts Given", money(total_discounts))
    c5.metric("Purchases", money(total_purchases))
    c6.metric("Wastage Cost", money(wastage_cost))

    c7, c8 = st.columns(2)
    c7.metric("Void Value", money(void_value))
    c8.metric("Void Count", void_count)

    st.divider()

    if not stats.empty:
        daily = (
            stats[(stats["Row_Type"] == "Detail") & (stats["Description"] == "Net Sales")]
            .groupby("Report_Date")["Total"].sum().reset_index()
        )
        fig = px.line(daily, x="Report_Date", y="Total", title="Net Sales by Day", markers=True)
        fig.update_layout(yaxis_title="Net Sales")
        st.plotly_chart(fig, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        divs = section(cr, "Summary Of Sales By Divisions")
        divs = divs[divs["Row_Type"] == "Detail"] if not divs.empty else divs
        if not divs.empty:
            by_div = divs.groupby("Description")["Total"].sum().sort_values(ascending=False).reset_index()
            fig = px.pie(by_div, names="Description", values="Total", title="Sales by Division", hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
    with col2:
        pay = section(cr, "Summary of Payments")
        pay = pay[pay["Row_Type"] == "Detail"] if not pay.empty else pay
        if not pay.empty:
            by_pay = pay.groupby("Description")["Total"].sum().sort_values(ascending=False).head(10).reset_index()
            fig = px.bar(by_pay, x="Description", y="Total", title="Top Payment / Table Groups")
            st.plotly_chart(fig, use_container_width=True)

# -------------------------------------------------------- Sales & Menu ---
elif page == "Sales & Menu":
    st.title("Sales & Menu")
    me = F["menu_engineering"]
    if me.empty:
        st.info("No Menu Engineering data in range.")
    else:
        me_d = me[me["Row_Type"] == "Detail"]
        agg = me_d.groupby("Menu Item").agg(
            Qty=("Qty", "sum"), Revenue=("Tot Revenue", "sum"), Profit=("Tot Profit", "sum")
        ).reset_index()

        c1, c2, c3 = st.columns(3)
        c1.metric("Items Sold (lines)", int(agg["Qty"].sum()))
        c2.metric("Total Revenue", money(agg["Revenue"].sum()))
        c3.metric("Total Profit", money(agg["Profit"].sum()))

        top_n = st.slider("Top N items", 5, 30, 15)
        top_rev = agg.sort_values("Revenue", ascending=False).head(top_n)
        fig = px.bar(top_rev, x="Menu Item", y="Revenue", title=f"Top {top_n} Items by Revenue")
        st.plotly_chart(fig, use_container_width=True)

        col1, col2 = st.columns(2)
        with col1:
            by_cat = me_d.groupby("Category")["Tot Revenue"].sum().sort_values(ascending=False).reset_index()
            fig = px.pie(by_cat, names="Category", values="Tot Revenue", title="Revenue by Category", hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            fig = px.scatter(
                agg, x="Qty", y="Profit", size="Revenue", hover_name="Menu Item",
                title="Popularity (Qty) vs Profit", size_max=40,
            )
            st.plotly_chart(fig, use_container_width=True)

        with st.expander("Menu class breakdown (Star / Workhorse / Dog / Challenge)"):
            cls_col = "Popularity Cat" if "Popularity Cat" in me_d.columns else None
            if cls_col:
                by_class = me_d.groupby(cls_col)["Tot Revenue"].agg(["count", "sum"]).reset_index()
                by_class.columns = ["Class", "Line Count", "Revenue"]
                st.dataframe(by_class, use_container_width=True, hide_index=True)

        st.subheader("All items")
        st.dataframe(agg.sort_values("Revenue", ascending=False), use_container_width=True, hide_index=True)

# ------------------------------------------------ Complete Report Explorer
elif page == "Complete Report Explorer":
    st.title("Complete Report Explorer")
    st.caption("Every sub-section of the daily 'Complete report' bundle, unified into one table.")

    if cr.empty:
        st.info("No Complete report data in range.")
    else:
        sections = sorted(cr["Section"].dropna().unique())
        chosen = st.selectbox("Section", sections)
        sub = cr[cr["Section"] == chosen]

        show_totals = st.checkbox("Include Total rows", value=True)
        if not show_totals:
            sub = sub[sub["Row_Type"] == "Detail"]

        detail = sub[sub["Row_Type"] == "Detail"]
        if not detail.empty:
            by_desc = detail.groupby("Description")["Total"].sum().sort_values(ascending=False).head(20).reset_index()
            fig = px.bar(by_desc, x="Description", y="Total", title=f"{chosen} — Total by Description (top 20)")
            st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            sub.sort_values(["Report_Date", "Row_ID"]),
            use_container_width=True, hide_index=True,
        )

# --------------------------------------------------------- Stock Movement
elif page == "Stock Movement":
    st.title("Stock Movement")
    sm = F["stock_movement"]
    if sm.empty:
        st.info("No Stock Movement data in range.")
    else:
        col1, col2, col3 = st.columns(3)
        locations = ["All"] + sorted(sm["Location"].dropna().unique().tolist())
        categories = ["All"] + sorted(sm["Category"].dropna().unique().tolist())
        with col1:
            loc = st.selectbox("Location", locations)
        with col2:
            cat = st.selectbox("Category", categories)

        view = sm.copy()
        if loc != "All":
            view = view[view["Location"] == loc]
        if cat != "All":
            view = view[view["Category"] == cat]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Purchases (qty)", money(view["Purchases"].sum()))
        c2.metric("Sales (qty)", money(view["Sales"].sum()))
        c3.metric("Consumption", money(view["Consumption"].sum()))
        c4.metric("Ending Stock Value", money(view["E.S Value"].sum()))

        top_products = (
            view.groupby("Product")["Consumption"].sum().sort_values(ascending=False).head(20).reset_index()
        )
        if not top_products.empty:
            fig = px.bar(top_products, x="Product", y="Consumption", title="Top 20 Products by Consumption")
            st.plotly_chart(fig, use_container_width=True)

        st.subheader("Track a product over time")
        products = sorted(view["Product"].dropna().unique())
        if products:
            pick = st.selectbox("Product", products)
            trend = view[view["Product"] == pick].groupby("Report_Date")[["Ending Stock", "Purchases", "Sales"]].sum().reset_index()
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=trend["Report_Date"], y=trend["Ending Stock"], name="Ending Stock", mode="lines+markers"))
            fig.add_trace(go.Bar(x=trend["Report_Date"], y=trend["Purchases"], name="Purchases"))
            fig.add_trace(go.Bar(x=trend["Report_Date"], y=trend["Sales"], name="Sales"))
            fig.update_layout(title=f"{pick} — Stock, Purchases & Sales", barmode="group")
            st.plotly_chart(fig, use_container_width=True)

        st.dataframe(view.sort_values("Report_Date"), use_container_width=True, hide_index=True)

# ------------------------------------------------------------- Purchases -
elif page == "Purchases":
    st.title("Purchases")
    purch = F["purchase"]
    if purch.empty:
        st.info("No Purchase data in range.")
    else:
        d = purch[purch["Row_Type"] == "Detail"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Spend", money(d["Total"].sum()))
        c2.metric("Line Items", len(d))
        c3.metric("Suppliers", d["Supplier"].nunique())

        daily = d.groupby("Report_Date")["Total"].sum().reset_index()
        fig = px.line(daily, x="Report_Date", y="Total", title="Purchase Spend by Day", markers=True)
        st.plotly_chart(fig, use_container_width=True)

        col1, col2 = st.columns(2)
        with col1:
            by_sup = d.groupby("Supplier")["Total"].sum().sort_values(ascending=False).head(10).reset_index()
            fig = px.bar(by_sup, x="Supplier", y="Total", title="Top 10 Suppliers by Spend")
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            by_prod = d.groupby("Product Description")["Total"].sum().sort_values(ascending=False).head(10).reset_index()
            fig = px.bar(by_prod, x="Product Description", y="Total", title="Top 10 Products by Spend")
            st.plotly_chart(fig, use_container_width=True)

        st.dataframe(d.sort_values("Report_Date"), use_container_width=True, hide_index=True)

# --------------------------------------------------------------- Wastage -
elif page == "Wastage":
    st.title("Wastage")
    siw = F["sales_item_wastage"]
    wr = F["wastage_report"]

    siw_d = siw[siw["Row_Type"] == "Detail"] if not siw.empty else siw
    wr_d = wr[wr["Row_Type"] == "Detail"] if not wr.empty else wr

    c1, c2 = st.columns(2)
    c1.metric("Sales-Item Wastage Cost", money(siw_d["Total Cost"].sum()) if not siw_d.empty else "—")
    c2.metric("Inventory Wastage Cost", money(wr_d["Total Cost"].sum()) if not wr_d.empty else "—")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Sales-item wastage (given away / comped)")
        if not siw_d.empty:
            by_remark = siw_d.groupby("Remark")["Total Cost"].sum().sort_values(ascending=False).reset_index()
            fig = px.pie(by_remark, names="Remark", values="Total Cost", title="Wastage by Reason", hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
            top = siw_d.groupby("Product Description")["Total Cost"].sum().sort_values(ascending=False).head(10).reset_index()
            fig = px.bar(top, x="Product Description", y="Total Cost", title="Top 10 Items")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No data in range.")
    with col2:
        st.subheader("Inventory wastage")
        if not wr_d.empty:
            top = wr_d.groupby("Product Description")["Total Cost"].sum().sort_values(ascending=False).head(10).reset_index()
            fig = px.bar(top, x="Product Description", y="Total Cost", title="Top 10 Wasted Products")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No data in range.")

    st.subheader("Detail")
    tab1, tab2 = st.tabs(["Sales item wastage", "Wastage Report"])
    tab1.dataframe(siw_d.sort_values("Report_Date") if not siw_d.empty else siw_d, use_container_width=True, hide_index=True)
    tab2.dataframe(wr_d.sort_values("Report_Date") if not wr_d.empty else wr_d, use_container_width=True, hide_index=True)

# --------------------------------------------------------- Voids & Disc. -
elif page == "Voids & Discounts":
    st.title("Voids & Discounts")
    voids = F["summary_of_voids"]
    disc = F["discount_by_invoice"]

    voids_d = voids[voids["Row_Type"] == "Detail"] if not voids.empty else voids
    disc_inv = disc[disc["Row_Type"] == "Invoice"] if not disc.empty else disc

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Voids")
        c1, c2 = st.columns(2)
        c1.metric("Void Value", money(voids_d["Value"].sum()) if not voids_d.empty else "—")
        c2.metric("Void Count", len(voids_d))
        if not voids_d.empty:
            by_server = voids_d.groupby("Server")["Value"].agg(["count", "sum"]).sort_values("sum", ascending=False).reset_index()
            by_server.columns = ["Server", "Void Count", "Void Value"]
            fig = px.bar(by_server, x="Server", y="Void Value", title="Voids by Server")
            st.plotly_chart(fig, use_container_width=True)
        st.dataframe(voids_d.sort_values("Report_Date") if not voids_d.empty else voids_d, use_container_width=True, hide_index=True)

    with col2:
        st.subheader("Discounts")
        c1, c2 = st.columns(2)
        c1.metric("Invoices Discounted", len(disc_inv))
        c2.metric("Total Discount", money(disc_inv["Discount_Amount"].sum()) if not disc_inv.empty else "—")
        if not disc_inv.empty:
            by_emp = disc_inv.groupby("Employee")["Discount_Amount"].agg(["count", "sum"]).sort_values("sum", ascending=False).reset_index()
            by_emp.columns = ["Employee", "Invoices", "Total Discount"]
            fig = px.bar(by_emp, x="Employee", y="Total Discount", title="Discounts by Employee")
            st.plotly_chart(fig, use_container_width=True)
        st.dataframe(disc.sort_values(["Report_Date", "Row_ID"]) if not disc.empty else disc, use_container_width=True, hide_index=True)

# ------------------------------------------------------- Transactions ----
elif page == "Transactions by Time":
    st.title("Transactions by Time")
    tt = F["transaction_by_time"]
    if tt.empty:
        st.info("No data in range.")
    else:
        det = tt[tt["Row_Type"] == "Detail"].copy()
        det["Hour"] = det["Time_Label"].astype(str).str.slice(0, 2)

        c1, c2 = st.columns(2)
        totals = tt[tt["Row_Type"] == "Total"]
        c1.metric("Total Transactions in Range", int(totals["Count_1"].sum()))
        c2.metric("Days with Data", tt["Report_Date"].nunique())

        by_hour = det.groupby("Hour")["Count_1"].sum().reset_index()
        fig = px.bar(by_hour, x="Hour", y="Count_1", title="Transactions by Hour of Day (summed across range)")
        st.plotly_chart(fig, use_container_width=True)

        daily = totals.groupby("Report_Date")["Count_1"].sum().reset_index()
        fig = px.line(daily, x="Report_Date", y="Count_1", title="Transactions by Day", markers=True)
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(det.sort_values(["Report_Date", "Time_Label"]), use_container_width=True, hide_index=True)

# ---------------------------------------------------------- Raw Explorer -
elif page == "Raw Data Explorer":
    st.title("Raw Data Explorer")
    st.caption("Browse any cleaned report type directly, filtered to the selected date range.")

    from data_loader import FOLDERS
    label_to_key = {v: k for k, v in FOLDERS.items()}
    chosen = st.selectbox("Report type", list(label_to_key.keys()))
    df = F[label_to_key[chosen]]

    if df.empty:
        st.info("No data in range for this report type.")
    else:
        if "Row_Type" in df.columns:
            types = ["All"] + sorted(df["Row_Type"].dropna().unique().tolist())
            rt = st.selectbox("Row_Type", types)
            if rt != "All":
                df = df[df["Row_Type"] == rt]

        st.write(f"{len(df):,} rows")
        st.dataframe(df.sort_values("Report_Date") if "Report_Date" in df.columns else df,
                      use_container_width=True, hide_index=True)

        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("Download filtered CSV", csv, f"{chosen}.csv", "text/csv")
