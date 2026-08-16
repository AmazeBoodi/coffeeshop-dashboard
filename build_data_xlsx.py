"""
One-off: combine dashboard-repo/data/<ReportFolder>/*.xlsx (per-day files)
into a single dashboard-repo/data.xlsx workbook, one sheet per report type.
Run this locally whenever the per-day snapshot under data/ changes, then
commit the resulting data.xlsx (single file, no GitHub upload-count limit).
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).parent
SRC = ROOT / "data"
OUT = ROOT / "data.xlsx"

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


def load_folder(folder_name: str) -> pd.DataFrame:
    folder = SRC / folder_name
    if not folder.exists():
        return pd.DataFrame()
    files = sorted(folder.glob("*.xlsx"))
    if not files:
        return pd.DataFrame()
    frames = [pd.read_excel(f, engine="openpyxl") for f in files]
    return pd.concat(frames, ignore_index=True)


def main():
    with pd.ExcelWriter(OUT, engine="openpyxl") as writer:
        for sheet, folder in FOLDERS.items():
            df = load_folder(folder)
            if df.empty:
                df = pd.DataFrame({"note": ["no data in range"]})
            df.to_excel(writer, sheet_name=sheet, index=False)
            print(f"{folder:<38} -> sheet '{sheet}': {len(df)} rows")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
