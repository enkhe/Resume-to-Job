# Getting Started

## Prerequisites
- Python 3.11 (3.12 also works locally)
- ~2 GB disk for the embedding model + dependencies

## Install
```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt   # pytest, for running tests
```

## (Optional) Get data + a model
The repo may already ship a harvested dataset and a trained model. If not:
```bash
# 1. Harvest some IT jobs (needs a RapidAPI JSearch key; budget-safe — see data-ingestion docs)
export JSEARCH_API_KEY=...your-key...
python testing/scripts/harvest_jobs_jsearch.py --max-requests 20

# 2. Train the role classifier (produces models/job_role_classifier/vN/model.joblib)
python ml/train_role_classifier.py
```

## Run the app
```bash
streamlit run app.py
# open http://localhost:8501
```

If `streamlit` isn't on your PATH, use `python -m streamlit run app.py`.

## App tour (sidebar order)
1. **Data Ingestion** — load jobs (CSV / API / JSearch).
2. **Dashboard** — catalog, KPIs, model-predicted role mix.
3. **Job Search** — keyword vs semantic retrieval.
4. **Job Matching** — resume → cosine shortlist → AI recommendations.
5. **Model Ops** — model registry, metrics, retrain.

## Configure keys
Set an LLM key for the AI feature (UI field or `AI_API_KEY` / `GEMINI_API_KEY`). All other features
run offline. See [configuration](../operations/configuration.md).

## Run with Docker
```bash
docker compose up --build      # http://localhost:8501
```
