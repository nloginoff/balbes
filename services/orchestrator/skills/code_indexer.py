"""
Code indexer for semantic search across the project codebase.

Indexes project files into Qdrant (collection: code_index) using file-level
embeddings. Supports:
  - Manual re-indexing via `index_codebase` tool
  - Semantic search via `code_search` tool
  - Automatic scheduled re-indexing
"""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from shared.config import get_settings
from shared.openrouter_http import openrouter_json_headers

logger = logging.getLogger("orchestrator.code_indexer")

# Collection name for code index (separate from agent_memory)
CODE_INDEX_COLLECTION = "code_index"
EMBEDDING_MODEL = "openai/text-embedding-3-small"
EMBEDDING_DIMENSION = 1536

# File extensions to index
INDEXED_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".yaml", ".yml", ".md", ".sh"}

# Paths to skip
SKIP_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "htmlcov",
    "migrations",
}

# Max file size to index (bytes)
MAX_FILE_SIZE = 50_000

# Max chars sent to embedding model (truncate if needed)
MAX_EMBED_CHARS = 4_000

# Project root
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.resolve()


class CodeIndexer:
    """
    Indexes project source files into Qdrant for semantic code search.
    Uses file-level granularity: each file is one vector point.
    """

    def __init__(
        self,
        openrouter_api_key: str,
        qdrant_host: str,
        qdrant_port: int,
        openrouter_user_end_id: str | None = None,
    ):
        self.openrouter_api_key = openrouter_api_key
        self.qdrant_host = qdrant_host
        self.qdrant_port = qdrant_port
        self.openrouter_user_end_id = openrouter_user_end_id
        self._http: httpx.AsyncClient | None = None
        self._qdrant: Any | None = None  # qdrant_client.AsyncQdrantClient

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=60.0)
        return self._http

    async def _get_qdrant(self):
        if self._qdrant is None:
            from qdrant_client import AsyncQdrantClient

            self._qdrant = AsyncQdrantClient(
                host=self.qdrant_host,
                port=self.qdrant_port,
                https=False,
                timeout=30,
            )
            await self._ensure_collection()
        return self._qdrant

    async def _ensure_collection(self) -> None:
        """Create code_index collection if it doesn't exist."""
        from qdrant_client.models import Distance, VectorParams

        client = self._qdrant
        collections = await client.get_collections()
        names = [c.name for c in collections.collections]
        if CODE_INDEX_COLLECTION not in names:
            await client.create_collection(
                collection_name=CODE_INDEX_COLLECTION,
                vectors_config=VectorParams(size=EMBEDDING_DIMENSION, distance=Distance.COSINE),
            )
            await client.create_payload_index(
                collection_name=CODE_INDEX_COLLECTION,
                field_name="path",
                field_schema="keyword",
            )
            logger.info(f"Created Qdrant collection '{CODE_INDEX_COLLECTION}'")

    async def _embed(self, text: str) -> list[float]:
        """Generate embedding via OpenRouter."""
        http = await self._get_http()
        # Truncate to avoid token limits
        truncated = text[:MAX_EMBED_CHARS]
        emb_body: dict[str, Any] = {"model": EMBEDDING_MODEL, "input": truncated}
        uid = self.openrouter_user_end_id
        if uid:
            emb_body["user"] = uid
        else:
            emb_body["user"] = get_settings().openrouter_service_user
        resp = await http.post(
            "https://openrouter.ai/api/v1/embeddings",
            headers=openrouter_json_headers(get_settings(), api_key=self.openrouter_api_key),
            json=emb_body,
            timeout=30.0,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Embedding API error: HTTP {resp.status_code} — {resp.text[:200]}")
        data = resp.json()
        return data["data"][0]["embedding"]

    def _collect_files(self, root: Path) -> list[Path]:
        """Walk project tree and return indexable files."""
        files: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(root):
            # Prune skip dirs in-place
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in filenames:
                p = Path(dirpath) / name
                if p.suffix.lower() not in INDEXED_EXTENSIONS:
                    continue
                try:
                    if p.stat().st_size > MAX_FILE_SIZE:
                        continue
                except OSError:
                    continue
                files.append(p)
        return files

    async def index_path(self, path: Path | None = None, force: bool = False) -> dict[str, Any]:
        """
        Index files under `path` (default: project root) into Qdrant.
        If force=False, skips files whose mtime hasn't changed since last index.
        Returns stats dict.
        """
        root = path or _PROJECT_ROOT
        client = await self._get_qdrant()

        files = self._collect_files(root)
        indexed = 0
        skipped = 0
        errors = 0

        for file_path in files:
            try:
                rel = str(file_path.relative_to(_PROJECT_ROOT))
                mtime = file_path.stat().st_mtime
                content = file_path.read_text(encoding="utf-8", errors="replace")

                # Check if already indexed with same mtime (unless force)
                if not force:
                    existing = await client.scroll(
                        collection_name=CODE_INDEX_COLLECTION,
                        scroll_filter={"must": [{"key": "path", "match": {"value": rel}}]},
                        limit=1,
                        with_payload=True,
                    )
                    if existing[0]:  # points found
                        stored_mtime = existing[0][0].payload.get("mtime", 0)
                        if abs(stored_mtime - mtime) < 1.0:
                            skipped += 1
                            continue

                # Build embed text: path header + content preview
                embed_text = f"# {rel}\n\n{content}"
                vector = await self._embed(embed_text)

                # Use hash of path for stable ID
                import hashlib

                path_hash = int(hashlib.md5(rel.encode()).hexdigest(), 16) % (2**63)

                lines = content.count("\n") + 1
                preview = content[:500].replace("\n", " ")

                from qdrant_client.models import PointStruct

                await client.upsert(
                    collection_name=CODE_INDEX_COLLECTION,
                    points=[
                        PointStruct(
                            id=path_hash,
                            vector=vector,
                            payload={
                                "path": rel,
                                "lines": lines,
                                "mtime": mtime,
                                "preview": preview,
                                "indexed_at": datetime.now(timezone.utc).isoformat(),
                            },
                        )
                    ],
                )
                indexed += 1
                logger.debug(f"Indexed: {rel}")

            except Exception as e:
                logger.warning(f"Failed to index {file_path}: {e}")
                errors += 1

        logger.info(f"Code index: {indexed} indexed, {skipped} skipped, {errors} errors")
        return {
            "indexed": indexed,
            "skipped": skipped,
            "errors": errors,
            "total_files": len(files),
        }

    async def search(
        self, query: str, path_filter: str | None = None, limit: int = 5
    ) -> list[dict[str, Any]]:
        """
        Search code index for files semantically matching the query.
        Returns list of {path, preview, score, lines}.
        """
        client = await self._get_qdrant()
        vector = await self._embed(query)

        search_filter = None
        if path_filter:
            from qdrant_client.models import FieldCondition, Filter, MatchText

            search_filter = Filter(
                must=[FieldCondition(key="path", match=MatchText(text=path_filter))]
            )

        results = await client.search(
            collection_name=CODE_INDEX_COLLECTION,
            query_vector=vector,
            query_filter=search_filter,
            limit=limit,
            with_payload=True,
        )

        return [
            {
                "path": r.payload.get("path", ""),
                "preview": r.payload.get("preview", "")[:200],
                "score": round(r.score, 3),
                "lines": r.payload.get("lines", 0),
            }
            for r in results
        ]

    async def close(self) -> None:
        if self._http:
            await self._http.aclose()
        if self._qdrant:
            await self._qdrant.close()
