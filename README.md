# Coffee Shop Operations Dashboard

Streamlit dashboard over Omega POS export data (sales, menu engineering,
stock movement, purchases, wastage, voids, discounts, transactions).

**This repo bundles a static data snapshot** (`data.xlsx`, one sheet per
report type) covering 2026-06-01 → 2026-07-31, for demo purposes. It does
not auto-update.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud

1. Push this repo to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in with GitHub.
3. "New app" → pick this repo/branch → main file path `app.py` → Deploy.
4. Share the generated `*.streamlit.app` URL.

## Refreshing the data snapshot

The cleaning pipeline that produces the per-day source files lives in a
separate, private project (not in this repo, since it touches raw POS
exports and login credentials). To update this repo with newer dates:
1. Regenerate the cleaned per-day output there.
2. Point `build_data_xlsx.py`'s `SRC` at that output and rerun it — it
   rebuilds `data.xlsx` (one sheet per report type, single file, no
   GitHub upload-count limit to worry about).
3. Commit and push the updated `data.xlsx` — Streamlit Cloud redeploys
   automatically.

## Structure

```
app.py               Dashboard UI (9 sections, sidebar date filter)
data_loader.py        Reads data.xlsx into cached DataFrames, one per sheet
data.xlsx              Bundled cleaned-data snapshot (10 sheets)
build_data_xlsx.py    Rebuilds data.xlsx from a per-day source folder
requirements.txt
```
