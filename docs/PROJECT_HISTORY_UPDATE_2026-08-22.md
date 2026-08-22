# Skippey — Project History Update

## 2026-08-22 — Memory, Runtime, and Deployment Milestone

This update records the latest engineering work after the Graphiti/Neo4j memory experiments.

### Memory architecture

- Added a PostgreSQL temporary-memory layer using `pgvector`.
- Temporary memories use the minimal representation:
  - `memory`
  - `vector`
  - `created_at`
- Removed the earlier importance/access-count based design from temporary memory.
- Memory retrieval now combines PostgreSQL and Neo4j/Graphiti results.
- Graphiti recall was moved toward configurable cosine-similarity filtering instead of relying only on a fixed number of returned memories.
- Retrieved memories are represented with their source and timestamp so Skippey can reason about where and when a memory originated.
- Current date/time is supplied separately to the main model when available rather than relying on stored memories for real-time information.
- Retrieved memory is injected as separate context instead of being merged into the user's message.
- Skippey's generated response can also be passed through the memory pipeline so the conversation can contribute to future memory.
- Recall is intended to be selective: unrelated messages such as casual conversation or jokes should not automatically retrieve project memories.
- Testing exposed an important retrieval issue: vague references such as "the project I've been working on" depend heavily on the memory manager generating a useful semantic recall query before vector/Graphiti search can happen.

### Graphiti search integration

- Updated the Graphiti search handling to account for the current `search_()` return structure.
- Graphiti search results are returned as `(field, value)` tuples; the `edges` field must be extracted before accessing `EntityEdge.fact` and temporal fields.
- Recall results use the Graphiti edge facts and their timestamps as long-term memory context.
- Retrieval threshold tuning is being treated separately from the memory-manager decision of whether a recall query should be generated.

### Skippey runtime

- `skippey.py` now keeps actual user/assistant conversation history separate from retrieved memory context.
- Added terminal UI improvements with distinct colors and bold labels for user and Skippey messages.
- Added current-time context to the model input.
- Conversation history remains bounded to avoid unbounded prompt growth.
- Skippey continues to run Qwen3 locally through Ollama.

### Docker and deployment

The runtime is now organized as a Docker Compose stack containing:

```text
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

- Added Dockerfile and Docker Compose configuration.
- Added `.dockerignore`.
- Removed the old `router.py` prototype.
- Removed the local `.venv` from the project workflow.
- Credentials were moved out of hardcoded Compose configuration into environment variables.
- Added `.env` to `.gitignore` and retained `.env.example` for reproducible configuration.

### Current direction

The next major architectural component is the sleep/maintenance pipeline. The intended flow is:

```text
Conversation
    ↓
Temporary memory
    ↓
Sleep / maintenance
    ├── discard weak or useless memories
    ├── consolidate duplicates
    ├── resolve/update temporal information
    └── promote useful memories
             ↓
       Long-term memory
```

The goal is for Skippey to avoid treating every conversational statement as permanent knowledge while still developing persistent, useful memory over time.
