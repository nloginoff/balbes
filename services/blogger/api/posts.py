"""
Blogger service REST API — post management endpoints.

Used by the main telegram_bot.py to handle inline button callbacks.
"""

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

if TYPE_CHECKING:
    pass

logger = logging.getLogger("blogger.api.posts")

router = APIRouter(prefix="/api/v1/posts", tags=["posts"])


def _parse_publish_at_iso(value: str):
    """Parse ISO 8601; accepts trailing ``Z`` (Python fromisoformat may not)."""
    from datetime import datetime

    t = (value or "").strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    return datetime.fromisoformat(t)


# These are set by main.py after service startup
_queue = None
_agent = None
_publisher = None
_business_bot = None


def init(queue, agent, publisher, business_bot=None):
    global _queue, _agent, _publisher, _business_bot
    _queue = queue
    _agent = agent
    _publisher = publisher
    _business_bot = business_bot


# =========================================================================
# Request models
# =========================================================================


class ReviseRequest(BaseModel):
    instruction: str
    owner_chat_id: int | None = None


class GenerateRequest(BaseModel):
    agents: list[str] = ["orchestrator", "coder"]
    cursor_files: int = 2
    from_hours: int = 48


class ScheduleRequest(BaseModel):
    publish_at: str  # ISO datetime string


async def _require_resolved_post_id(raw: str) -> str:
    """Map path segment to full post UUID; 400 on invalid or ambiguous id."""
    resolved, err = await _queue.resolve_post_id(raw)
    if err:
        raise HTTPException(status_code=400, detail=err)
    return resolved


# =========================================================================
# Endpoints
# =========================================================================


@router.get("/")
async def list_posts(status: str | None = None, limit: int = 20):
    """List blog posts, optionally filtered by status."""
    posts = await _queue.list_posts(status=status, limit=limit)
    return {"posts": [_serialize_post(p) for p in posts]}


@router.get("/{post_id}")
async def get_post(post_id: str):
    """Get a single post by ID."""
    rid = await _require_resolved_post_id(post_id)
    post = await _queue.get_post(rid)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return _serialize_post(post)


@router.post("/{post_id}/approve")
async def approve_post(post_id: str):
    """
    Approve a pending post — moves it to the publish queue.
    Called by telegram_bot callback handler.
    """
    rid = await _require_resolved_post_id(post_id)
    ok = await _queue.approve(rid)
    if not ok:
        raise HTTPException(
            status_code=400, detail="Post not found or not in pending_approval state"
        )

    # For agent posts: assign to appropriate channels automatically
    post = await _queue.get_post(rid)
    if post and not post.get("channel_id"):
        await _assign_channels(rid, post.get("post_type", "agent"))

    logger.info("Post %s approved", rid)
    return {"status": "approved", "post_id": rid}


@router.post("/{post_id}/reject")
async def reject_post(post_id: str):
    """Reject a pending post."""
    rid = await _require_resolved_post_id(post_id)
    ok = await _queue.reject(rid)
    if not ok:
        raise HTTPException(status_code=400, detail="Post not found")
    logger.info("Post %s rejected", rid)
    return {"status": "rejected", "post_id": rid}


@router.post("/{post_id}/revise")
async def revise_post(post_id: str, body: ReviseRequest):
    """
    Trigger post revision by the agent.
    Called when owner clicks 'Edit' and then sends instructions.
    """
    rid = await _require_resolved_post_id(post_id)
    owner_id = body.owner_chat_id or _agent.owner_tg_id
    await _agent.handle_edit_instruction(owner_id, rid, body.instruction)
    return {"status": "revision_started", "post_id": rid}


@router.post("/generate")
async def generate_post(body: GenerateRequest):
    """
    Manually trigger agent post generation.
    """
    post = await _agent.generate_agent_post(
        agents=body.agents,
        cursor_files=body.cursor_files,
        from_hours=body.from_hours,
    )
    if not post:
        raise HTTPException(
            status_code=422, detail="Could not generate post from available material"
        )

    post_id = await _agent.create_and_send_draft(post, post_type="agent")
    return {"status": "draft_created", "post_id": post_id}


