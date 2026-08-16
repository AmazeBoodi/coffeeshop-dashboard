"""
Shared data-loading layer for the Streamlit dashboard.

Reads data.xlsx in this repo - one sheet per report type, produced by
build_data_xlsx.py from a cleaned per-day snapshot. This is a static demo
snapshot, not a live feed. To refresh: rerun build_data_xlsx.py against an
updated data/ snapshot, then commit the new data.xlsx.
"""
from pathlib import Path
import pandas as pd
import streamlit as st

DATA_FILE = Path(__file__).parent / "data.xlsx"

FOLDERS = {
    "complete_report": "Complete report",
    "details_of_refunds": "Details of refunds",
    "discount_by_invoice": "Discount by Invoice with Details",
    "menu_engineering": "Menu Engineering",
    "purchase": "Purchase With all Details",
    "sales_item_wastage": "Sales item wastage",
    "stock_movement": "Stock Movement",
    "summary_of_voids": "Summary of voids",
    "transaction_by_time": "Transaction Report by Time",
    "wastage_report": "Wastage Report",
}


@st.cache_data(show_spinner="Loading cleaned reports...")
def load_all() -> dict[str, pd.DataFrame]:
    if not DATA_FILE.exists():
        return {key: pd.DataFrame() for key in FOLDERS}

    sheets = pd.read_excel(DATA_FILE, sheet_name=None, engine="openpyxl")
    out = {}
    for key, folder_name in FOLDERS.items():
        df = sheets.get(key, pd.DataFrame())
        if "note" in df.columns:  # placeholder for an empty report type
            df = pd.DataFrame()

        if not df.empty and folder_name == "Transaction Report by Time":
            # this report has no real header row in the source at all - the
            # first data row's own text ("Total ", <count>, <count>, <count>)
            # gets read as column names, so pandas ends up with duplicate
            # integer column labels. Rename positionally instead.
            cols = list(df.columns)
            cols[3:7] = ["Time_Label", "Count_1", "Count_2", "Count_3"][: len(cols) - 3]
            df.columns = cols

        if "Report_Date" in df.columns:
            df["Report_Date"] = pd.to_datetime(df["Report_Date"])
        out[key] = df
    return out


def date_bounds(dfs: dict[str, pd.DataFrame]):
    dates = [
        df["Report_Date"] for df in dfs.values()
        if not df.empty and "Report_Date" in df.columns and df["Report_Date"].notna().any()
    ]
    if not dates:
        return None, None
    all_dates = pd.concat(dates)
    return all_dates.min().date(), all_dates.max().date()


def filter_dates(df: pd.DataFrame, start, end) -> pd.DataFrame:
    if df.empty or "Report_Date" not in df.columns:
        return df
    mask = (df["Report_Date"].dt.date >= start) & (df["Report_Date"].dt.date <= end)
    return df[mask]
