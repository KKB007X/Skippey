# Skippey — Project History

> This document records the evolution of Skippey's architecture and the reasoning behind major changes. It is intentionally written as an engineering history rather than a snapshot of the current implementation.
>
> Historical details before the current repository state were reconstructed from the project's development work. Performance numbers are only recorded when they were actually measured; unmeasured claims are marked as such.

## 1. Original goal

Skippey started as an attempt to build a personal AI assistant with persistent memory rather than a stateless chat interface.

The core requirements that emerged were:

- remember useful information from conversations;
- retrieve relevant memories later;
- keep memory persistent across program restarts;
- allow memories to be reinforced rather than expiring on a fixed TTL;
- eventually separate short-lived context from durable long-term memory;
- keep the LLM local so the assistant does not fundamentally depend on an internet connection;
- make the system portable and reproducible.

The memory system therefore became a project of its own rather than just a database attached to the assistant.

---

## 2. First generation — hosted LLM + PostgreSQL/pgvector

The first memory design used PostgreSQL as the persistent store and vector embeddings for semantic retrieval.

The initial LLM integration used the NVIDIA API. The model used during the early experiments was `meta/llama-3.1-8b-instruct`.

### Memory representation

The early database contained a `memories` table with the main fields:

- `id`
- `memory` — the stored text
- `embedding` — a vector embedding
- `importance`
- `created_at`
- `last_accessed`
- `access_count`

The embedding model used was Sentence Transformers `all-MiniLM-L6-v2`, producing 384-dimensional embeddings.

An HNSW index with cosine distance was added for semantic retrieval.

### Why this design made sense

PostgreSQL was already familiar and gave the project both normal relational storage and vector search in one database. Embeddings made it possible to retrieve memories by meaning instead of requiring exact keyword matches.

### Memory decay idea

The first design also introduced the idea that memories should not simply disappear after a fixed amount of time. Instead, persistence should depend on factors such as:

- importance;
- recency;
- how often a memory is recalled or used.

This became the conceptual basis for later temporary/long-term memory promotion.

### Limitations discovered

The vector-only representation was good at similarity search but did not naturally represent entities and relationships between them. As the intended assistant became more sophisticated, the memory model needed to represent facts such as relationships between the user, projects, tools, models, and preferences.

---

## 3. Local inference became a requirement

A major architectural goal was added: Skippey should not rely on an internet connection for its core intelligence.

The LLM was therefore moved from the NVIDIA API to local inference through Ollama.

Qwen3 became the local model used by the memory system, initially `qwen3:4b-instruct`.

This changed the architecture from:

```text
Skippey → NVIDIA API → LLM
```

to:

```text
Skippey → Ollama → Qwen3
```

### Why

The local approach gives the project:

- offline-capable LLM inference;
- control over the model and its runtime;
- no per-request API cost for the local model;
- a path toward running the complete assistant on a future local GPU machine.

The trade-off is that local inference depends on available hardware and model size.

---

## 4. Graph memory — Neo4j + Graphiti

The next major architectural change was moving the persistent memory representation from PostgreSQL/pgvector to Neo4j with Graphiti.

Graphiti became responsible for constructing the temporal knowledge graph from memory episodes.

The system began using:

- Neo4j for graph persistence;
- Graphiti for episode processing, entity extraction, relationships, temporal graph construction, and retrieval;
- BGE embeddings for semantic representation;
- a BGE reranker for retrieval refinement.

### Why the graph approach

The important difference was that memories could now be represented as connected facts instead of isolated vectors.

Conceptually:

```text
             ┌──────────┐
             │  Chris   │
             └────┬─────┘
                  │
               builds
                  │
                  ▼
             ┌──────────┐
             │ Skippey  │
             └────┬─────┘
                  │
                uses
                  │
          ┌───────┴────────┐
          ▼                ▼
       Neo4j             Qwen3
```

The graph therefore became useful for both semantic retrieval and explicit relationships.

---

## 5. BGE embedding and reranking

The local embedding model was changed to `BAAI/bge-large-en-v1.5`.

Graphiti was also configured with `BAAI/bge-reranker-v2-m3` through its BGE reranker client.

The important architectural distinction is:

```text
Embedding model
    ↓
semantic candidate retrieval
    ↓
reranker
    ↓
more relevant results
```

This introduced additional local computation compared with the earlier vector-only pipeline, but gave the graph memory system stronger semantic retrieval capabilities.

The models are downloaded once and cached locally; later the cache was persisted through Docker volumes.

---

## 6. Temporary memory and long-term memory

A single undifferentiated memory store was not sufficient for the intended assistant.

The design evolved toward two Graphiti groups:

- `skippey_temp` — recent/temporary memories;
- `skippey_main` — durable long-term memories.

