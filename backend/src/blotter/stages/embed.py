from __future__ import annotations

from blotter.config import EmbeddingConfig
from blotter.log import get_logger

log = get_logger(__name__)


class Embedder:
    def __init__(self, config: EmbeddingConfig) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(config.model_name, device=config.device)
        log.info("embedding model loaded", model=config.model_name, device=config.device)

    def encode(self, text: str) -> list[float]:
        return self._model.encode(text, normalize_embeddings=True).tolist()
