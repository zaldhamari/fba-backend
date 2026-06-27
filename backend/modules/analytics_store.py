import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("siftly.analytics")


def store_events(events: List[Dict[str, Any]]) -> None:
    """Log validated analytics events. Railway streams stdout to Papertrail/logs."""
    for ev in events:
        logger.info(json.dumps({
            "type": "analytics",
            "event": ev.get("event"),
            "userId": ev.get("userId"),
            "appVersion": ev.get("appVersion"),
            "screen": ev.get("screen"),
            "ts": ev.get("ts") or datetime.now(timezone.utc).isoformat(),
            "properties": ev.get("properties") or {},
        }))
