# Skippey — Project History

> This is the engineering history of Skippey, not just a description of the final architecture. It records major approaches we tried, why they were changed, problems encountered, and the design principles that survived the experiments.
>
> Details that were not measured or preserved exactly are explicitly described as design observations rather than numerical results.

---

# 1. The original idea

Skippey began as a personal AI assistant project whose main challenge was not simply generating responses, but **remembering useful information across conversations**.

The initial requirements gradually became:

- persistent memory across program restarts;
- semantic retrieval rather than exact keyword matching;
- memory reinforcement through later use;
- importance and recency as factors in persistence;
- a distinction between short-lived context and durable knowledge;
- eventually, relationships between people, projects, tools, preferences, and other entities;
- local LLM inference so core functionality would not depend on the internet;
- a portable runtime that could eventually be moved to a more powerful GPU laptop.

This caused the memory system to evolve from a small database helper into a separate subsystem of Skippey.

---

# 2. Generation 1 — NVIDIA API + PostgreSQL/pgvector

The first practical implementation used a hosted LLM through the **NVIDIA API**. The model used in the early experiments was:

```text
meta/llama-3.1-8b-instruct
```

For persistent memory, the first database design used **PostgreSQL with pgvector**.

The basic idea was straightforward:

```text
Conversation
    ↓
LLM
    ↓
Memory text
    ↓
Embedding
    ↓
PostgreSQL + pgvector
```

## 2.1 Initial memory table

The early database contained a `memories` table with fields including:

- `id`
- `memory`
- `embedding`
- `importance`
- `created_at`
- `last_accessed`
- `access_count`

The embedding model was initially:

```text
all-MiniLM-L6-v2
```

which produced 384-dimensional embeddings.

An HNSW index using cosine distance was created for vector retrieval.

## 2.2 Initial memory API

The early memory layer was deliberately simple. It exposed operations along the lines of:

```text
remember()
recall()
forget()
modify()
```

### `remember()`

Stored a memory and its embedding.

### `recall()`

Embedded a query and searched the vector index for semantically similar memories.

### `forget()`

Removed an unwanted memory.

### `modify()`

Allowed an existing memory to be updated rather than creating another independent record.

This established an important principle that remained throughout the project: **memory should be treated as data with a lifecycle, not merely as a chat transcript.**

## 2.3 Memory decay and reinforcement

One of the early design discussions was how memories should disappear.

A fixed TTL was considered too simplistic. Instead, the intended persistence model was based on a combination of:

- importance;
- recency;
- how often a memory was recalled or used.

The conceptual model became:

```text
important + frequently used
        → durable

unimportant + never used
        → candidate for decay
```

This idea later became the foundation for temporary/long-term memory promotion.

## 2.4 Problems with the first generation

Vector search solved semantic similarity, but the representation was fundamentally flat.

A record such as:

```text
"Chris uses Python for coding assessments."
```

was a useful searchable sentence, but the database did not naturally know that:

```text
Chris ──PREFERS_FOR──► Python
                         │
                    coding assessments
```

As Skippey evolved, entity relationships became increasingly important.

There were also practical issues around the LLM's reliability in deciding **what should actually be remembered**. Simply asking an LLM to remember an entire conversation risked storing too much irrelevant context.

This led to the next major idea: memory extraction should be separated from raw conversation storage.

---

# 3. Moving toward a memory manager

Instead of treating every message as a memory, the system began experimenting with an LLM-driven memory manager.

The manager's job was conceptually:

```text
Current message
      ↓
Memory manager
      ├── memories worth storing
      └── information that needs to be recalled
```

This eventually became the `remember[]` / `recall[]` design.

## 3.1 Breaking messages into memories

A single user message can contain multiple independent facts.

For example:

```text
I've been working on Skippey.
I'm using Neo4j for its memory system.
I prefer Python for coding OAs.
I use C++ for robotics projects.
```

