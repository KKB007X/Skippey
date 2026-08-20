# Skippey — Project History

> This document records the engineering evolution of Skippey: what the system originally was, why the architecture changed, the problems that drove each change, and the direction of the project.
>
> Skippey is more than a memory backend. It is a personal AI assistant/chatbot whose memory system has progressively become a major part of the architecture. The long-term goal is to make the assistant behave as much like a persistent, evolving personal assistant as practical, with memory, perception, web access, and other tools added over time.

---

# 1. Original Skippey — just a chatbot

The earliest version of Skippey was much simpler than the current system.

It was essentially:

```text
User
  ↓
Skippey
  ↓
NVIDIA API
  ↓
LLM response
```

At this stage there was:

- no persistent memory;
- no memory database;
- no memory retrieval;
- no memory-management tools;
- no knowledge graph;
- no local model.

The goal was initially just to get a functional chatbot running.

The first major limitation was obvious: the assistant could respond to a conversation, but it did not retain useful information between interactions.

This led to the first real architectural expansion: giving the chatbot a persistent memory system.

---

# 2. Generation 1 — PostgreSQL + pgvector

The next stage introduced PostgreSQL and pgvector, along with an embedding model downloaded through Hugging Face/Sentence Transformers.

The basic architecture became:

```text
User message
     ↓
Main LLM
     ↓
Memory operations
     ↓
Embedding
     ↓
PostgreSQL + pgvector
```

The memory database contained information such as:

- memory text;
- embeddings;
- importance;
- creation time;
- last access time;
- access/reinforcement information.

The initial embedding model was:

```text
all-MiniLM-L6-v2
```

with 384-dimensional embeddings.

An HNSW vector index using cosine similarity was used for semantic retrieval.

## 2.1 Memory tools

The main model was given tools for managing its own memory. The early interface included operations such as:

```text
remember()
recall()
update()/modify()
forget()
```

The intention was for the LLM to decide when it needed to store, retrieve, change, or remove information.

Conceptually:

```text
User
 ↓
Main LLM
 ├── remember
 ├── recall
 ├── update / modify
 └── forget
       ↓
 PostgreSQL + pgvector
```

This was the first version where Skippey could actually retain information between separate calls.

---

# 3. The tool-calling reliability problem

The PostgreSQL system worked technically, but a new problem appeared: **the model had to reason correctly about when and how to use the memory tools.**

Small models were attractive because they were faster and cheaper, but their reasoning and tool-use reliability were not good enough for consistently managing memory.

Typical problems included:

- inconsistent decisions about when to store a memory;
- incorrect tool selection;
- unreliable update/forget decisions;
- failure to retrieve information when it was needed;
- unnecessary memory operations;
- inconsistent behavior between otherwise similar messages.

Larger models were better at reasoning and tool use, but introduced another problem:

```text
better reasoning
      ↕
slower + more expensive inference
```

This created an architectural bottleneck rather than simply a model-selection problem.

The important realization was:

> The main conversational model should not necessarily be responsible for every memory-management decision.

---

# 4. Separate memory-management pipeline

To solve the tool-use reliability problem, the architecture was redesigned so that memory management became a **separate pipeline**.

Instead of giving the main chatbot complete freedom to call memory tools, every user message was passed through a dedicated memory-management system first.

The architecture became:

```text
                       User message
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Memory Manager LLM  │
                 │                     │
                 │ Decide what memory  │
                 │ operations are      │
                 │ required            │
                 └──────────┬──────────┘
                            │
                 ┌──────────┴──────────┐
                 ▼                     ▼
            Operations              Retrieved data
                 │                     │
                 └──────────┬──────────┘
                            ▼
                    Main chatbot LLM
                            │
                            ▼
                         Response
```

The memory manager received each message and decided which operations should happen, such as:

```text
remember
update
forget
recall
```

The results of those operations, including retrieved memories, were then passed to the main model so that the main model could produce the final response.

This was an important architectural separation:

```text
Memory reasoning
        ≠
Conversation reasoning
```

The main model could focus on producing a good answer while a dedicated component handled persistent memory.

---

# 5. Why the separate manager still wasn't enough

The separate memory-management pipeline improved the architecture conceptually, but it still depended heavily on the reasoning quality of the model responsible for memory decisions.

It remained inconsistent in cases where the model had to determine:

