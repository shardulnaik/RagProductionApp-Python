# Production-Ready RAG AI Agent

A production-grade RAG application with **observability, logging, retries, and rate limiting**.

## Tech Stack
- **Orchestration:** Inngest (retryable workflows, monitoring)
- **Frontend:** Streamlit
- **Vector DB:** Qdrant
- **Ingestion:** LlamaIndex
- **AI:** OpenAI

## Key Features
- **Production Workflow:** Automatic retries, execution logging, error handling
- **PDF Ingestion:** Load, chunk, and vectorize documents
- **RAG Inference:** Semantic search with grounded LLM responses
- **Operational Control:** Rate limiting, concurrency control, throttling

## Run Locally (Windows PowerShell)

Requirements: Python 3.13+, `uv`, Node.js/npm, and Docker Desktop. Copy
`.env.example` to `.env` and set `OPENAI_API_KEY`. The default local setup stores
PDFs under `data/uploads`, uses local Qdrant and Inngest, and does not require
S3-compatible storage credentials.

Install dependencies from the repository root:

```powershell
uv sync --locked --link-mode copy
```

Start Docker Desktop, then start Qdrant:

```powershell
docker start rag-qdrant 2>$null; if ($LASTEXITCODE -ne 0) { docker run -d --name rag-qdrant --restart unless-stopped -p 6333:6333 -p 6334:6334 -v rag-qdrant-storage:/qdrant/storage qdrant/qdrant }
```

In separate PowerShell terminals, start the Inngest dev server, FastAPI worker,
and Streamlit UI:

```powershell
npx inngest-cli@1.45.1 dev -u http://localhost:8000/api/inngest
```

```powershell
uv run --locked uvicorn main:app --reload --port 8000
```

```powershell
uv run --locked streamlit run streamlit_app.py
```

Open <http://localhost:8501>. The local Inngest dashboard is at
<http://localhost:8288>. For S3-compatible storage, set `STORAGE_BACKEND=s3`
and provide `STORAGE_BUCKET_URL`, `STORAGE_ACCESS_KEY`, and
`STORAGE_SECRET_KEY` in `.env`.

## Usage
1. Upload PDFs via Streamlit interface
2. System automatically processes and vectors documents
3. Ask questions in natural language
4. Receive grounded responses with context

## Architecture
```
Streamlit → Inngest → OpenAI API
              ↓
         Qdrant ← LlamaIndex
```

## Production Features
- **Observability:** Full visibility into function runs
- **Reliability:** Automatic retries with exponential backoff
- **Scalability:** Horizontal scaling support
- **Security:** Rate limiting, API key management

---

**License:** MIT
