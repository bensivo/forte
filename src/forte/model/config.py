"""Resolved Forte vault configuration and its errors.

A vault's ``forte.yaml`` holds settings that features read at runtime —
currently the extraction model id, the Anthropic API key, and the editor
command. :class:`Config` is the resolved (post-default, post-interpolation)
view of that file that the rest of the app depends on.
"""

from dataclasses import dataclass

# Fallback extraction model used when `forte.yaml` is missing or omits
# `model.extraction`.
DEFAULT_EXTRACTION_MODEL = "claude-haiku-4-5"


@dataclass(frozen=True)
class Config:
    """Resolved Forte vault configuration."""

    extraction_model: str
    anthropic_api_key: str | None
    # Top-level `editor:` key in forte.yaml. Literal command name or path (no
    # env-var interpolation); the precedence logic ($VISUAL → $EDITOR → this
    # value → fallback) lives with the editor-session controller, not here.
    editor: str | None


class ConfigError(Exception):
    """Base class for config errors."""


class MissingAPIKeyError(ConfigError):
    """Raised when an operation needs an Anthropic API key but none is set."""