- what is actually worth remembering;
- whether a fact already exists;
- whether something should be updated or forgotten;
- what information should be recalled;
- how to phrase an effective retrieval query.

This led to an important shift in thinking:

> The problem was not only how to search memories. The representation of memory itself needed to become richer.

That led to the investigation of **knowledge graphs**.

---

# 6. Generation 2 — Neo4j + Graphiti

The memory backend was moved from PostgreSQL/pgvector to **Neo4j + Graphiti**.

The motivation was to represent memory as a connected knowledge structure rather than a collection of independent vector records.

Graphiti provided:

- episode ingestion;
- entity extraction;
- relationship extraction;
- temporal information;
- semantic retrieval;
- embeddings;
- reranking;
- Neo4j graph persistence.

The architecture became:

```text
User message
     ↓
Memory manager
     ↓
Graphiti
     ↓
Entities + relationships + facts
     ↓
Neo4j
```

A fact such as:

```text
Chris uses Python for coding assessments.
```

could now conceptually participate in a graph such as:

```text
Chris ── prefers/uses ──► Python
                              │
                              ▼
                    coding assessments
```

This was a better fit for a personal assistant because people, projects, tools, preferences, models, and other concepts naturally form relationships.

---

# 7. Local LLM — Ollama + Qwen3

The project then moved toward fully local inference.

The hosted NVIDIA API was replaced in the memory pipeline with Ollama and Qwen3.

The current local model is:

```text
qwen3:4b-instruct
```

The architecture changed from:

```text
NVIDIA API → hosted model
```

to:

```text
Ollama → Qwen3 → local inference
```

This was driven by the desire for Skippey to operate without relying on the internet for its core assistant and memory functionality.

The trade-off is that local inference is constrained by available hardware, but it removes dependence on a remote API for the model itself.

---

# 8. Current memory-manager architecture

The current design intentionally returns to the useful part of the earlier separate memory-manager architecture, but with a much stronger backend and a local model.

The memory manager receives the user's message and determines the memory operations required.

Conceptually:

```text
                 User message
                      │
                      ▼
              ┌───────────────┐
              │   Qwen3       │
              │ Memory Manager│
              └───────┬───────┘
                      │
              memory operations
                      │
              ┌───────┴────────┐
              ▼                ▼
          Remember           Recall
              │                │
              ▼                ▼
          Graphiti          Graphiti
              │                │
              └───────┬────────┘
                      ▼
                    Neo4j
                      │
                      ▼
              Memory results
                      │
                      ▼
               Main chatbot
                      │
                      ▼
                   Response
```

The main chatbot can therefore focus on conversation while the memory manager focuses on memory policy.

## 8.1 No separate update operation

The earlier PostgreSQL system needed explicit operations such as `update()` or `modify()`.

The graph-based design changes this model.

Instead of requiring a dedicated update function for every change, a new episode/fact can be added and Graphiti's temporal graph machinery can represent the evolution of the information.

This simplifies the memory interface while giving the graph more information about how facts change over time.

The core memory actions are therefore becoming closer to:

```text
remember / add
recall
forget / invalidate when appropriate
```

rather than requiring a separate CRUD-style update path for every memory change.

---

# 9. Memory extraction and context separation

The memory manager was refined so that **recent conversation context is not automatically treated as new memory**.

Recent context exists primarily to make the current message understandable.

The intended distinction is:

```text
Recent context
    ↓
helps resolve references

Current message
    ↓
source of new memory

Graph memory
    ↓
used only when information is needed
```

For example, context can establish what `it`, `that`, or `they` refers to without forcing the manager to store the entire context again.

This was important because earlier tests showed that overly large context could cause the memory manager to over-store information that was merely present in the prompt.

---

# 10. Temporary memory — the next memory pipeline

The current memory architecture is being redesigned around a **temporary-memory-first** model.

Rather than immediately treating every extracted memory as permanent long-term knowledge, newly extracted memories will first receive a temporary-memory classification/tag.

Conceptually:

```text
User message
     ↓
Memory manager
     ↓
Temporary memory
     ↓
        ... normal operation ...
     ↓
Sleep / maintenance period
     ↓
Memory maintenance
     ├── discard / forget weak memories
     ├── consolidate duplicates
     ├── update temporal knowledge
     └── promote useful memories
              ↓
        Long-term memory
```