should not necessarily become one giant memory.

The manager instead extracts self-contained units such as:

```text
- Chris is working on Skippey.
- Skippey's memory system uses Neo4j.
- Chris prefers Python for coding assessments.
- Chris uses C++ for robotics projects.
```

This was important because individual facts can then be independently retrieved, connected, deduplicated, and promoted.

## 3.2 Recall queries

The manager was also given the ability to generate explicit recall queries.

For example:

```text
Current message:
"What programming language do I prefer for OAs?"

Recall:
"What programming language does the user prefer for coding assessments?"
```

The memory layer then performs semantic retrieval against the graph/database.

This separated two different reasoning tasks:

1. **What information do I need?**
2. **Where is that information stored?**

The LLM handled the first; the memory backend handled the second.

---

# 4. Local LLM — Ollama + Qwen3

A major requirement appeared during development: **Skippey should not fundamentally rely on the internet.**

The hosted NVIDIA API was therefore replaced for the local memory pipeline by Ollama.

The architecture changed from:

```text
Skippey → NVIDIA API → Llama
```

to:

```text
Skippey → Ollama → Qwen3
```

The local model used in the current experiments is:

```text
qwen3:4b-instruct
```

## Why local inference?

- offline-capable core operation;
- no API request required for each memory operation;
- no dependency on a third-party LLM service for the assistant's memory;
- control over model/runtime selection;
- eventual ability to move the whole system to a local GPU machine.

The trade-off is that model quality and latency are constrained by local hardware.

The project therefore deliberately treats **memory as persistent external knowledge** rather than assuming the model itself needs to be retrained whenever Skippey learns something.

---

# 5. Generation 2 — Neo4j + Graphiti

The next major change was moving from PostgreSQL/pgvector to **Neo4j + Graphiti**.

The reason was not simply that graph databases were interesting. The memory representation had started to require explicit entities and relationships.

Graphiti provided the infrastructure for:

- episode ingestion;
- entity extraction;
- relationship extraction;
- temporal facts;
- embeddings;
- semantic search;
- reranking;
- graph persistence in Neo4j.

The architecture became:

```text
Conversation
      ↓
Memory manager
      ↓
Graphiti episode
      ↓
Entity / relationship extraction
      ↓
Neo4j graph
```

## 5.1 Why this was better than vector-only memory

Instead of storing only:

```text
"Chris uses Python for OAs"
```

the system could potentially represent:

```text
Chris ──PREFERS_FOR──► Python
                         │
                         ▼
                 coding assessments
```

and connect the same entities to other facts.

This is especially useful for a personal assistant because the same entity can participate in many memories:

```text
Chris
 ├── works on → Skippey
 ├── uses → Python
 ├── uses → C++
 └── works on → robotics projects
```

---

# 6. Local BGE embeddings

Graphiti was configured with a local Sentence Transformers embedding implementation rather than relying on a remote embedding API.

The embedding model became:

```text
BAAI/bge-large-en-v1.5
```

A custom `BGEEmbedder` implementing Graphiti's `EmbedderClient` interface was created.

It provides:

```text
create()
create_batch()
```

The implementation had to handle Graphiti's single-item calling convention as well as batch embedding.

The important interface behavior was tested explicitly because Graphiti can call the embedder with either a string or a one-element list.

---

# 7. BGE reranking

Graphiti was also configured with:

```text
BAAI/bge-reranker-v2-m3
```

through `BGERerankerClient`.

The retrieval pipeline therefore became approximately:

```text
Query
  ↓
Embedding
  ↓
Graph/vector candidate retrieval
  ↓
BGE reranking
  ↓
Relevant facts
```

This improved the sophistication of retrieval but introduced additional local inference cost.

That latency trade-off is now one of the things we are measuring rather than assuming is worth the cost.

---

# 8. Graphiti initialization and retrieval behavior

The memory layer eventually settled around functions such as:

```text
initialize()
remember()
recall()
process_message()
close()
```

## `initialize()`

Builds Graphiti indices and constraints once per process.

This was important because repeatedly rebuilding the graph indices for every operation would add unnecessary startup work.

## `remember()`

Creates a Graphiti episode from a memory/message and assigns it to a graph group.

## `recall()`

Runs a natural-language Graphiti search and extracts facts from the returned results.

The implementation explicitly retrieves **multiple** results rather than assuming the search returns only one useful memory.

## `process_message()`

Provides the high-level pipeline:

```text
message
  ↓
recall relevant existing memory
  ↓
remember current message
```

The larger memory-manager architecture later wraps this lower-level API so that only selected memories are written.

---

# 9. Temporary vs long-term memory

The system then evolved from one memory store toward two conceptual layers:

```text
skippey_temp
skippey_main
```

The intended lifecycle is:

```text
Conversation
     ↓
Extract useful facts
     ↓
Temporary memory
     ↓
Periodic maintenance
     ↓
Evaluate usefulness
     ↓
Promote durable facts
     ↓
Long-term memory
```

The important distinction is:

> **Temporary memory is not simply a second database. It is a staging area for information that has not yet earned long-term persistence.**

The planned maintenance behavior is to process temporary memories periodically, consolidate useful information, and promote durable knowledge into the long-term graph.

This builds on the original PostgreSQL-era idea of importance, recency, and reinforcement without requiring a fixed TTL for every memory.

---

# 10. Context is not memory

One of the more important prompt-design problems appeared during multi-turn testing.

Early versions supplied previous messages to the memory manager and sometimes caused the model to store facts merely because they appeared in recent context.

That was not the intended behavior.

The desired distinction became:

```text
Recent context
    = helps understand the current message

Current message
    = source of new memories

Long-term memory
    = retrieved only when needed
```

For example, if recent context says:

```text
Chris uses Qwen3 locally.
```

and the current message asks:

```text
What model am I using?
```

the context can make the current message self-contained enough to understand what it refers to. It should not automatically create another memory just because that sentence was supplied as context.

This significantly reduced unnecessary memory creation and made the manager less prone to overfitting its output to the test prompts.

---

# 11. Memory manager output format

The manager eventually used a structured output concept:

```json
{
  "remember": [],
  "recall": []
}
```

The intended behavior is:

### `remember`

Create concise, self-contained memories from facts expressed by the current message.

### `recall`

Create search queries only when the current message requires information that is not already available.

This produced an important optimization:

```text
No recall needed
      ↓
Do not search Graphiti
```

rather than performing a memory search for every message.

Likewise:

```text
No new fact
      ↓
Do not write a memory
```

This became the basis for reducing unnecessary graph operations.

---

# 12. Real multi-turn testing

A test conversation was used to evaluate whether memory persisted across calls and whether the manager could retrieve facts introduced several turns earlier.

Example progression:

```text
Turn 1:
Chris is building Skippey and its memory system.

Turn 2:
Qwen3 is running locally through Ollama.

Turn 3:
Memories should be split into temporary and long-term storage.

Turn 4:
Neo4j is used for the memory system.

Turn 5:
What model is being used?

Turn 6:
Temporary memories should be processed once a day.
```

The important result was that the system could retrieve older graph facts on later turns, proving that persistence was coming from Neo4j rather than from the LLM's conversational context.

The tests also exposed several problems with entity/relation extraction and duplicate retrieval, which became useful debugging cases rather than reasons to abandon the graph architecture.

---

# 13. Entity resolution — the `Chris` problem

A persistent `Chris` entity was manually created in Neo4j.

The goal was to have facts such as:

```text
Chris prefers Python for coding assessments.
Chris uses C++ for robotics projects.
Chris is building Skippey.
```

all connect to the same user node.

However, testing revealed an important Graphiti behavior:

