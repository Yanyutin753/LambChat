from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()


class DemoNoteCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    source: str = Field("manual", max_length=80)


class DemoNoteResponse(BaseModel):
    id: str
    content: str
    source: str
    created_at: str


@router.get("/health")
async def demo_notes_health() -> dict[str, Any]:
    return {"plugin_id": "demo_notes", "status": "ok"}


@router.post("/notes", response_model=DemoNoteResponse)
async def create_demo_note(body: DemoNoteCreate) -> DemoNoteResponse:
    now = datetime.now(timezone.utc).isoformat()
    return DemoNoteResponse(
        id=f"demo-{int(datetime.now(timezone.utc).timestamp())}",
        content=body.content,
        source=body.source,
        created_at=now,
    )

