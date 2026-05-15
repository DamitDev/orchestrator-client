"""Environment-based configuration for the orchestrator client.

All settings are read from environment variables with sensible defaults,
so upstream applications can configure the client without passing args.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class OrchestratorConfig:
    """Connection configuration for the Orchestrator API.

    Attributes:
        base_url:  Base URL of the orchestrator (e.g. ``http://orchestrator:8080``).
                   Supports subpath deployments — keep the subpath as part of the URL
                   (e.g. ``https://oapi.local/uat``).
        api_key:   Optional static bearer token sent as ``Authorization: Bearer <key>``.
                   ``None`` means no auth header is added.
        timeout:   Default timeout in seconds for HTTP requests (connect, read, write, pool).
        max_retries: Maximum retry attempts on transient failures (connection errors,
                   5xx responses). Zero means no retries.
    """

    base_url: str = "http://localhost:8080"
    api_key: str | None = None
    timeout: float = 30.0
    max_retries: int = 3


def load_config() -> OrchestratorConfig:
    """Build configuration from environment variables.

    ``ORCHESTRATOR_URL`` is the only required variable in production;
    everything else is optional.
    """
    return OrchestratorConfig(
        base_url=os.environ.get("ORCHESTRATOR_URL", "http://localhost:8080").rstrip("/"),
        api_key=os.environ.get("ORCHESTRATOR_API_KEY") or None,
        timeout=float(os.environ.get("ORCHESTRATOR_TIMEOUT", "30.0")),
        max_retries=int(os.environ.get("ORCHESTRATOR_MAX_RETRIES", "3")),
    )