The intended lifecycle is:

```text
Conversation
     ↓
Memory extraction
     ↓
Temporary memory
     ↓
Periodic processing
     ↓
Useful / durable memories
     ↓
Long-term memory
```

The important design choice is that the conversation itself is not automatically promoted to long-term memory. Temporary memory acts as a staging area.

The planned maintenance process is to process temporary memories periodically and promote useful information to long-term memory.

---

## 7. Memory manager

Another important change was separating conversation processing from graph construction.

Instead of sending every complete conversation directly into memory, a local Qwen memory manager analyzes the current message and produces two lists:

```json
{
  "remember": [],
  "recall": []
}
```

### Remember

The manager extracts distinct facts explicitly expressed by the current message and converts them into self-contained memories.

### Recall

The manager identifies information that the current message needs from previous memory and produces concise search queries.

Recent conversation context is supplied only to resolve references such as `it`, `that`, or `they`. It should not become memory merely because it appears in the context window.

This gives the system a pipeline closer to:

```text
Current message + small recent context
              ↓
        Qwen memory manager
              ↓
       ┌──────┴──────┐
       ▼             ▼
   remember[]      recall[]
       │             │
       ▼             ▼
    Graphiti       Graphiti
       │             │
       └──────┬──────┘
              ▼
            Neo4j
```

Graphiti remains responsible for entities and relationships rather than the memory manager inventing graph structure itself.

---

## 8. Entity handling experiments

The system experimented with explicitly creating a persistent `Chris` entity so that memories describing the user could connect to the same user node.

This exposed an important distinction between:

- having an entity in Neo4j;
- Graphiti's entity resolution actually selecting that entity when processing a new episode.

The experiments showed that merely pre-creating a node does not guarantee that every Graphiti episode will attach its extracted entity to that exact node. Entity resolution therefore remains an area that needs deliberate handling.

Another lesson was that `Chris` should not be recreated with a fresh UUID every time the program starts.

---

## 9. Context handling refinement

Early experiments supplied too much previous conversation context and sometimes caused the manager to treat context as new memory.

The prompt was refined so that:

- the current message is the source of new memories;
- recent context exists primarily for reference resolution;
- facts from context are not copied unless the current message requires them;
- recall is generated only when information is genuinely missing from the current message/context.

This reduced unnecessary memory creation and made the manager's job more focused.

---

## 10. Dockerization

The project was then moved toward a self-contained Docker deployment.

The target architecture became:

```text
Docker Compose
│
├── Skippey
│   ├── Python
│   ├── Graphiti
│   ├── BGE embedding
│   └── BGE reranking
│
├── Neo4j
│   └── persistent Docker volume
│
└── Ollama
    └── Qwen3
```

### Why Docker

Docker isolates the runtime and makes the entire stack reproducible on another machine.

The application no longer needs a host Python virtual environment for its container runtime.

The source code can be mounted into the container during development, while Python dependencies remain inside the container.

### Persistent storage

Neo4j's existing data was preserved by reusing its existing Docker volumes rather than creating a new empty database.

The Ollama model store is also represented as a persistent Docker volume.

BGE model downloads are cached in a Docker volume so the models do not need to be downloaded on every container creation.

---

## 11. Current architecture

At the current stage, the infrastructure is:

```text
                         ┌──────────────────────┐
                         │      Skippey         │
                         │                      │
User ──────────────────► │  Memory Manager      │
                         │       Qwen3          │
                         │          │           │
                         │    ┌─────┴─────┐     │
                         │    ▼           ▼     │
                         │ remember     recall  │
                         │    │           │     │
                         └────┼───────────┼─────┘
                              │           │
                              ▼           ▼
                         ┌───────────────────┐
                         │      Graphiti     │
                         │  BGE + reranking  │
                         └─────────┬─────────┘
                                   │
                                   ▼
                         ┌───────────────────┐
                         │       Neo4j        │
                         │                   │
                         │ TEMP + LONG TERM │
                         └───────────────────┘

                  Qwen3 inference runs through Ollama
```

---

## 12. What remains to be built

The current architecture is not the final system. Planned work includes:

- completing the temporary-to-long-term memory promotion process;
- improving entity resolution so the persistent user entity is reliably reused;
- benchmarking each stage of the memory pipeline;
- reducing unnecessary LLM calls;
- optimizing embedding and reranking latency;
- integrating the memory system cleanly into the main Skippey assistant;
- eventually evaluating larger local models when suitable hardware is available;
- exploring whether the model itself should evolve over time versus keeping learning in the memory/knowledge layer.

The distinction between **model evolution** and **memory evolution** is intentional: persistent knowledge should initially evolve without continuously modifying the model weights.
