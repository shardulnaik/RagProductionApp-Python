import os

from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct

class QdrantStorage:
    def __init__(self, collection="docs", dim=1536):
        self.client = QdrantClient(
            url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            api_key=os.getenv("QDRANT_API_KEY"),
            timeout=30,
        )
        self.collection = collection
        self.dim = dim

    def _ensure_collection(self):
        """Connect to Qdrant only when a workflow actually needs it.

        Keeping network I/O out of module import means the API can start while
        Docker/Qdrant is still coming up (or temporarily restarting).
        """
        if self.client.collection_exists(self.collection):
            return
        try:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=self.dim, distance=Distance.COSINE),
            )
        except Exception:
            # Another worker may have created it between the existence check
            # and create call. Only suppress that race if it now exists.
            if not self.client.collection_exists(self.collection):
                raise
    
    def upsert(self, ids, vectors, payloads):
        self._ensure_collection()
        points = [PointStruct(id=ids[i], vector=vectors[i], payload=payloads[i]) for i in range(len(ids))]
        self.client.upsert(self.collection, points=points)
    
    def search(self, query_vector, top_k: int = 5):
        self._ensure_collection()
        results = self.client.query_points(
                    collection_name=self.collection,
                    query=query_vector,
                    with_payload=True,
                    limit=top_k
                ).points
        
        contexts = []
        sources = set()  # Using set to avoid duplicates
        
        for r in results:
            payload = getattr(r, "payload", None) or {}
            text = payload.get("text", "")
            source = payload.get("source", "")
            if text:  # Fixed: added proper indentation here
                contexts.append(text)
                sources.add(source)
        
        return {"contexts": contexts, "sources": list(sources)}
