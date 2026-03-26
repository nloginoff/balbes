"""
Memory API endpoints (Qdrant-backed semantic memory).
"""

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

router = APIRouter()


class MemoryStoreRequest(BaseModel):
    """Request model for storing memory"""

    agent_id: str = Field(..., description="Agent identifier")
    content: str = Field(..., description="Memory content")
    scope: str = Field(default="personal", description="Memory scope (personal, shared)")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Optional metadata")


class MemorySearchRequest(BaseModel):
    """Request model for searching memory"""

    agent_id: str = Field(..., description="Agent identifier")
    query: str = Field(..., description="Search query")
    scope: str | None = Field(default=None, description="Filter by scope")
    limit: int = Field(default=5, ge=1, le=20, description="Max results")


@router.post("/memory", status_code=status.HTTP_201_CREATED)
async def store_memory(
    request: MemoryStoreRequest,
) -> dict[str, Any]:
    """
    Store memory with semantic indexing.

    Args:
        request: Memory data

    Returns:
        Memory ID and status
    """
    import main as memory_main

    qdrant_client = memory_main.qdrant_client

    if not qdrant_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Qdrant client not available",
        )

    result = await qdrant_client.store_memory(
        agent_id=request.agent_id,
        content=request.content,
        scope=request.scope,
        metadata=request.metadata,
    )

    return result


@router.post("/memory/search")
async def search_memory(
    request: MemorySearchRequest,
) -> dict[str, Any]:
    """
    Semantic search across agent's memories.

    Args:
        request: Search parameters

    Returns:
        Search results with similarity scores
    """
    import main as memory_main

    qdrant_client = memory_main.qdrant_client

    if not qdrant_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Qdrant client not available",
        )

    result = await qdrant_client.search_memory(
        agent_id=request.agent_id,
        query=request.query,
        scope=request.scope,
        limit=request.limit,
    )

    return result


@router.delete("/memory/{memory_id}")
async def delete_memory(
    memory_id: str,
) -> dict[str, str]:
    """
    Delete memory by ID.

    Args:
        memory_id: Memory UUID

    Returns:
        Status
    """
    import main as memory_main

    qdrant_client = memory_main.qdrant_client

    if not qdrant_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Qdrant client not available",
        )

    result = await qdrant_client.delete_memory(memory_id=memory_id)
    return result
