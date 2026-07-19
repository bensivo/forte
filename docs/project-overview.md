# Project Overview

## Domain - Knowledge Bases, Knowledge Graphs

Forte lives in the personal knowledge-base space, inspired by Tiago Forte's *Building a Second Brain*. A second brain is a personal, durable store of the information a knowledge worker cares about — notes, documents, meeting transcripts, references, ideas — organized so it can be revisited, connected, and built upon over time.

The natural structure for a mature second brain is a knowledge graph: entities (people, projects, meetings, concepts) linked to each other and to the raw source documents they came from. Users should be able to traverse from a document to the entities it mentions, from an entity to every document that references it, and across related entities.

## Problem Statement

Maintaining a useful second brain takes a lot of manual effort. Users have to sort through new information as it arrives, decide where it belongs, extract the concepts and people and projects worth tracking, link them back to existing notes, and keep the whole structure coherent as it grows. That upkeep cost is high enough that most people either never build a second brain or let the one they started rot.

At the same time, the resulting knowledge base has to stay human-readable and human-owned. A system that hides everything behind a proprietary format or an opaque AI blob defeats the purpose — users need to trust what's in there, browse it directly, and take it with them.

## Product Pitch

Forte is a personal knowledge-base tool that offloads the organizational work of maintaining a second brain to an AI agent (Claude), while keeping the resulting knowledge base fully human-readable.

The user's job is to drop raw documents — markdown, docx, PDF, transcripts, whatever they have — into the system. Forte parses them, extracts the entities that matter (people, projects, meetings, and other kinds the user defines), links them into a knowledge graph, and stores the result as browsable markdown files on the filesystem. Users can then query the graph, look up entities and documents, and explore how everything connects.

**Target users.** The MVP is aimed at knowledge workers broadly — engineers, researchers, students — anyone who accumulates documents and wants them organized without doing the organizing themselves. The long-term vision is a SaaS product supporting both individual users and team/company spaces.
