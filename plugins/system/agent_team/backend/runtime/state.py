"""Team Agent state."""

from typing import Any, Dict, List, Optional, TypedDict


class TeamAgentState(TypedDict):
    input: str
    session_id: str
    messages: List[Any]
    output: str
    attachments: Optional[List[Dict[str, Any]]]
