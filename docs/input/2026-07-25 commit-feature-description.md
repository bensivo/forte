# Commit Feature

Describes a feature that I want. 

Context: 
- When a user runs through `forte agent ingest <filepath>`, there are usually many entities extracted from the doc, many of which are fine, but some of which are not important to the user. 
- Currently, the user has to one-by-one hit 'y/n' on each extracted entity to confirm whether to push it to the forte vault.

Issue:
- It quickly gets tedious to review each entity one at a time. 


Solution:
- Give an option during agent ingest `--bulk-commit`, which does this:
  - instead of offering all entities one-by-one, open a git-style text editor (default to vi,vim,nano, configurable in settings) which shows each extracted entity on a line,
  - users modify the file to update all entities, setting a value for each

e.g.
```
###############
# Extracted Entity Bulk Commit. 
#
# Review all proposed entities and links. To reject a line, change the [y] to [n], or delete the line
# When you are done, save and close the editor to bulk commit all changes. 
###############

# New Entities
[y] [person] Alice
[y] [person] Bob
[y] [person] Charlie

# Links to existing entities
[y] #1 [project] Manhattan Project
[y] #2 [project] Project Hail Mary

```