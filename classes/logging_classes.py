from pydantic import BaseModel
from typing import Any
from classes.base_classes import *


# ===== class for the content of log entries =====

class LogEntry(BaseModel):
    time: str
    source_ip: str | None = None
    http_method: str
    endpoint: str
    status_code: int
    streamed: bool | None = None
    headers: dict[str, str] | None = None
    request_hex_dump: str | None = None
    error_data: dict[str, Any] | None = None
    request_body: dict[str, Any] | BaseRequest | None = None
    response: dict[str, Any] | BaseResponse | None = None