This is intended to behave more like human memory than a database where every stored sentence immediately becomes permanent.

## 10.1 Sleep / maintenance period

A planned maintenance process will run during a designated sleep period rather than forcing all memory consolidation to happen synchronously with every user message.

This allows the online conversation pipeline to stay focused on responsiveness while heavier memory processing happens asynchronously.

The maintenance stage is intended to perform the actual:

- forgetting;
- consolidation;
- short-term → long-term promotion;
- cleanup;
- temporal memory maintenance.

This is a major direction for the memory system and is still under development.

---

# 11. BGE embeddings and reranking

Graphiti is currently using local Sentence Transformers models rather than a remote embedding API.

The embedding model is:

```text
BAAI/bge-large-en-v1.5
```

A custom `BGEEmbedder` implements Graphiti's `EmbedderClient` interface with:

```text
create()
create_batch()
```

Graphiti is also configured with:

```text
BAAI/bge-reranker-v2-m3
```

through `BGERerankerClient`.

The retrieval path is therefore approximately:

```text
Query
  ↓
BGE embedding
  ↓
Graphiti / Neo4j retrieval
  ↓
BGE reranking
  ↓
Relevant memories
```

This introduces local computation cost, so retrieval and reranking latency are being measured before optimization decisions are made.

---

# 12. Graph/entity experiments

A canonical user entity was manually created in Neo4j so that facts could ideally converge on one persistent user node.

Testing exposed a subtle Graphiti problem: creating the entity manually does not automatically guarantee that Graphiti will resolve future mentions to that exact node.

Episodes could contain the correct user name while Graphiti still failed to connect a generated relation to the existing entity.

Warnings encountered during experiments included patterns such as:

```text
Source entity not found in nodes for edge relation: ...
Target entity not found in nodes for edge relation: ...
```

This demonstrated that:

```text
Entity exists in Neo4j
        ≠
Graphiti will always resolve a new mention to it
```

Entity resolution remains an active part of the design rather than something assumed to be solved merely by creating a node once.

---

# 13. Retrieval problems discovered during testing

Multi-turn tests revealed several useful failure modes:

- retrieval could return repeated facts;
- multiple episodes could encode effectively the same information;
- semantically related memories were sometimes returned instead of the most useful one;
- a recall query could retrieve information that was relevant to the broader project but irrelevant to the exact question;
- entity/relation extraction could fail even when the natural-language memory itself was retained.

These tests led to the principle that **memory quality has several independent dimensions**:

```text
Extraction quality
      +
Entity resolution
      +
Retrieval quality
      +
Deduplication
      +
Consolidation
      +
Temporal validity
```

A knowledge graph does not automatically solve all of them.

---

# 14. Performance optimization

Once the pipeline became functional, latency became the next engineering problem.

The system can involve several expensive stages:

```text
Qwen3 memory manager
       ↓
BGE embedding
       ↓
Graphiti processing
       ↓
Neo4j retrieval
       ↓
BGE reranking
       ↓
Main model response
```

The current approach is to measure first and optimize second.

Timers are kept outside the core memory functions during benchmarking so that the production functions themselves do not continually print timing information.

The benchmark loop is:

```text
Measure
  ↓
Find bottleneck
  ↓
Change one thing
  ↓
Measure again
  ↓
Keep/revert based on result
```

Actual latency numbers will be recorded in the performance documentation once representative measurements are collected.

---

# 15. Docker — fully self-contained deployment

The current Skippey environment is being moved into a self-contained Docker Compose stack.

The target architecture is:

```text
Docker Compose
│
├── Skippey
│   ├── Python runtime
│   ├── memory system
│   ├── Graphiti
│   ├── Sentence Transformers
│   └── BGE models/cache
│
├── Neo4j
│   └── persistent Docker volume
│
└── Ollama
    └── Qwen3 model
```

The purpose is not merely convenience. The goal is for the assistant's complete runtime to be reproducible and portable without depending on a host Python environment or separately installed database/model services.

Persistent Docker volumes are used so that:

- Neo4j data survives container recreation;
- downloaded Hugging Face models are cached;
- Ollama models survive container recreation.

The current project therefore aims to be **fully self-contained at the infrastructure level**.

---

# 16. Why the architecture has changed so many times

