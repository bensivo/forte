"""Tests for the default config.yaml writer."""

import pytest

from forte.services.config import write_default_config


def test_write_default_config_creates_nonempty_file_with_comment(tmp_path):
    config_path = tmp_path / "config.yaml"

    write_default_config(config_path)

    assert config_path.exists()
    contents = config_path.read_text(encoding="utf-8")
    assert contents.strip() != ""
    assert any(line.lstrip().startswith("#") for line in contents.splitlines())


def test_write_default_config_refuses_to_overwrite(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("existing content\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        write_default_config(config_path)

    assert config_path.read_text(encoding="utf-8") == "existing content\n"
