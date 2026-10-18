"""The real embedder: Voyage AI with the pinned model, a 5-second timeout, document and query modes."""

import numpy as np

from app.config import SETTINGS


VOYAGE_RETRIES = 1


class VoyageEmbedder:
    def __init__(self, input_type: str = "query"):
        import voyageai

        self._client = voyageai.Client(timeout=SETTINGS.voyage_timeout_s, max_retries=VOYAGE_RETRIES)
        self._input_type = input_type

    def embed(self, texts: list[str]) -> np.ndarray:
        result = self._client.embed(texts, model=SETTINGS.embedding_model, input_type=self._input_type)
        vectors = np.array(result.embeddings, dtype=float)
        return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
