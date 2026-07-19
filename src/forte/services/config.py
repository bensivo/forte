"""Config file writer for Forte vaults."""

from pathlib import Path

DEFAULT_CONFIG_CONTENT = (
    "# Forte vault config - settings will be added here as features need them.\n"
)


def write_default_config(path: Path) -> None:
    """Write the default Forte config file to `path`.

    Raises:
        FileExistsError: if `path` already exists.
    """
    if path.exists():
        raise FileExistsError(f"Config file already exists: {path}")

    path.write_text(DEFAULT_CONFIG_CONTENT, encoding="utf-8")
