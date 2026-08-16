"""
Shared data-loading layer for the Streamlit dashboard.

Reads the cleaned report files bundled under data/<folder>/*.xlsx in this
repo (a snapshot produced by clean_reports.py on the source machine). This
is a static snapshot for demo purposes - it won't pick up new downloads on
its own. To refresh: regenerate data/ from a fresh clean_reports.py run and
push the updated files.
"""
from pathlib import Path
import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).parent / "data"

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


def _load_folder(folder_name: str) -> pd.DataFrame:
    folder = DATA_DIR / folder_name
    if not folder.exists():
        return pd.DataFrame()
    files = sorted(folder.glob("*.xlsx"))
    if not files:
        return pd.DataFrame()
    frames = []
    for f in files:
        try:
            frames.append(pd.read_excel(f, engine="openpyxl"))
        except Exception as e:
            st.warning(f"Couldn't read {f.name}: {e}")
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)

    if folder_name == "Transaction Report by Time":
        # this report has no real header row in the source at all - the first
        # data row's own text ("Total ", <count>, <count>, <count>) gets read
        # as column names, so pandas ends up with duplicate integer column
        # labels. Rename positionally instead of trusting the header text.
        cols = list(df.columns)
        cols[3:7] = ["Time_Label", "Count_1", "Count_2", "Count_3"][: len(cols) - 3]
        df.columns = cols

    if "Report_Date" in df.columns:
        df["Report_Date"] = pd.to_datetime(df["Report_Date"])
    return df


@st.cache_data(show_spinner="Loading cleaned reports...")
def load_all() -> dict[str, pd.DataFrame]:
    return {key: _load_folder(folder) for key, folder in FOLDERS.items()}


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