The project did not replace technologies arbitrarily. Each major change came from a limitation in the previous architecture:

```text
Simple chatbot
    │
    │ no persistent memory
    ▼
PostgreSQL + pgvector
    │
    │ LLM tool-use was inconsistent
    │ small models lacked reasoning
    │ large models were slow/expensive
    ▼
Separate memory-management pipeline
    │
    │ memory representation still too flat
    │ graph relationships became important
    ▼
Neo4j + Graphiti
    │
    │ hosted inference still undesirable
    ▼
Ollama + Qwen3
    │
    │ permanent storage for everything is not human-like
    ▼
Temporary memory + sleep/maintenance
    │
    └──► future consolidation + long-term memory
```

The architecture is therefore the result of repeatedly identifying the limiting part of the previous design and moving that responsibility to a more suitable component.

---

# 17. Current high-level architecture

```text
                         ┌───────────────────────┐
                         │        Skippey        │
                         │      Chatbot/AI       │
                         └───────────┬───────────┘
                                     │
                              User message
                                     │
                                     ▼
                         ┌───────────────────────┐
                         │  Memory Manager       │
                         │       Qwen3           │
                         │      via Ollama       │
                         └───────────┬───────────┘
                                     │
                          Decide memory operations
                                     │
                         ┌───────────┴───────────┐
                         ▼                       ▼
                    Remember                  Recall
                         │                       │
                         └───────────┬───────────┘
                                     ▼
                              Graphiti + BGE
                                     │
                                     ▼
                                  Neo4j
                                     │
                          temporary memory now
                                     │
                            sleep / maintenance
                                     │
                         ┌───────────┴───────────┐
                         ▼                       ▼
                      Forget                Promote
                                                 │
                                                 ▼
                                          Long-term memory
                                     │
                                     ▼
                              Main chatbot model
                                     │
                                     ▼
                                  Response
```

---

# 18. Long-term vision

The memory system is only one part of the larger assistant architecture.

The intended direction is to make Skippey progressively more capable and more human-like in how it interacts with information.

Planned capabilities include:

- computer vision;
- web searching;
- additional external/internal tools;
- richer memory consolidation;
- temporal reasoning;
- better entity resolution;
- autonomous maintenance during sleep periods;
- improved local models as hardware allows.

The long-term goal is not simply to build a chatbot with a database attached to it.

The goal is a persistent personal assistant whose **model, memory, tools, perception, and maintenance processes work together**.

---

# 19. Engineering principles

Several principles have emerged from the project:

### Memory should be explicit

Not every conversation message should become permanent memory.

### Context is not memory

Recent context exists primarily to make the current message understandable.

### Memory management should be separated from conversation generation

The model generating the final answer should not necessarily be responsible for every memory decision.

### Memory should evolve independently of model weights

The assistant should learn new facts by updating its persistent memory rather than requiring continuous model retraining.

### Graph structure is useful but not automatically correct

Neo4j stores the graph deterministically, but entity and relationship extraction can still be imperfect.

### Temporary memory should absorb uncertainty

New information can be stored first and evaluated later rather than forcing every decision to happen synchronously.

### Optimize from measurements

Latency changes should be justified with benchmarks rather than intuition.

### Failed approaches are part of the engineering story

The NVIDIA → PostgreSQL → separate memory manager → Graphiti/Neo4j → local Qwen → temporary/long-term progression is the result of iterative problem solving, not unnecessary rewrites.

---

# 20. Remaining work

## Memory

- complete the temporary-memory maintenance process;
- implement robust forgetting;
- implement short-term → long-term promotion;
- consolidate duplicate memories;
- improve temporal validity handling;
- improve canonical entity resolution;
- improve retrieval quality and diversity.

## Performance

- benchmark every major memory stage;
- reduce unnecessary LLM calls;
- evaluate embedding/reranking cost;
- optimize Graphiti/Neo4j retrieval;
- measure end-to-end response latency;
- record before/after results for meaningful optimizations.

## Assistant

- integrate the refined memory pipeline into the main chatbot;
- add computer vision;
- add web search;
- add additional tools;
- improve autonomous maintenance;
- eventually evaluate larger local models.

## Infrastructure

- finish validating the complete Docker stack;
- keep persistent model/database volumes;
- make the full runtime reproducible on another machine.
