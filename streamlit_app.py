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
    api_base_url = os.getenv("INNGEST_API_BASE", "http://localhost:8288")
    return inngest.Inngest(
        api_base_url=api_base_url,
        app_id="rag_app",
        event_key=os.getenv("INNGEST_EVENT_KEY", "local"),
        signing_key=os.getenv("INNGEST_SIGNING_KEY"),
        is_production=_inngest_is_production(),
        request_timeout=120_000,
    )


async def send_rag_ingest_event(object_key: str, source_id: str) -> str:
    client = get_inngest_client()
    try:
        result = await client.send(
            inngest.Event(
                name="rag/ingest_pdf",
                data={
                    "object_key": object_key,
                    "source_id": source_id,
                },
            )
        )
        return result[0]
    except Exception:
        logger.exception("Inngest ingestion event send failed")
        raise


st.title("Upload a PDF to Ingest")
uploaded = st.file_uploader("Choose a PDF", type=["pdf"], accept_multiple_files=False)

if uploaded is not None:
    file_bytes = uploaded.getvalue()
    upload_id = hashlib.sha256(uploaded.name.encode() + file_bytes).hexdigest()
    if st.session_state.get("last_upload_id") != upload_id:
        with st.spinner("Uploading and triggering ingestion..."):
            try:
                object_key = upload_pdf(uploaded.name, file_bytes)
                ingest_event_id = run_async(send_rag_ingest_event(object_key, uploaded.name))
                wait_for_run_output(ingest_event_id)
            except Exception as exc:
                st.error(f"Could not finish ingestion: {exc}")
                st.caption("Check that the Inngest dev server and API are running, then retry.")
            else:
                st.session_state["last_upload_id"] = upload_id
                uploaded_sources = st.session_state.setdefault("uploaded_sources", [])
                if uploaded.name not in uploaded_sources:
                    uploaded_sources.append(uploaded.name)
                st.success(f"Ingestion completed for: {uploaded.name}")
    else:
        st.success(f"Ingestion is complete for: {uploaded.name}")
    st.caption("You can upload another PDF if you like.")

st.divider()
st.title("Ask a question about your PDFs")
session_sources = st.session_state.get("uploaded_sources", [])
if session_sources:
    selected_sources = st.multiselect(
        "Search these PDFs",
        options=session_sources,
        default=session_sources,
        help="Only selected PDFs uploaded in this session will be searched.",
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
    return os.getenv("INNGEST_API_BASE", "http://localhost:8288").rstrip("/")


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
