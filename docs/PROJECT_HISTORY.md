# Skippey — Project History

Skippey is a fully local, privacy-preserving AI assistant with persistent long-term memory. It runs entirely on-device (Qwen3 via Ollama) and is built around a dedicated memory-management pipeline rather than relying on a single large model to both converse and manage its own memory.

This document tracks the project as a single continuous timeline, from the earliest prototype to the current architecture and its next planned stage.

---

## v0 — Stateless Chat
Initial prototype used the NVIDIA API for inference with no memory system. The assistant could hold a conversation but retained nothing across turns or sessions.

## v1 — Vector-Backed Retrieval
Introduced PostgreSQL with `pgvector` and a Hugging Face embedding model to store and retrieve conversational memory by similarity search. This gave Skippey basic recall, but memory management (deciding what to store, update, or discard) was not yet a distinct responsibility.

## v2 — Tool-Calling Memory Manager
Refactored memory operations (remember, update, forget, recall) into explicit tools the model could invoke. In practice, small models lacked the reasoning reliability to select tools correctly, while models large enough to be reliable were too slow and costly for real-time use — motivating a split between a lightweight memory-management model and the main conversational model. Results were more consistent but still not fully reliable.

## v3 — Knowledge Graph Memory (Graphiti / Neo4j)
Replaced flat vector storage with a Graphiti-backed Neo4j knowledge graph for long-term memory, enabling structured, temporally-aware relationships between memories rather than isolated embeddings. The two-tier design was retained: a dedicated memory-manager model (now running Qwen3 via Ollama) handles retrieval and storage decisions, while the main model focuses on generating responses. Explicit "update" operations were simplified — new information is appended rather than requiring separate update logic.

## v4 — Hybrid Temporary + Graph Memory

Building on the Graphiti/Neo4j foundation, memory was split into a fast temporary layer and the existing long-term graph layer, with retrieval combining both:

- Added a PostgreSQL temporary-memory layer using `pgvector`, with a minimal schema: `memory`, `vector`, `created_at`.
- Removed the earlier importance/access-count-based design from temporary memory in favor of this simpler representation.
- Memory retrieval now combines results from PostgreSQL and Neo4j/Graphiti.
- Graphiti recall moved from a fixed-count result window to configurable cosine-similarity filtering.
- Retrieved memories carry their source and timestamp, so Skippey can reason about where and when a memory originated.
- Current date/time is supplied directly to the main model rather than relying on stored memories for real-time information.
- Retrieved memory is injected as separate context rather than merged into the user's message.
- Skippey's own generated responses can be passed through the memory pipeline, allowing the conversation itself to contribute to future memory.
- Recall is intentionally selective — casual conversation and unrelated messages should not trigger project-memory retrieval.
- Testing surfaced a key retrieval dependency: vague references (e.g., "the project I've been working on") rely on the memory manager generating a useful semantic recall query before vector/Graphiti search can succeed.

Alongside this, the Graphiti search integration itself was updated:

- Updated Graphiti search handling to match the current `search_()` return structure.
- Graphiti search results return as `(field, value)` tuples; the `edges` field must be extracted before accessing `EntityEdge.fact` and its temporal fields.
- Recall now uses Graphiti edge facts and their timestamps as long-term memory context.
- Retrieval threshold tuning is treated as a separate concern from the memory manager's decision of whether to generate a recall query at all.

## v5 — Runtime and Deployment Hardening

With the memory architecture stabilizing, focus shifted to the runtime and how the project is packaged and run:

**Runtime**
- `skippey.py` now keeps live conversation history separate from retrieved memory context.
- Added terminal UI improvements: distinct colors and bold labels for user and Skippey messages.
- Added current-time context to model input.
- Conversation history remains bounded to prevent unbounded prompt growth.
- Continues to run Qwen3 locally via Ollama.

**Docker and Deployment**

The runtime is now organized as a Docker Compose stack:

```
Skippey
├── Python application
├── Memory manager
└── Graphiti/BGE components

Neo4j
└── persistent graph storage

PostgreSQL + pgvector
└── temporary/vector memory

Ollama
└── local Qwen3 inference
```

- Added `Dockerfile` and Docker Compose configuration.
- Added `.dockerignore`.
- Removed the old `router.py` prototype.
- Removed local `.venv` from the project workflow.
- Moved credentials out of hardcoded Compose configuration into environment variables.
- Added `.env` to `.gitignore`; retained `.env.example` for reproducible configuration.

## v6 (Planned) — Sleep / Maintenance Pipeline

The next major architectural component is a sleep/maintenance cycle for memory consolidation:

```
Conversation
    ↓
Temporary memory
    ↓
Sleep / Maintenance
    ├── discard weak or useless memories
    ├── consolidate duplicates
    ├── resolve/update temporal information
    └── promote useful memories
             ↓
       Long-term memory
```

The goal is for Skippey to avoid treating every conversational statement as permanent knowledge, while still building persistent, useful memory over time — modeled loosely on biological memory consolidation.
