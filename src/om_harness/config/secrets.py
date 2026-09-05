"""Secret redaction: credentials never reach events, logs, or checkpoints."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

REDACTED = "***REDACTED***"

# Exact key names whose values are always sensitive regardless of content.
SENSITIVE_KEY_NAMES = {
    "token",
    "auth",
    "authentication",
    "api_key",
    "apikey",
    "access_token",
    "auth_token",
    "bearer_token",
    "refresh_token",
    "session_token",
    "password",
    "passwd",
    "secret",
    "secret_key",
    "credentials",
    "authorization",
    "proxy_authorization",
}

# Substring patterns for compound names (kept narrow so usage metrics like
# ``input_tokens``/``output_tokens`` are NOT redacted).
SENSITIVE_KEY_SUBSTRINGS = (
    "api_key",
    "apikey",
    "secret",
    "password",
    "authorization",
    "credential",
)


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    if lowered in SENSITIVE_KEY_NAMES:
        return True
    return any(pattern in lowered for pattern in SENSITIVE_KEY_SUBSTRINGS)


STANDARD_KEY_VARS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "OPENROUTER_API_KEY",
    "GROQ_API_KEY",
    "MISTRAL_API_KEY",
)


class SecretRedactor:
    """Replaces known secret values and obviously-secret keys with a marker.

    Applied at the event bus so every downstream consumer (UI, logs, event
    store) is covered by one mechanism.
    """

    def __init__(self, secrets: list[str] | tuple[str, ...] = ()) -> None:
        # Longest first so overlapping secrets are fully covered.
        self._secrets = sorted({s for s in secrets if s and len(s) >= 6}, key=len, reverse=True)

    @classmethod
    def from_env(cls, env: Mapping[str, str], extra: list[str] | None = None) -> SecretRedactor:
        secrets = [env[name] for name in STANDARD_KEY_VARS if env.get(name)]
        # Allow extra custom key vars, e.g. OM_HARNESS_EXTRA_API_KEY.
        secrets += [
            v for k, v in env.items() if k.startswith("OM_HARNESS_") and "API_KEY" in k and v
        ]
        # Extra secrets from configuration (e.g. inline keys in models.json).
        if extra:
            secrets += [s for s in extra if s]
        return cls(secrets)

    def redact_text(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, REDACTED)
        return text

    def redact_value(self, value: Any) -> Any:
        """Recursively redact strings in dicts/lists/tuples and by key name."""
        if isinstance(value, str):
            return self.redact_text(value)
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for key, item in value.items():
                if isinstance(key, str) and _is_sensitive_key(key):
                    out[key] = REDACTED
                else:
                    out[key] = self.redact_value(item)
            return out
        if isinstance(value, list):
            return [self.redact_value(v) for v in value]
        if isinstance(value, tuple):
            return tuple(self.redact_value(v) for v in value)
        return value
