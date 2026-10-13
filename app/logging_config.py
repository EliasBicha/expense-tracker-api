"""Structured JSON logging and per-request log lines (LOG-01)."""

import json
import logging
import re
import sys
import time
import uuid
from datetime import UTC, datetime

from fastapi import Request, Response

request_logger = logging.getLogger("app.request")

# Accept a client-supplied X-Request-ID only if it is short and harmless,
# so it can't be used to inject fake lines or huge values into the logs.
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        entry.update(getattr(record, "fields", {}))
        if record.exc_info:
            entry["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # Route uvicorn's own logs through the JSON handler instead of its plain-text one.
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
    # Our middleware already logs one structured line per request.
    logging.getLogger("uvicorn.access").disabled = True


async def request_logging_middleware(request: Request, call_next) -> Response:
    incoming_id = request.headers.get("X-Request-ID", "")
    request_id = incoming_id if _REQUEST_ID_PATTERN.match(incoming_id) else uuid.uuid4().hex
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        # Only metadata is logged: never bodies or headers (passwords, tokens) (SEC-03).
        request_logger.info(
            "request",
            extra={
                "fields": {
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": status,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 2),
                    "user_id": getattr(request.state, "user_id", None),
                }
            },
        )
