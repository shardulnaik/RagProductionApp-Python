import asyncio
import hashlib
import logging
import time

import streamlit as st
import inngest
from dotenv import load_dotenv
import os
import requests

from storage import upload_pdf

load_dotenv()
logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


def _inngest_is_production() -> bool:
    configured_mode = os.getenv("INNGEST_IS_PRODUCTION")
    if configured_mode is not None:
        return configured_mode.strip().lower() in {"1", "true", "yes", "on"}
    return bool(os.getenv("INNGEST_SIGNING_KEY"))


def _inngest_api_base_url() -> str:
    configured_base = os.getenv("INNGEST_API_BASE")
    if configured_base:
        return configured_base.rstrip("/")
    return "https://api.inngest.com" if _inngest_is_production() else "http://localhost:8288"


def run_async(coro):
    import asyncio

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()


st.set_page_config(page_title="RAG Ingest PDF", page_icon="📄", layout="centered")


@st.cache_resource
def get_inngest_client() -> inngest.Inngest:
    api_base_url = _inngest_api_base_url()
    return inngest.Inngest(
        api_base_url=api_base_url,
        app_id="rag_app",
        event_key=os.getenv("INNGEST_EVENT_KEY", "local"),
        signing_key=os.getenv("INNGEST_SIGNING_KEY"),
        is_production=_inngest_is_production(),
        request_timeout=120_000,
    )


async def send_rag_ingest_event(object_key: str, source_id: str, source_name: str) -> str:
    client = get_inngest_client()
    try:
        result = await client.send(
            inngest.Event(
                name="rag/ingest_pdf",
                data={
                    "object_key": object_key,
                    "source_id": source_id,
                    "source_name": source_name,
                },
            )
        )
        return result[0]
    except Exception:
        logger.exception("Inngest ingestion event send failed")
        raise


st.title("Upload a PDF to Ingest")
uploaded = st.file_uploader("Choose a PDF", type=["pdf"], accept_multiple_files=False)
if st.session_state.get("upload_state_version") != 2:
    st.session_state["last_upload_id"] = None
    st.session_state["uploaded_sources"] = {}
    st.session_state["upload_state_version"] = 2
uploaded_sources = st.session_state.get("uploaded_sources")
if not isinstance(uploaded_sources, dict):
    uploaded_sources = {}
    st.session_state["uploaded_sources"] = uploaded_sources

if uploaded is not None:
    file_bytes = uploaded.getvalue()
    upload_id = hashlib.sha256(uploaded.name.encode() + file_bytes).hexdigest()
    if st.session_state.get("last_upload_id") != upload_id:
        with st.spinner("Uploading and triggering ingestion..."):
            try:
                object_key = upload_pdf(uploaded.name, file_bytes)
                ingest_event_id = run_async(
                    send_rag_ingest_event(object_key, upload_id, uploaded.name)
                )
                ingest_output = wait_for_run_output(ingest_event_id)
                if ingest_output.get("error"):
                    raise RuntimeError(ingest_output["error"])
                ingested_count = ingest_output.get("ingested", 0)
                if not isinstance(ingested_count, int) or ingested_count < 1:
                    raise RuntimeError(
                        ingest_output.get("message", "No text chunks were ingested from this PDF.")
                    )
            except Exception as exc:
                st.error(f"Could not finish ingestion: {exc}")
                st.caption("Check that the Inngest dev server and API are running, then retry.")
            else:
                st.session_state["last_upload_id"] = upload_id
                uploaded_sources[upload_id] = uploaded.name
                st.success(f"Ingestion completed for: {uploaded.name}")
    else:
        uploaded_sources[upload_id] = uploaded.name
        st.success(f"Ingestion is complete for: {uploaded.name}")
    st.caption("You can upload another PDF if you like.")

st.divider()
st.title("Ask a question about your PDFs")
session_sources = list(uploaded_sources)
if session_sources:
    latest_source = st.session_state.get("last_upload_id")
    default_sources = (
        [latest_source]
        if latest_source in session_sources
        else [session_sources[-1]]
    )
    source_labels = {
        source_id: f"{uploaded_sources[source_id]} · {source_id[:8]}"
        for source_id in session_sources
    }
    selected_sources = st.multiselect(
        "Search these PDFs (newest selected by default)",
        options=session_sources,
        default=default_sources,
        format_func=lambda source_id: source_labels[source_id],
        help="The latest PDF is selected by default. Select older PDFs if you want to include them.",
    )
else:
    selected_sources = []
    st.info("Upload and finish ingesting a PDF in this session before asking a question.")


async def send_rag_query_event(question: str, top_k: int, source_ids: list[str]) -> str:
    client = get_inngest_client()
    try:
        result = await client.send(
            inngest.Event(
                name="rag/query_pdf_ai",
                data={
                    "question": question,
                    "top_k": top_k,
                    "source_ids": source_ids,
                },
            )
        )
        return result[0]
    except Exception:
        logger.exception("Inngest query event send failed")
        raise


def _inngest_api_base() -> str:
    return _inngest_api_base_url()


def fetch_runs(event_id: str) -> list[dict]:
    url = f"{_inngest_api_base()}/v1/events/{event_id}/runs"
    headers = {}
    signing_key = os.getenv("INNGEST_SIGNING_KEY")
    if signing_key:
        headers["Authorization"] = f"Bearer {signing_key}"
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", [])


def wait_for_run_output(event_id: str, timeout_s: float = 120.0, poll_interval_s: float = 0.5) -> dict:
    start = time.time()
    last_status = None
    while True:
        runs = fetch_runs(event_id)
        if runs:
            run = runs[0]
            status = run.get("status")
            last_status = status or last_status
            if status in ("Completed", "Succeeded", "Success", "Finished"):
                return run.get("output") or {}
            if status in ("Failed", "Cancelled"):
                raise RuntimeError(f"Function run {status}")
        if time.time() - start > timeout_s:
            raise TimeoutError(f"Timed out waiting for run output (last status: {last_status})")
        time.sleep(poll_interval_s)


with st.form("rag_query_form"):
    question = st.text_input("Your question")
    top_k = st.number_input("How many chunks to retrieve", min_value=1, max_value=20, value=5, step=1)
    submitted = st.form_submit_button("Ask")

    if submitted and question.strip():
        if not selected_sources:
            st.error("Select at least one PDF to search.")
        else:
            with st.spinner("Searching selected PDFs and generating answer..."):
                try:
                    event_id = run_async(send_rag_query_event(question.strip(), int(top_k), selected_sources))
                    output = wait_for_run_output(event_id)
                except Exception as exc:
                    st.error(f"The query did not finish: {exc}")
                    st.caption("Check the Inngest dashboard and API/worker terminal for details.")
                    st.stop()
                answer = output.get("answer", "")
                sources = output.get("sources", [])

            st.subheader("Answer")
            st.write(answer or "(No answer)")
            if sources:
                st.caption("Sources")
                for s in sources:
                    st.write(f"- {s}")
