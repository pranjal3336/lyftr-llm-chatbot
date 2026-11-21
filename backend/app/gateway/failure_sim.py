"""X-Simulate-Failure header parsing and simulated provider errors."""
from __future__ import annotations

import litellm

ALLOWED_STATUSES = {429, 500, 502, 503}


def parse_failure_header(value: str | None, key_ids: list[str]) -> dict[str, int]:
    """'key_1=429,key_2=500' / '*=429' -> {key_id: status}. Unknown/invalid pairs are ignored."""
    sim: dict[str, int] = {}
    if not value:
        return sim
    for pair in value.split(","):
        name, sep, status = pair.partition("=")
        name, status = name.strip(), status.strip()
        if not sep or not status.isdigit() or int(status) not in ALLOWED_STATUSES:
            continue
        code = int(status)
        if name == "*":
            sim.update({k: code for k in key_ids})
        elif name in key_ids:
            sim[name] = code
    return sim


def simulated_exception(status: int, model: str) -> Exception:
    """The LiteLLM exception a provider would raise for this HTTP status."""
    msg = f"simulated provider failure (HTTP {status})"
    cls = {
        429: litellm.RateLimitError,
        500: litellm.InternalServerError,
        502: litellm.BadGatewayError,
        503: litellm.ServiceUnavailableError,
    }[status]
    return cls(message=msg, llm_provider="simulated", model=model)
