# Config Writer Spec

Behavior spec for the default `config.yaml` writer used by `forte init`. Documents the observable behavior of `write_default_config` in `src/forte/services/config.py`.

## Scenarios

### Scenario: Writing the default config to a fresh path

```gherkin
Given a path that does not yet exist on disk
When `write_default_config(path)` is called
Then a file is created at that path
And the file is non-empty
And the file contains a comment line (starting with `#`)
And the file contains no YAML keys
```

### Scenario: Refusing to overwrite an existing config

```gherkin
Given a path where a file already exists
When `write_default_config(path)` is called
Then the call raises `FileExistsError`
And the existing file's contents are not modified
```

## Out of scope for MVP

- Real config keys (`model`, `api_keys`, etc.) — the placeholder file intentionally has none until a feature actually reads one.
- YAML parsing / `pyyaml` dependency — deferred until the first real key is introduced.
- Creating parent directories — the caller (`forte init`) is responsible for ensuring `.forte/` exists before invoking the writer.
