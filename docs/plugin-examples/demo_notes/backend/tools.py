from __future__ import annotations

from typing import Annotated


async def demo_notes_create_note(
    content: Annotated[str, "Note content to save."],
    source: Annotated[str, "Where the note came from."] = "agent",
) -> dict[str, str]:
    return {
        "status": "created",
        "plugin_id": "demo_notes",
        "source": source,
        "content": content,
    }
