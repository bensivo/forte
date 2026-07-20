# Interview - Project Overview

- **Topic:** Forte project overview (initial scoping, empty repo)
- **Interviewee:** Ben Sivongxay (bensivo@gmail.com)
- **Date:** 2026-07-18

## Summary

**Forte** is a personal knowledge-base tool inspired by Tiago Forte's *Building a Second Brain*. The core problem it addresses is the high manual effort required to maintain a useful second brain: sorting new information, organizing thoughts, linking concepts. Forte's bet is that an AI agent (Claude) can do that organizational work automatically, while keeping the resulting knowledge base fully human-readable.

**Target users:** MVP targets knowledge workers broadly — engineers, researchers, students. Long-term vision is a SaaS product supporting both individual and team/company spaces.

**User workflow:** Users drop raw documents (markdown, docx, PDF, transcripts, etc.) into the system. Forte parses them, extracts entities, links them into a knowledge graph, and stores everything as browsable markdown. Users interact via structured queries (entity search, doc lookup) in MVP; richer graph/UI exploration comes later.

**Architecture (MVP):**
- **Python CLI** exposing primitive operations (chosen over Go for the mature Python document-parsing and LLM ecosystem).
- **Markdown files on the filesystem** as source of truth for docs and entities (human-readable, git-friendly).
- **SQLite** as a derived, rebuildable queryable index to avoid expensive file I/O for graph queries.
- **Claude Haiku** as the default extraction model (cheap/fast; ingest quality is expected to iterate heavily).
- **Manual orchestration** for MVP — user or Claude Code drives the primitive CLI commands with pre-made prompts. A dedicated agent/daemon orchestration layer is a future phase.

**Ingest pipeline** is expected to be multi-step (copy → extract entities → link to existing → create new → extract structured fields) with a **human-in-the-loop TUI review** before finalization. A `--yes`/auto-approve flag is needed so agents can run ingest non-interactively and defer review to later entity edits.

**Schema model:** Users define their own entity kinds ("schemas") via CLI — e.g., Person, Project, Meeting — including fields. "Schema" was chosen over "entity-type"/"kind" because the audience is familiar with the term, and it pairs naturally with "entity" as the instance.

**MVP command surface (draft):**
- `forte init`
- `forte doc ingest <path>` / `doc list` / `doc show <id>`
- `forte schema add/list/remove`
- `forte entity list [--type X]` / `entity show <id>` / `entity search <query>`
- `forte reindex`

**Vault layout:**
```
my-vault/
  .forte/
    index.db
    config.yaml
  docs/
    raw/
    processed/
  entities/
    person/
    project/
```

## Interview Log

**Q:** What is this project called "forte", and in one or two sentences, what problem is it trying to solve or what will it do?

**A:** We're working in the realm of personal knowledge-bases. The big problem is how much manual effort is required to maintain a knowledge base. Based on the book "Second Brain" by Tiago Forte (where the name comes from), it takes a lot of work to sort through new information, organize thoughts and docs, and build a useful second brain. We want to see if there's a way to build tooling around an AI agent like claude to make a second brain that an AI agent can manage and organize, but skill be readable and used by a person.

**Q:** Who is the target user? Is this just for you personally as a first user, or are you envisioning a broader audience (e.g., knowledge workers, researchers, students)? And is it single-user or multi-user from the start?

**A:** For MVP, we'll target any kind of knowledge worker. Engineers, researchers, students. But longer-term, I imagine this being a SaaS product that can support individual spaces as well as team / company spaces.

**Q:** What kinds of information should the knowledge base ingest? (e.g., notes typed by the user, web clippings, PDFs, emails, chat logs, meeting transcripts, code snippets, images) — and for MVP, which of these are must-haves vs. later?

**A:** The idea is that all a user has to do is provide the raw documents, in whatever format they have it in - .md, docx, pdf, transcripts, etc.. then the system can parse them, organize them, and extract relevant information into a knowledge graph and a second brain.

**Q:** What should the *output* / user experience look like? When a user wants to retrieve or use their second brain, what do they interact with? (e.g., a chat interface to ask questions, a browsable graph UI, generated markdown notes they can read/edit, exportable summaries, all of the above?)

**A:** I imagine the user should be able to manually interrogate the entities of the knoweldge graph itself. They should be able to configure whatever kinds of entities they want (like "projects", "people", "meetings", etc.), then see any instances of those entities, as well as see the raw docs that are related to those entities. They should also be able to browse all the raw docs that they've uploaded, like a standard file browser. However, we should talk about MVP scope on this - the interface in the first pass can be much simpler than that.

