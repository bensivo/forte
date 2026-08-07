import os
import re

from forte.interface.config_store import IConfigStore
from forte.model.config import DEFAULT_EXTRACTION_MODEL, Config, MissingAPIKeyError

# Matches a `${VAR_NAME}` value so it can be interpolated against the process
# environment instead of being used literally.
_ENV_VAR_PATTERN = re.compile(r"^\$\{(?P<name>[^}]+)\}$")


class ConfigService:
    """
    Contains all the operations for resolving a vault's configuration:
    reading its raw `forte.yaml` data (via the injected IConfigStore),
    applying defaults, and resolving `${VAR}` interpolation.

    Reading is deliberately tolerant: a missing file or missing keys fall
    back to documented defaults rather than raising, so deterministic
    commands work without any config. The only typed failure,
    MissingAPIKeyError, is raised only by `require_api_key`, for callers on
    the agent path that actually need a key.
    """

    def __init__(self, config_store: IConfigStore):
        """
        Args:
            config_store (IConfigStore): Storage backend for the vault's raw
                config data.
        """
        self._config_store = config_store

    def get_config(self) -> Config:
        """
        Resolve the active vault's configuration.

        Tolerates a missing file and missing keys by falling back to
        defaults: `extraction_model` defaults to `claude-haiku-4-5`,
        `anthropic_api_key` and `editor` to None. Never raises
        MissingAPIKeyError — callers needing a key use `require_api_key`.

        Returns:
            (Config) The resolved configuration.

        Raises:
            NoDefaultVaultError: if no vault is selected (propagated from the
                injected VaultContext, via the config store).
        """
        data = self._config_store.read()

        model_section = data.get("model")
        extraction_model = DEFAULT_EXTRACTION_MODEL
        if isinstance(model_section, dict):
            value = model_section.get("extraction")
            if isinstance(value, str) and value:
                extraction_model = value

        api_keys_section = data.get("api_keys")
        anthropic_api_key = None
        if isinstance(api_keys_section, dict):
            anthropic_api_key = self._resolve_api_key(api_keys_section.get("anthropic"))

        editor = None
        value = data.get("editor")
        if isinstance(value, str) and value:
            editor = value

        return Config(
            extraction_model=extraction_model,
            anthropic_api_key=anthropic_api_key,
            editor=editor,
        )

    def require_api_key(self) -> str:
        """
        Resolve the active vault's configuration and return its Anthropic
        API key, raising if none is set.

        Returns:
            (str) The resolved Anthropic API key.

        Raises:
            MissingAPIKeyError: if the resolved config has no Anthropic API
                key set.
            NoDefaultVaultError: if no vault is selected (propagated from the
                injected VaultContext, via the config store).
        """
        config = self.get_config()
        if not config.anthropic_api_key:
            raise MissingAPIKeyError(
                "Set ANTHROPIC_API_KEY or configure api_keys.anthropic in forte.yaml"
            )
        return config.anthropic_api_key

    @staticmethod
    def _resolve_api_key(raw: object) -> str | None:
        """Resolve an `api_keys.anthropic` value to a concrete key or None.

        A `${VAR}` string is interpolated from the environment (unset or
        empty -> None). Any other non-empty string is used literally.
        Missing/blank values resolve to None.
        """
        if not isinstance(raw, str):
            return None
        match = _ENV_VAR_PATTERN.match(raw.strip())
        if match is not None:
            value = os.environ.get(match.group("name"), "")
            return value or None
        return raw or None