@router.post("/{post_id}/schedule")
async def schedule_post(post_id: str, body: ScheduleRequest):
    """Schedule an approved post for publishing at a specific time."""
    rid = await _require_resolved_post_id(post_id)
    try:
        publish_at = _parse_publish_at_iso(body.publish_at)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid publish_at datetime format") from None

    ok = await _queue.schedule(rid, publish_at)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="Post not found or not in approved state; approve the post first",
        )
    return {"status": "scheduled", "post_id": rid, "publish_at": body.publish_at}


# =========================================================================
# Business bot state endpoint (used by telegram_bot callback)
# =========================================================================


@router.post("/edit-mode/{post_id}")
async def set_edit_mode(post_id: str, owner_chat_id: int):
    """Set business_bot into edit-waiting mode for a specific post."""
    rid = await _require_resolved_post_id(post_id)
    if _business_bot:
        _business_bot.set_waiting_edit(owner_chat_id, rid)
    return {"status": "waiting_edit", "post_id": rid}


@router.post("/create")
async def create_post_draft(body: dict):
    """Create a draft and send for approval (called from orchestrator tools)."""
    content_ru = body.get("content_ru", "")
    content_en = body.get("content_en", "")
    post_type = body.get("post_type", "agent")

    post_id = await _queue.create_draft(
        content_ru=content_ru,
        content_en=content_en,
        post_type=post_type,
        source_refs=body.get("source_refs", []),
        notes=body.get("notes", ""),
        title=body.get("title", ""),
    )

    post = {
        "title": body.get("title", ""),
        "content_ru": content_ru,
        "content_en": content_en,
        "source_refs": body.get("source_refs", []),
        "notes": body.get("notes", ""),
    }
    await _agent.create_and_send_draft.__func__(_agent, post, post_type)

    return {"status": "created", "post_id": post_id}


# =========================================================================
# Business chat endpoints (used by orchestrator tools)
# =========================================================================

business_router = APIRouter(prefix="/api/v1", tags=["business"])


class SetRoleRequest(BaseModel):
    group_id: str
    user_id: str
    role: str


class BusinessSummaryRequest(BaseModel):
    period_hours: int = 24
    chat_ids: list[int] | None = None


@business_router.get("/business-messages")
async def get_business_messages(from_ts: str | None = None, limit: int = 200):
    """Get anonymized business messages."""
    from datetime import datetime

    from_dt = None
    if from_ts:
        try:
            from_dt = datetime.fromisoformat(from_ts.replace("Z", "+00:00"))
        except ValueError:
            pass

    if _queue and _queue.db:
        from ..reader import BusinessChatReader

        reader = BusinessChatReader(_queue.db)
        messages = await reader.read(from_ts=from_dt, limit=limit)
        return {"messages": messages}
    return {"messages": []}


@business_router.post("/business-summary")
async def get_business_summary(body: BusinessSummaryRequest):
    """Generate LLM summary of business chats."""
    if _agent:
        summary = await _agent.generate_business_summary(
            period_hours=body.period_hours,
        )
        return {"summary": summary or ""}
    return {"summary": ""}


@business_router.post("/business-chats/set-role")
async def set_business_role(body: SetRoleRequest):
    """Set role mapping for anonymization."""
    if not _queue or not _queue.db:
        raise HTTPException(status_code=503, detail="DB not available")
    import json

    row = await _queue.db.fetchrow(
        "SELECT id, role_map FROM business_chats WHERE tg_group_id = $1",
        body.group_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Business chat {body.group_id} not found")

    role_map = dict(row["role_map"] or {})
    role_map[body.user_id] = body.role

    await _queue.db.execute(
        "UPDATE business_chats SET role_map = $1::jsonb WHERE tg_group_id = $2",
        json.dumps(role_map),
        body.group_id,
    )
    return {"status": "ok", "group_id": body.group_id, "user_id": body.user_id, "role": body.role}


# =========================================================================
# Helpers
# =========================================================================


def _serialize_post(p: dict) -> dict:
    """Convert asyncpg Record to JSON-serializable dict."""
    result = {}
    for k, v in p.items():
        if hasattr(v, "isoformat"):
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result


async def _assign_channels(post_id: str, post_type: str) -> None:
    """Assign channel_id to an approved post based on type."""
    channels = await _queue.get_channels()
    if not channels:
        return

    target_lang = "personal" if post_type == "user" else "ru"

    for ch in channels:
        if ch.get("language") == target_lang:
            await _queue.db.execute(
                "UPDATE blog_posts SET channel_id = $1, updated_at = NOW() WHERE id = $2",
                ch["id"],
                post_id,
            )
            break
