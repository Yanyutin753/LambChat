from __future__ import annotations

import uuid
from datetime import datetime


def generate_run_id() -> str:
    """Generate a unique task run identifier."""
    return f"run_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