> **Having a node called `Chris` in Neo4j does not guarantee that Graphiti will resolve a newly extracted `Chris` mention to that exact node.**

There were runs where Graphiti correctly extracted `Chris` in the episode text but failed to connect the relationship to the manually created entity.

The system also produced warnings such as:

```text
Source entity not found in nodes for edge relation: ...
Target entity not found in nodes for edge relation: ...
```

These experiments demonstrated that entity creation and entity resolution are separate problems.

The current direction is to preserve the canonical user entity and make resolution explicit/reliable rather than recreating the node every time the program starts.

---

# 14. Relation extraction problems

Graphiti occasionally generated relations such as:

```text
PREFERS_FOR
IS_USED_FOR
USES_FOR
HAS_PROCESSING_SCHEDULE
```

while failing to find one of the source/target entities required for the relation.

This did not necessarily mean the memory text was lost; the episode and extracted facts could still exist even when a particular graph edge failed.

The lesson was that **graph construction is probabilistic at the extraction layer**, even though Neo4j itself is deterministic once a node/relationship write has been specified.

This is one reason the project keeps the natural-language fact itself valuable instead of depending exclusively on a perfect graph edge.

---

# 15. Duplicate and noisy recall

During testing, some recall queries returned repeated or weakly related facts.

For example, a query about the assistant's model could return the same Qwen/Neo4j facts multiple times, sometimes because multiple episodes encoded essentially the same information.

This exposed several independent issues:

- multiple episodes can represent the same fact;
- semantic search may return several near-duplicates;
- reranking does not automatically mean deduplication;
- a memory search can return relevant-but-not-best facts;
- the caller needs to decide how many results are actually useful.

The project therefore began treating **retrieval quality and memory consolidation as separate optimization problems**.

---

# 16. Why Graphiti rather than manually constructing every relationship

At one point it was considered whether memories should be converted into graph entities and relationships entirely by application code.

The decision was to let Graphiti handle entity and relationship extraction while the application controls the higher-level memory policy.

In other words:

```text
Application
    ↓
Decides WHAT should be remembered/recalled

Graphiti
    ↓
Decides HOW the fact becomes graph entities/relations

Neo4j
    ↓
Persists the resulting graph
```

This keeps the memory policy separate from graph-construction mechanics.

---

# 17. Performance became an explicit engineering problem

After the functionality became reasonably stable, the next problem was latency.

The memory pipeline can involve several expensive operations:

```text
Qwen memory manager
       ↓
BGE embedding
       ↓
Graphiti processing
       ↓
Neo4j search
       ↓
BGE reranking
```

Instead of optimizing blindly, timing instrumentation was added to measure the actual cost of each stage.

The timers are intentionally kept outside the core memory functions during normal use. Benchmark code measures calls such as:

```text
recall()
remember()
process_message()
```

without making the production memory API print timing information.

The optimization process will therefore be measurement-driven:

```text
Measure
  ↓
Identify bottleneck
  ↓
Optimize bottleneck
  ↓
Measure again
```

Performance numbers will be added here only after actual benchmarks have been run.

---

# 18. Docker migration

Once the architecture had become dependent on several local services and ML models, reproducibility became a concern.

The target environment was moved toward Docker Compose:

```text
Docker Compose
│
├── Skippey
│   ├── Python
│   ├── Graphiti
│   ├── Sentence Transformers
│   ├── BGE
│   └── memory.py
│
├── Neo4j
│   └── persistent Docker volume
│
└── Ollama
    └── Qwen3
```

## 18.1 Why Docker

Docker provides:

- dependency isolation;
- reproducible Python environments;
- isolated Neo4j and Ollama services;
- persistent volumes for databases and model caches;
- easier migration to another machine.

A host Python virtual environment is therefore not required for the containerized runtime.

## 18.2 Migration problems

The migration exposed normal dependency/infrastructure issues:

