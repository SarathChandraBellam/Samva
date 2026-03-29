"""Discover local files to ingest into the knowledge base."""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Formats supported by the Gemini File Search API
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".txt", ".md", ".pdf",
        ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".json", ".yaml", ".yml", ".toml", ".csv",
        ".html", ".xml",
        ".py", ".js", ".ts", ".java", ".go", ".rs", ".cpp", ".c", ".h",
        ".sh", ".rb", ".php", ".swift", ".kt",
    }
)


def discover_files(path: str | Path) -> list[Path]:
    """Return all supported files under *path* (file or directory)."""
    path = Path(path)
    if not path.exists():
        logger.warning("Path does not exist: %s", path)
        return []

    if path.is_file():
        if path.suffix.lower() in SUPPORTED_EXTENSIONS:
            return [path]
        logger.warning("Unsupported file type: %s", path.suffix)
        return []

    files = [
        p for p in path.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    files.sort()
    logger.info("Discovered %d file(s) in %s", len(files), path)
    return files
