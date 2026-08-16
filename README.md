# Stream Coffeeshop — Operations Dashboard

Streamlit dashboard over Omega POS export data (sales, menu engineering,
stock movement, purchases, wastage, voids, discounts, transactions).

**This repo bundles a static data snapshot** (`data/`) covering
2026-06-01 → 2026-07-31, for demo purposes. It does not auto-update.

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

The cleaning pipeline that produced `data/` lives in a separate, private
project (not in this repo, since it touches raw POS exports and login
credentials). To update this repo with newer dates:
1. Regenerate the cleaned output there.
2. Copy the updated folders over `data/` here.
3. Commit and push — Streamlit Cloud redeploys automatically.

## Structure

```
app.py            Dashboard UI (9 sections, sidebar date filter)
data_loader.py     Reads data/<ReportFolder>/*.xlsx into cached DataFrames
data/              Bundled cleaned-data snapshot
requirements.txt
```
