"""Manage Gemini File Search stores for the knowledge base."""
from __future__ import annotations

import logging
from pathlib import Path

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class KnowledgeBaseManager:
    """Create, populate, and query Gemini File Search stores."""

    def __init__(self, client: genai.Client, search_model: str) -> None:
        self.client = client
        self.search_model = search_model
        # Cache display_name -> resource name
        self._store_cache: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Store management
    # ------------------------------------------------------------------

    def create_or_get_store(self, display_name: str) -> str:
        """Return the resource name of an existing store, or create one."""
        if display_name in self._store_cache:
            return self._store_cache[display_name]

        # Search among existing stores
        for store in self.client.file_search_stores.list():
            if store.display_name == display_name:
                logger.info("Found existing KB store: %s (%s)", display_name, store.name)
                self._store_cache[display_name] = store.name
                return store.name

        # Create a new store
        store = self.client.file_search_stores.create(
            config={"display_name": display_name}
        )
        logger.info("Created KB store: %s (%s)", display_name, store.name)
        self._store_cache[display_name] = store.name
        return store.name

    def list_documents(self, store_name: str) -> list[str]:
        """Return display names of all documents in the store."""
        docs = []
        for doc in self.client.file_search_stores.documents.list(parent=store_name):
            docs.append(doc.display_name or doc.name)
        return docs

    def delete_store(self, store_name: str) -> None:
        """Permanently delete a knowledge base store."""
        self.client.file_search_stores.delete(name=store_name)
        self._store_cache = {k: v for k, v in self._store_cache.items() if v != store_name}
        logger.info("Deleted KB store: %s", store_name)

    # ------------------------------------------------------------------
    # Document ingestion
    # ------------------------------------------------------------------

    def upload_file(
        self,
        store_name: str,
        file_path: str | Path,
        display_name: str | None = None,
        poll_interval: float = 2.0,
    ) -> None:
        """Upload a file directly into the knowledge base store."""
        import time

        file_path = Path(file_path)
        display_name = display_name or file_path.name
        logger.info("Uploading '%s' → store %s ...", display_name, store_name)

        op = self.client.file_search_stores.upload_to_file_search_store(
            file=str(file_path),
            file_search_store_name=store_name,
            config={"display_name": display_name},
        )

        # Poll until the indexing operation completes
        while not op.done:
            time.sleep(poll_interval)
            op = self.client.operations.get(op)

        logger.info("Uploaded '%s' successfully", display_name)

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def search(self, store_name: str, query: str, retries: int = 3) -> str:
        """Run a RAG query against the store and return a grounded answer."""
        import time

        logger.debug("KB search | store=%s | query=%r", store_name, query)
        last_err = None
        for attempt in range(retries):
            try:
                response = self.client.models.generate_content(
                    model=self.search_model,
                    contents=query,
                    config=types.GenerateContentConfig(
                        tools=[
                            types.Tool(
                                file_search=types.FileSearch(
                                    file_search_store_names=[store_name]
                                )
                            )
                        ]
                    ),
                )
                result = response.text or "No relevant information found in the knowledge base."
                logger.debug("KB result: %s", result[:200])
                return result
            except Exception as e:
                last_err = e
                logger.warning("KB search attempt %d failed: %s", attempt + 1, e)
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)  # 1s, 2s backoff
        logger.error("KB search failed after %d attempts: %s", retries, last_err)
        return "I couldn't retrieve information from the knowledge base right now. Please try again in a moment."
