We're changing how vaults are managed, accessed, and configured. 

Current state:
- Users run `forte init` in a dir to create a new vault (a .forte/ directory)
- When running forte, the app looks up from the current dir to find `.forte`, and if it gets to root, there's no vault


New behavior:
- We want vaults to exist anywhere on the filesystem, but should all be indexed in a user-level app directory
- Users would run `forte vault create <name> .` to create a new vault at a specific location. This does not create a .forte folder, btu just the standard folders directly, and 'forte.db' and 'forte.yaml' in that folder
- The vault is also registered in a user-level config at ~/.forte/
- A new command `forte vault set-default <name>` can be used to set the default vault
- Any other commands, `forte doc ingest` or `forte schema add` work out of the default vault, unless a separate one is passed with a --vault parameter. 


Implementation
- Create a VaultService, with these functions:
  - create_vault(name, path)
  - list_vaults()
  - get_vault(name)
  - remove_vault(name)
  - set_default_vault(name)

- Expose those services in a CliVaultController, with these click commands:
  - `forte vault add`
  - `forte vault list`
  - `forte vault show`
  - `forte vault remove`
  - NOTE: for now, there is no 'edit' vault command.
  
- Update all other commands to either find the DB and folder from the default vault, or the vault that's passed in. 