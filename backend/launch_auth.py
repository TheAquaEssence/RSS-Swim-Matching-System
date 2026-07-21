"""Per-launch capability-token helpers for desktop-hosted backend access."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field


LAUNCH_TOKEN_ENV = "AQUA_LAUNCH_TOKEN"
LAUNCH_TOKEN_HEADER = "X-Aqua-Launch-Token"
_PUBLIC_API_PATHS = frozenset({"/api/health", "/api/ready"})


def generate_launch_token() -> str:
    """Return a cryptographically strong token for one backend process launch."""

    return secrets.token_urlsafe(32)


def launch_token_from_environment() -> str | None:
    """Read the desktop-supplied token without generating or exposing one."""

    value = os.environ.get(LAUNCH_TOKEN_ENV)
    return value if value else None


def requires_launch_token(path: str) -> bool:
    """Identify API and private-data paths covered by capability authentication."""

    if path in _PUBLIC_API_PATHS:
        return False
    return (
        path == "/api"
        or path.startswith("/api/")
        or path == "/jobs"
        or path.startswith("/jobs/")
        or path == "/xai"
        or path.startswith("/xai/")
    )


@dataclass(frozen=True)
class LaunchTokenAuth:
    """Optional per-application capability-token validator."""

    _token: bytes | None = field(repr=False)

    @classmethod
    def configured(cls, token: str | None) -> "LaunchTokenAuth":
        return cls(token.encode("utf-8") if token else None)

    @property
    def enabled(self) -> bool:
        return self._token is not None

    def accepts(self, presented: str | None) -> bool:
        """Validate a presented token in constant time when auth is enabled."""

        if self._token is None:
            return True
        try:
            candidate = (presented or "").encode("utf-8")
        except UnicodeEncodeError:
            return False
        return secrets.compare_digest(candidate, self._token)
