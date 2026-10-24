import os
from pathlib import Path
from google import genai
from google.genai import types
from llama_index.readers.file import PDFReader
from llama_index.core.node_parser import SentenceSplitter

EMBED_MODEL = "gemini-embedding-2"
EMBED_DIM = 1536

splitter = SentenceSplitter(chunk_size=1000, chunk_overlap=200)

def get_gemini_client():
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])

def load_and_chunk_pdf(path: str) -> list[str]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"PDF file not found at path: {path}")
        
    # Updated: Pass file=Path(path) or file_path=file_path directly
    docs = PDFReader().load_data(file=file_path)
    texts = [d.text for d in docs if getattr(d, "text", None)]
    
    if not texts:
        return []

    chunks = []
    for t in texts:
        chunks.extend(splitter.split_text(t))
    return chunks

def embed_texts(texts: list[str], *, input_type: str = "document") -> list[list[float]]:
    if not texts:
        return []

    if input_type == "document":
        contents = [f"title: none | text: {text}" for text in texts]
    elif input_type == "query":
        contents = [f"task: question answering | query: {text}" for text in texts]
    else:
        raise ValueError("input_type must be 'document' or 'query'")
        
    client = get_gemini_client()
    response = client.models.embed_content(
        model=EMBED_MODEL,
        contents=[
            types.Content(parts=[types.Part(text=text)], role="user")
            for text in contents
        ],
        config=types.EmbedContentConfig(output_dimensionality=EMBED_DIM),
    )
    if response.embeddings is None:
        raise RuntimeError("Gemini returned no embeddings")
    return [embedding.values for embedding in response.embeddings]

