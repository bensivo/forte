# CLI Base Spec

Behavior spec for the base `forte` CLI entry point: what happens when the user runs `forte` with no subcommand, requests help, or references a registered subcommand.

## Scenarios

### Scenario: Running the CLI with no arguments shows help

```gherkin
Given the `forte` CLI is installed and available on PATH
When the user runs `forte` with no arguments
Then the process prints the CLI's help text to stdout
And the help text includes the program name `forte`
And the help text lists the `init` subcommand
And the process exits with status code 0
```

### Scenario: Requesting help via long flag

```gherkin
Given the `forte` CLI is installed and available on PATH
When the user runs `forte --help`
Then the process prints the CLI's help text to stdout
And the help text includes the program name `forte`
And the help text lists the `init` subcommand
And the process exits with status code 0
```

### Scenario: Requesting help via short flag

```gherkin
Given the `forte` CLI is installed and available on PATH
When the user runs `forte -h`
Then the process behaves identically to `forte --help`
```

### Scenario: `init` is a registered subcommand

```gherkin
Given the `forte` CLI is installed and available on PATH
When the user runs `forte --help`
Then the help text lists `init` in the Commands section
```

## Out of scope for MVP scaffold

- `forte --version` — version flag behavior is intentionally undefined at the scaffold stage and will be specified once a versioning strategy is chosen.
- Error handling for unknown flags or arguments — deferred until multiple real subcommands exist.
- Behavior of individual subcommands — covered in their own specs (e.g. the `forte init` spec).
