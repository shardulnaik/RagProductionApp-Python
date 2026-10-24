# RAG PDF application

This repository is configured for the hosted production application. It is not
intended to run against local services.

## Live architecture

- **Frontend:** Streamlit Community Cloud (`streamlit_app.py`)
- **API and Inngest functions:** Render (`main.py`, `/api/inngest`)
- **Workflow execution:** Inngest Cloud
- **PDF objects:** Supabase Storage through its S3-compatible API
- **Embeddings and retrieval:** Gemini Embeddings 2 and Qdrant Cloud
- **Answer generation:** Gemini Flash

PDF uploads are stored in Supabase, then Inngest sends the storage key to the
Render worker. The worker extracts text, creates Gemini embeddings, and writes
points into the `docs_gemini` Qdrant collection. Queries are filtered to the
PDFs selected in the current Streamlit session.

## Required hosted configuration

Set the following values in the **Render backend environment**:

- `GEMINI_API_KEY`
- `QDRANT_URL`
- `QDRANT_API_KEY`
- `INNGEST_EVENT_KEY`
- `INNGEST_SIGNING_KEY`
- `STORAGE_BUCKET_URL`
- `STORAGE_ACCESS_KEY`
- `STORAGE_SECRET_KEY`
- `PYTHONUNBUFFERED=1`

Set these values in **Streamlit Community Cloud → App settings → Secrets**:

- `INNGEST_EVENT_KEY`
- `INNGEST_SIGNING_KEY`
- `STORAGE_BUCKET_URL`
- `STORAGE_ACCESS_KEY`
- `STORAGE_SECRET_KEY`

The Gemini and Qdrant credentials belong only to the Render backend. The
Streamlit frontend does not call Gemini or Qdrant directly. Supabase region
defaults to `ap-south-1` (Mumbai); set `STORAGE_REGION` in both hosted
environments only if the Supabase project is in another region.

`INNGEST_API_BASE` is fixed to `https://api.inngest.com` in the app code.
Register the Render endpoint with Inngest Cloud as:

```text
https://rag-worker-komx.onrender.com/api/inngest
```

## Deploy behavior

Deploy the repository's `main` branch to both hosted apps. Streamlit's entry
file is `streamlit_app.py`. Render starts the FastAPI service with:

```text
uv run uvicorn main:app --host 0.0.0.0 --port $PORT
```

After a new deployment, upload each PDF again so it is embedded into the Gemini
collection. The previous OpenAI collection is left untouched.
