"""ID helpers — short, sortable, debuggable. Replace with ULIDs in prod."""
from __future__ import annotations

import time
import uuid


def new_id(prefix: str) -> str:
    return f"{prefix}_{int(time.time() * 1000):x}_{uuid.uuid4().hex[:6]}"
