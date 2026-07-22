"""Config file writer and reader for Forte vaults.

The vault's ``.forte/config.yaml`` holds settings that features read at
runtime — currently the extraction model id and the Anthropic API key. Keys
may use ``${VAR}`` interpolation so a committed config never contains a raw
secret; :func:`load_config` resolves those against the process environment.

The reader is deliberately tolerant: a missing file or missing keys fall back
to documented defaults rather than raising, so deterministic commands work
without any config. The only typed failure, :class:`MissingAPIKeyError`, is
exposed for callers on the agent path to raise via :func:`require_api_key`
when they actually need a key — :func:`load_config` itself never raises it.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from forte.domain.vault import VaultLayout

DEFAULT_EXTRACTION_MODEL = "claude-haiku-4-5"
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

DEFAULT_CONFIG_CONTENT = (
    "# Forte vault config.\n"
    "model:\n"
    "  extraction: claude-haiku-4-5\n"
    "embedding:\n"
    "  model: sentence-transformers/all-MiniLM-L6-v2\n"
    "api_keys:\n"
    "  anthropic: ${ANTHROPIC_API_KEY}\n"
)

_ENV_VAR_PATTERN = re.compile(r"^\$\{(?P<name>[^}]+)\}$")


class ConfigError(Exception):
    """Base class for config service errors."""


class MissingAPIKeyError(ConfigError):
    """Raised when an operation needs an Anthropic API key but none is set."""


@dataclass(frozen=True)
class Config:
    """Resolved Forte vault configuration."""

    extraction_model: str
    embedding_model: str
    anthropic_api_key: str | None


def write_default_config(path: Path) -> None:
    """Write the default Forte config file to `path`.

    Raises:
        FileExistsError: if `path` already exists.
    """
    if path.exists():
        raise FileExistsError(f"Config file already exists: {path}")

    path.write_text(DEFAULT_CONFIG_CONTENT, encoding="utf-8")


def _resolve_api_key(raw: object) -> str | None:
    """Resolve an ``api_keys.anthropic`` value to a concrete key or None.

    A ``${VAR}`` string is interpolated from the environment (unset or empty
    → ``None``). Any other non-empty string is used literally. Missing/blank
    values resolve to ``None``.
    """
    if not isinstance(raw, str):
        return None
    match = _ENV_VAR_PATTERN.match(raw.strip())
    if match is not None:
        value = os.environ.get(match.group("name"), "")
        return value or None
    return raw or None


def load_config(root: Path) -> Config:
    """Read ``.forte/config.yaml`` from the vault at ``root`` into a Config.

    Tolerates a missing file and missing keys by falling back to defaults:
    ``extraction_model`` defaults to ``claude-haiku-4-5``,
    ``embedding_model`` to ``sentence-transformers/all-MiniLM-L6-v2``, and
    ``anthropic_api_key`` to ``None``. Does not raise
    :class:`MissingAPIKeyError` — callers needing a key use
    :func:`require_api_key`.
    """
    config_path = VaultLayout(root).config_path

    data: dict = {}
    if config_path.exists():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded

    model_section = data.get("model")
    extraction_model = DEFAULT_EXTRACTION_MODEL
    if isinstance(model_section, dict):
        value = model_section.get("extraction")
        if isinstance(value, str) and value:
            extraction_model = value

    api_keys_section = data.get("api_keys")
    anthropic_api_key = None
    if isinstance(api_keys_section, dict):
        anthropic_api_key = _resolve_api_key(api_keys_section.get("anthropic"))

    embedding_section = data.get("embedding")
    embedding_model = DEFAULT_EMBEDDING_MODEL
    if isinstance(embedding_section, dict):
        value = embedding_section.get("model")
        if isinstance(value, str) and value:
            embedding_model = value

    return Config(
        extraction_model=extraction_model,
        embedding_model=embedding_model,
        anthropic_api_key=anthropic_api_key,
    )


def require_api_key(config: Config) -> str:
    """Return the resolved Anthropic API key or raise MissingAPIKeyError."""
    if not config.anthropic_api_key:
        raise MissingAPIKeyError(
            "Set ANTHROPIC_API_KEY or configure api_keys.anthropic in .forte/config.yaml"
        )
    return config.anthropic_api_key
