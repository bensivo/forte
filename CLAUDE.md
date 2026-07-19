# Forte

Forte is a personal knowledge-base tool that offloads the organizational work of maintaining a second brain to an AI agent (Claude) while keeping the resulting knowledge base fully human-readable. Users drop raw documents into a vault; Forte extracts entities, links them into a knowledge graph, and stores everything as browsable markdown alongside a SQLite index.

## Docs Index

The `docs/` folder holds the project's planning and design documentation:

- [docs/project-overview.md](docs/project-overview.md) — high-level overview of the project and its domain (personal knowledge bases, knowledge graphs)
- [docs/prd.md](docs/prd.md) — Product Requirements Document listing the requirements of the MVP (V0)
- [docs/solution-design.md](docs/solution-design.md) — design choices and technical architecture; *how* the MVP will be built
- [docs/index.md](docs/index.md) — index of the files and folders in the docs directory

### docs/input/ — raw context files used as inputs to write other docs (interview transcripts, references)
This folder will build up over time, but usually you don't need to look at it unless asked directly

### docs/impl/ — docs produced during implementation (code plans, todo lists)
This folder containes a folder for each day, and is used for temp files needed during implementation, like task lists, todo lists, implementatino plans. Use this for any of those kinds of temp docs taht you need now, but are not persistent docs for the entire project. 

### docs/spec/ — test specs
This folder contains human-readable test specs, describing teh functional behavior of the system. These are the 'source of truth' for how the app should behave, and drive the building of automated test cases. Generally 1 file per group of features, with each file containing multiple scenarios in Gherkin-style syntax.