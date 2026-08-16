# Skippey

A local-first personal AI assistant with long-term memory backed by Graphiti and Neo4j.

## Current architecture

```text
User message
     |
     +----> recall() ----> Graphiti / Neo4j ----> relevant facts
     |
     +----> remember() --> Graphiti / Neo4j
     |
     v
 Main LLM ----> response
```

### Memory

- **Graphiti** manages episodic/knowledge-graph memory.
- **Neo4j** stores the graph locally.
- **BGE-large-en-v1.5** provides local 1024-dimensional embeddings.
- **BGE reranker v2-m3** provides local cross-encoder reranking.
- **Qwen3 4B Instruct** runs locally through Ollama as Graphiti's LLM.
- Each message is recalled against existing memory and then stored as a new episode.
- Explicit forgetting is planned as a tool exposed to the main assistant.
- Importance/usage-based memory decay is planned for the maintenance loop.

## Requirements

- Python 3.12+
- Neo4j 5.x
- Ollama
- Enough local storage/RAM for the embedding and reranker models

The models are downloaded to the local Hugging Face/Ollama caches and are not stored in this repository.

## Setup

Create a virtual environment and install the dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Start Neo4j and Ollama locally, then pull the Graphiti LLM:

```bash
ollama pull qwen3:4b-instruct
```

Create `.env` from `.env.example` and fill in the local Neo4j password and, if needed, the main LLM credentials.

## Configuration

`memory.py` uses environment variables for credentials and local service addresses. Secrets are intentionally excluded from Git.

The main assistant currently uses an NVIDIA-hosted LLM for the conversation response, while Graphiti uses the local Qwen3 model for memory extraction and retrieval-related reasoning.

## Project status

This repository is an active prototype. The memory pipeline is being developed incrementally, with explicit forgetting and adaptive memory decay planned as the next stages.