**Q:** For the MVP interface specifically, what's the minimum you'd want? Some options:
- (a) Pure CLI — upload docs to a folder, run a command, get organized markdown files out
- (b) Local web UI with a file browser and a chat/query box
- (c) Just a structured folder of markdown that the user browses in their own editor (Obsidian, VS Code, etc.), with the AI managing the files behind the scenes
- (d) Something else

Which feels right for MVP?

**A:** Lets start with a CLI. Becuase that's the best way for an Agent to interact with the system too. It also makes it so any core functiosn the agent does, a user can do manually and script if they want.

**Q:** Where does the AI agent live in the architecture? A few models:
- (a) The CLI *is* the agent — user runs `forte ingest ./docs` and Claude (via API/SDK) does the parsing/organizing under the hood
- (b) CLI is dumb tools (ingest, query, list-entities, etc.), and the user runs Claude Code / an external agent that calls those tools
- (c) Both — CLI exposes primitive commands, and there's also a higher-level `forte agent` mode that runs an agentic loop

Which matches your vision?

**A:** What are your thoughts? I definitely want all the primitive opertaions exposed in the CLI, but I can also see the value of another orchestration layer manging the agent, beecause the prompts and orchestration workflows might end up being really complicated, requiring lots of work.

**Q (recommendation):** My take: go with (c), but staged. Start with (b) for MVP — build the primitive CLI commands (`forte ingest`, `forte query`, `forte entity list`, etc.) and let Claude Code be the "agent" for now by calling those tools. This gets you a working system fast, and Claude Code already handles the orchestration/prompt complexity for free. Then, once the primitives are stable and you've learned what workflows actually matter, add `forte agent` as a thin orchestration layer (likely using the Claude Agent SDK) that bakes in the prompts and loops you've validated. This avoids premature investment in orchestration code that you'd throw away. The tradeoff: MVP users need Claude Code (or similar) installed to get the "magic" experience. But since your target is knowledge workers/engineers/researchers, that's an acceptable bar early on. Sound reasonable? And if so — for MVP, do you want the CLI written in a specific language? (Python is natural for AI/parsing ecosystems; Go/Rust for a distributable single binary; Node/TS if you're eyeing the eventual SaaS web stack.)

**A:** I thnk taht's reasonable. We can start wtih B, a CLI with primitive operaitons. And we'll orchestrate *manually* with pre-made prompts. But later, we can add a separate agent app which uses the CLI (or the underlying functions) with premade workflows. That could be another CLI or maybe even a true daemon / service.

**Q:** Language/runtime for the MVP CLI? Python is the natural default given the AI/document-parsing ecosystem (unstructured, pypdf, docx parsers, embedding libs all live there). But you might have other reasons — do you have a preference, or want me to recommend Python?

**A:** Normally for CLIs, I'd go with Golang, but you're right. There's likely goign to be a ton of document pre-processing tasks that will be easier in the python ecosystem. Unless I'm just behind on golang's ecosystem?

**Q (recommendation):** You're not that far behind — Go has grown, but for this domain Python still wins clearly:
- **Document parsing:** `unstructured`, `docling`, `pypdf`, `python-docx`, `markitdown` — all Python, all actively maintained. Go equivalents are thinner (e.g., `unidoc` is commercial, `pdfcpu` is more about manipulation than extraction).
- **Embeddings / vector stores / graph libs:** Python-first across the board (LangChain, LlamaIndex, chromadb, networkx). Go clients exist but lag features.
- **LLM SDKs:** Anthropic ships an official Python SDK; the Go SDK exists but the Python one gets features first.
- **Distribution downside for Python:** harder to ship a single binary. Mitigations: `uv` / `pipx` install, or Docker. For an early adopter audience (engineers/researchers), that's fine.

If distribution simplicity mattered more than ecosystem, Go would win. For MVP with heavy doc-processing, Python is the right call. Going with Python then. Next: for the knowledge graph itself, do you have a preference for storage? Options:
- (a) Plain markdown files + frontmatter in a git-friendly folder (very "Obsidian vault" feeling; graph is derived)
- (b) SQLite with a graph schema (portable single file, easy to query)
- (c) A real graph DB (Neo4j, Kuzu) — more power, more setup
- (d) Hybrid: markdown as source of truth + SQLite/Kuzu as derived index

Given the "readable by a person" requirement, (a) or (d) feel most aligned — but curious what you're thinking.

**A:** Lets go wtih D. I think the raw and processed files can be markdown on the filesystem, but that we'll need some kind of queryable index in sqlite to avoid lengthy query operations stopped by expensive file I/O.

**Q:** How should the user *configure* what entity types exist? You mentioned users defining their own entities (projects, people, meetings, etc.). Options:
- (a) A config file (YAML/TOML) in the vault where users declare entity types + their schemas
- (b) CLI commands (`forte entity-type add Person --field name --field email`)
- (c) Convention-only — entity types emerge from tags/frontmatter the agent invents, no explicit schema
- (d) Start with a small hardcoded set for MVP (Person, Project, Note) and make it configurable later

Which fits?

**A:** CLI commands.

**Q:** For MVP, what's the minimum command surface you want? Here's a strawman — tell me what's missing, wrong, or out of scope:

**Vault / setup**
- `forte init` — create a new vault (folder structure + SQLite index)

**Ingest**
- `forte ingest <path>` — add raw doc(s), parse to markdown, extract entities, update index

**Entity types (schema)**
- `forte entity-type add <name> --field ...`
- `forte entity-type list`
- `forte entity-type remove <name>`

**Entities (instances)**
- `forte entity list [--type X]`
- `forte entity show <id>`
- `forte entity search <query>`

**Docs**
- `forte doc list`
- `forte doc show <id>`

**Index maintenance**
- `forte reindex` — rebuild SQLite from markdown

What would you add/cut for MVP?

**A:** I like it, one feedback is lets put the 'ingest' command in the docs section `forte doc ingest <path>`. For brevity, can you think of other names for 'entity-type'? I don't like that.

**Q:** Good call on `forte doc ingest`. Alternatives for `entity-type`:
- **`schema`** — `forte schema add Person --field name` (clear: it's the shape/schema of an entity)
- **`kind`** — `forte kind add Person` (short, reads well; Kubernetes uses this exact term for the same concept)
- **`class`** — `forte class add Person` (accurate but overloaded with programming meaning)
- **`type`** — `forte type add Person` (shortest, but slightly ambiguous)
- **`concept`** — `forte concept add Person` (knowledge-graph flavored)

My pick: **`kind`**. Short, unambiguous in context, and matches established precedent (K8s, some graph DBs). `schema` is a solid second if you prefer the "shape definition" framing. Which do you want to go with?

**A:** I like schema, I think most people using this will be familiar with that wording. And because we're using 'entity' as the instance it makes sense.

**Q:** Two quick MVP scope questions bundled:

(a) **Querying:** For MVP, do you want a natural-language query command (e.g., `forte query "what did I learn about vector DBs?"` that uses the LLM + index to answer), or just structured commands (`entity search`, `doc show`) and let the user/agent compose?

(b) **LLM usage in ingest:** During `doc ingest`, the LLM does entity extraction. Which model do you want to default to — Haiku (cheap, fast, good enough for extraction) or Sonnet (better accuracy, more expensive)? Configurable either way, but what's the default?

**A:** For MVP, lets just do structured commands, like entity search and doc show.

For `doc ingest`, lets make use simpler models like haiku for entity extraction. I expect we'll work on that a lot in the future, the whole ingest task will have multiple steps (copy doc to system, extract entities, find existing entities and link, create new entities, extract structured fields). In this process, there shoudl also be a way to do human review of all the outputs before finalizing the extracted entiites. That way someone can correct "Nope that project shoudl already exist, under this name" or "That is a person, but I don't care about them, don't save".

**Q:** For the human review step in MVP, what shape? Options:
- (a) Ingest writes a "staging" markdown file per doc listing proposed entities/links; user edits it; `forte doc ingest --finalize <staging-id>` commits
- (b) Interactive TUI prompt during ingest (y/n/edit for each proposed entity)
- (c) Two-phase CLI: `forte doc ingest <path>` produces a review file; `forte doc review <id>` opens it in `$EDITOR`; `forte doc commit <id>` finalizes
- (d) Skip review for MVP — just extract and commit, fix later via `forte entity edit`

Which fits the "agent-friendly + scriptable" ethos best in your mind?

**A:** B.

**Q:** Interactive TUI it is. One flag worth noting: since agents need non-interactive mode too, we'll want a `--yes` / `--auto-approve` flag (or similar) so the agent can run ingest headlessly and defer review to a later `forte entity edit` step. Sound right?

**A:** (Implicitly accepted — moved to next question.)

**Q:** Vault structure — how do you want files laid out on disk? Strawman:

```
my-vault/
  .forte/
    index.db          # SQLite
    config.yaml       # vault config
  docs/
    raw/              # original uploaded files (pdf, docx, etc.)
    processed/        # parsed markdown versions
  entities/
    person/
      jane-doe.md
    project/
      forte.md
```

Anything you'd change — flatter, deeper, different names?

**A:** That's good.
