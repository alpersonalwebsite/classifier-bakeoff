"""Capture each HTTP exchange exactly as sent and received (spec 001 B5).

Every call goes through one OpenRouter client built on an `httpx2.Client`, so
one transport wrapper records the request body and the raw response body for
every variant. Token counts are read from that raw body, never from a local
estimate (constitution Principle 2).
"""

import json
import threading
from dataclasses import dataclass
from typing import Any

import httpx2

# Headers that can carry credentials, OpenRouter's or any vendor's.
_SECRET_HEADERS = {"authorization", "x-api-key", "api-key", "openai-organization", "openai-project"}


@dataclass
class Exchange:
    url: str
    request_body: Any
    request_headers: dict[str, str]
    status: int | None
    response_body: Any


def _decode(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return raw.decode("utf-8", errors="replace")


class RecordingTransport(httpx2.BaseTransport):
    """Wraps a real transport and keeps the most recent exchange per thread."""

    def __init__(self, inner: httpx2.BaseTransport | None = None):
        self._inner = inner or httpx2.HTTPTransport()
        self._local = threading.local()

    def reset(self) -> None:
        self._local.exchange = None

    @property
    def last(self) -> Exchange | None:
        return getattr(self._local, "exchange", None)

    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        headers = {k: v for k, v in request.headers.items() if k.lower() not in _SECRET_HEADERS}
        exchange = Exchange(
            url=str(request.url),
            request_body=_decode(request.content),
            request_headers=headers,
            status=None,
            response_body=None,
        )
        self._local.exchange = exchange
        response = self._inner.handle_request(request)
        response.read()
        exchange.status = response.status_code
        exchange.response_body = _decode(response.content)
        return response

    def close(self) -> None:
        self._inner.close()


def recording_client(transport: RecordingTransport, timeout: float) -> httpx2.Client:
    return httpx2.Client(transport=transport, timeout=timeout)
