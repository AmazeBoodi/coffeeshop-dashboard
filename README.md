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

## "Ask AI" setup (Groq API key)

The **🤖 Ask AI** page answers questions about the currently-filtered data
using Groq. It needs an API key — the app works fine without one, that page
just shows a setup message instead.

1. Get a free key at [console.groq.com/keys](https://console.groq.com/keys).
2. **Local run:** copy `.streamlit/secrets.toml.example` to
   `.streamlit/secrets.toml` (exact filename, no `.example`) and paste your
   key in. That file is gitignored — it never gets committed.
3. **Streamlit Community Cloud:** app page → ⋮ menu → **Settings** →
   **Secrets** → paste:
   ```toml
   GROQ_API_KEY = "your-key-here"
   ```
   Save — the app restarts automatically with it available.

The key is never hardcoded anywhere in this repo — only read via
`st.secrets`, which Streamlit keeps out of the deployed source and out of
version control.

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
app.py                        Dashboard UI (10 sections, sidebar date filter)
data_loader.py                 Reads data.xlsx into cached DataFrames, one per sheet
ai_assistant.py                Groq-powered "Ask AI" chat (data digest + Q&A)
data.xlsx                       Bundled cleaned-data snapshot (10 sheets)
build_data_xlsx.py             Rebuilds data.xlsx from a per-day source folder
.streamlit/secrets.toml.example  Copy to secrets.toml and add your Groq key
requirements.txt
```