- large PyTorch/CUDA packages made the first image build unnecessarily heavy;
- the dependency list initially missed packages used by the larger Skippey application, such as `fastcoref`;
- an existing Neo4j container conflicted with the Compose container name;
- Neo4j data had to be preserved while replacing the container;
- the Ollama image itself was several gigabytes and experienced network timeouts while downloading;
- host Ollama had to be stopped before Docker could bind port `11434`.

These were deployment issues rather than memory-architecture failures.

The important data-preservation decision was to reuse the existing Neo4j Docker volume while replacing the container, rather than deleting the database.

---

# 19. Current development workflow

During development, the memory system can be run directly in the Skippey container without requiring the full assistant application to start.

The current development command is conceptually:

```bash
docker compose run --rm skippey python memory.py
```

This is useful because the main `skippey.py` application and other components can remain unfinished while the memory subsystem is developed independently.

The planned development workflow is:

```text
Edit memory.py
      ↓
Syntax check
      ↓
Run memory.py in Docker
      ↓
Measure if necessary
      ↓
Inspect Neo4j / recall behavior
      ↓
Document meaningful architectural changes
```

When a new Python dependency is introduced, the Docker image needs to be rebuilt. Ordinary source-code changes do not conceptually require rebuilding once source bind-mounting is used for development.

---

# 20. Current architecture

The current design can be summarized as:

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

The historical progression is:

```text
NVIDIA API
    ↓
PostgreSQL + pgvector
    ↓
remember / recall / forget / modify
    ↓
memory decay + reinforcement concepts
    ↓
local Ollama + Qwen3
    ↓
Neo4j + Graphiti
    ↓
BGE-large embeddings + BGE reranking
    ↓
message → remember[] / recall[]
    ↓
temporary + long-term memory
    ↓
entity-resolution experiments
    ↓
benchmarking and latency optimization
    ↓
Dockerized deployment
```

---

# 21. Remaining work

The current system is intentionally not considered finished.

## Memory

- finish temporary-to-long-term promotion;
- consolidate duplicate memories;
- improve entity resolution for the canonical user entity;
- decide how much graph structure should be trusted versus natural-language facts;
- improve recall ranking and result diversity;
- determine whether reranking is worth its latency for every query.

## Performance

- benchmark Qwen manager latency;
- benchmark BGE embedding latency;
- benchmark Graphiti ingestion;
- benchmark Neo4j search;
- benchmark reranking;
- reduce unnecessary LLM calls;
- evaluate whether a smaller/faster embedding or reranker is sufficient;
- measure end-to-end latency before and after every meaningful optimization.

## Integration

- integrate the memory subsystem into the main Skippey assistant;
- ensure conversation context and memory remain separate;
- add the missing dependencies required by the complete application;
- eventually remove the host Python environment once Docker is fully validated.

## Hardware

The long-term plan is to run the complete local stack on a machine with a stronger GPU. A future RTX-class laptop should make it practical to evaluate larger local models while retaining the same Ollama-based architecture.

---

# 22. Engineering principles that emerged

Several principles survived the changes in architecture:

### 1. Memory should be explicit

Not every sentence in a conversation deserves permanent storage.

### 2. Context is not memory

Recent conversation context exists to interpret the current message; it should not automatically become persistent knowledge.

### 3. The model and memory are separate

Skippey should be able to learn new facts without retraining the LLM.

### 4. Retrieval and reasoning are different jobs

The LLM can determine what information is needed; the memory backend should retrieve it.

### 5. Graph structure is useful, but extraction is probabilistic

Neo4j provides deterministic persistence, while the natural-language entity/relation extraction performed before the write can fail or produce imperfect relations.

### 6. Optimize from measurements

Latency should be measured before changing architecture or replacing components.

### 7. Failed approaches are useful engineering information

The history of Skippey includes approaches that were replaced because they did not satisfy the emerging requirements. Those failures are part of the design rationale, not something to hide.
