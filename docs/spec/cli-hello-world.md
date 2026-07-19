# CLI Hello World Spec

Behavior spec for the base `forte` CLI at the scaffold stage. Documents the observable behavior of the entry point before real commands are added.

## Scenarios

### Scenario: Running the CLI with no arguments

```gherkin
Given the `forte` CLI is installed and available on PATH
When the user runs `forte` with no arguments
Then the process prints `hello-world` to stdout
And the process exits with status code 0
```

### Scenario: Requesting help

```gherkin
Given the `forte` CLI is installed and available on PATH
When the user runs `forte --help`
Then the process prints the CLI's help text to stdout
And the help text includes the program name `forte`
And the process exits with status code 0
```

### Scenario: Requesting help via short flag

```gherkin
Given the `forte` CLI is installed and available on PATH
When the user runs `forte -h`
Then the process behaves identically to `forte --help`
```

## Out of scope for MVP scaffold

- `forte --version` — version flag behavior is intentionally undefined at the scaffold stage and will be specified once a versioning strategy is chosen.
- Subcommands and command-specific flags — none exist yet at the scaffold stage.
- Error handling for unknown flags or arguments — deferred until the first real subcommand lands.
