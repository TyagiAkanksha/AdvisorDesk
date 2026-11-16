"""Provider selection for the embedder (`Settings.embedding_provider`)."""

from __future__ import annotations

from app.config import Settings
from app.rag.embeddings import Embedder, OpenAICompatibleEmbedder
from app.rag.local_embeddings import LocalEmbedder

__all__ = ["build_embedder"]


def build_embedder(settings: Settings) -> Embedder:
    """Build the embedder for the configured provider."""
    if settings.embedding_provider == "local":
        return LocalEmbedder.from_settings(settings)
    return OpenAICompatibleEmbedder.from_settings(settings)
