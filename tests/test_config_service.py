"""Tests for the config reader (load_config / require_api_key)."""

from __future__ import annotations

import pytest

from forte.domain.vault import VaultLayout
from forte.services.config import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_EXTRACTION_MODEL,
    Config,
    MissingAPIKeyError,
    load_config,
    require_api_key,
    write_default_config,
)


def _write_config(root, contents: str) -> None:
    layout = VaultLayout(root)
    layout.forte_dir.mkdir(parents=True, exist_ok=True)
    layout.config_path.write_text(contents, encoding="utf-8")


def test_default_model_when_unset(tmp_path):
    _write_config(tmp_path, "api_keys:\n  anthropic: literal-key\n")
    config = load_config(tmp_path)
    assert config.extraction_model == DEFAULT_EXTRACTION_MODEL
    assert config.extraction_model == "claude-haiku-4-5"


def test_explicit_model_override(tmp_path):
    _write_config(tmp_path, "model:\n  extraction: claude-sonnet-4-5\n")
    config = load_config(tmp_path)
    assert config.extraction_model == "claude-sonnet-4-5"


def test_env_var_interpolation_when_set(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-from-env")
    _write_config(tmp_path, "api_keys:\n  anthropic: ${ANTHROPIC_API_KEY}\n")
    config = load_config(tmp_path)
    assert config.anthropic_api_key == "sk-from-env"


def test_env_var_interpolation_when_unset_is_none(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _write_config(tmp_path, "api_keys:\n  anthropic: ${ANTHROPIC_API_KEY}\n")
    config = load_config(tmp_path)
    assert config.anthropic_api_key is None


def test_literal_api_key_used_as_is(tmp_path):
    _write_config(tmp_path, "api_keys:\n  anthropic: sk-literal\n")
    config = load_config(tmp_path)
    assert config.anthropic_api_key == "sk-literal"


def test_missing_config_file_uses_defaults(tmp_path):
    config = load_config(tmp_path)
    assert config.extraction_model == "claude-haiku-4-5"
    assert config.anthropic_api_key is None


def test_default_written_config_round_trips(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-round-trip")
    layout = VaultLayout(tmp_path)
    layout.forte_dir.mkdir(parents=True, exist_ok=True)
    write_default_config(layout.config_path)
    config = load_config(tmp_path)
    assert config.extraction_model == "claude-haiku-4-5"
    assert config.embedding_model == "sentence-transformers/all-MiniLM-L6-v2"
    assert config.anthropic_api_key == "sk-round-trip"


def test_require_api_key_raises_when_none():
    config = Config(
        extraction_model="claude-haiku-4-5",
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        anthropic_api_key=None,
    )
    with pytest.raises(MissingAPIKeyError):
        require_api_key(config)


def test_require_api_key_returns_key_when_present():
    config = Config(
        extraction_model="claude-haiku-4-5",
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        anthropic_api_key="sk-123",
    )
    assert require_api_key(config) == "sk-123"


def test_default_embedding_model_when_unset(tmp_path):
    _write_config(tmp_path, "model:\n  extraction: claude-haiku-4-5\n")
    config = load_config(tmp_path)
    assert config.embedding_model == DEFAULT_EMBEDDING_MODEL
    assert config.embedding_model == "sentence-transformers/all-MiniLM-L6-v2"


def test_explicit_embedding_model_override(tmp_path):
    _write_config(tmp_path, "embedding:\n  model: custom-model-v1\n")
    config = load_config(tmp_path)
    assert config.embedding_model == "custom-model-v1"


def test_unknown_keys_in_embedding_section_dont_break_parsing(tmp_path):
    _write_config(
        tmp_path,
        "embedding:\n  model: sentence-transformers/all-MiniLM-L6-v2\n  dimension: 384\n  extra_key: value\n",
    )
    config = load_config(tmp_path)
    assert config.embedding_model == "sentence-transformers/all-MiniLM-L6-v2"
