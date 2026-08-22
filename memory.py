import asyncio
import json
from datetime import datetime, timezone
import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from openai import AsyncOpenAI
from sentence_transformers import SentenceTransformer

from graphiti_core import Graphiti
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.nodes import EpisodeType, EntityNode
from graphiti_core.cross_encoder.bge_reranker_client import BGERerankerClient
from graphiti_core.search.search_config import (
    SearchConfig,
    EdgeSearchConfig,
    EdgeSearchMethod,
    EdgeReranker,
    NodeSearchConfig,
    NodeSearchMethod,
    NodeReranker,
)

search_config = SearchConfig(
    edge_config=EdgeSearchConfig(
        search_methods=[EdgeSearchMethod.cosine_similarity],
        reranker=EdgeReranker.rrf,
        sim_min_score=0.5,
    ),
    node_config=NodeSearchConfig(
        search_methods=[NodeSearchMethod.cosine_similarity],
        reranker=NodeReranker.rrf,
        sim_min_score=0.5,
    ),
    limit=10,
)

from uuid import uuid4

from time import perf_counter

import psycopg

POSTGRES_DSN = os.getenv(
    "POSTGRES_DSN",
    "postgresql://skippey:skippey123@postgres:5432/skippey",
)


def timed(label):
    # start = perf_counter()
    pass
    def stop():
        # elapsed = perf_counter() - start
        # print(f"[TIME] {label}: {elapsed:.3f}s")
        # return elapsed
        pass
    return stop


# ============================================================
# Neo4j configuration
# ============================================================

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

if not NEO4J_PASSWORD:
    raise RuntimeError("NEO4J_PASSWORD is not set")

# ============================================================
# Ollama configuration
# ============================================================



OLLAMA_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://localhost:11434/v1"
)

MODEL = "qwen3:4b-instruct"

# ============================================================
# Local BGE embedding model
# ============================================================

class BGEEmbedder(EmbedderClient):

    def __init__(self):
        print("Loading BGE...")
        self.model = SentenceTransformer(
            "BAAI/bge-large-en-v1.5"
        )
        print("BGE loaded!")

    async def create(self, input_data):
        """
        Create one embedding.

        Graphiti may provide either:
            "some text"
        or:
            ["some text"]
        """

        if isinstance(input_data, list):
            if len(input_data) != 1:
                raise ValueError(
                    f"BGEEmbedder.create() expected one input, "
                    f"got {len(input_data)}"
                )

            input_data = input_data[0]

        _stop = timed("BGE create")
        embedding = self.model.encode(
            input_data,
            convert_to_numpy=True,
        )
        _stop()

        return [float(x) for x in embedding]

    async def create_batch(self, input_data_list):
        """
        Create embeddings for multiple texts.
        """

        _stop = timed("BGE create_batch")
        embeddings = self.model.encode(
            input_data_list,
            convert_to_numpy=True,
        )
        _stop()

        return [
            [float(x) for x in embedding]
            for embedding in embeddings
        ]


# ============================================================
# Graphiti LLM
# ============================================================

cross_encoder = BGERerankerClient()

llm_config = LLMConfig(
    api_key="ollama",
    model=MODEL,
    small_model=MODEL,
    base_url=OLLAMA_URL,
)

llm_client = OpenAIGenericClient(
    config=llm_config
)


# ============================================================
# Embedding model
# ============================================================

embedder = BGEEmbedder()


# ============================================================
# Graphiti
# ============================================================

graphiti = Graphiti(
    NEO4J_URI,
    NEO4J_USER,
    NEO4J_PASSWORD,
    llm_client=llm_client,
    embedder=embedder,
    cross_encoder=cross_encoder,
)


# ============================================================
# Qwen manager
# ============================================================

manager = AsyncOpenAI(
    base_url=OLLAMA_URL,
    api_key="ollama",
)


# ============================================================
# Memory manager prompt
# ============================================================

MANAGER_PROMPT = """
You are Skippey's memory manager.

Analyze the CURRENT MESSAGE. RECENT CONVERSATION is provided only
to resolve references and understand context.

Return only JSON:

{
    "remember": [],
    "recall": []
}

REMEMBER:

Extract only meaningful, potentially useful facts from the CURRENT MESSAGE.

- Prefer facts about the user, their preferences, goals, projects,
  relationships, environment, or persistent circumstances.
- Do not store conversational filler, greetings, acknowledgements,
  questions, jokes, or generic statements.
- Do not store temporary runtime information such as the current time,
  current date, model output, system state, or tool results.
- Do not store statements about Skippey's own behavior, capabilities,
  responses, or internal processes.
- Do not store information merely because it appears factual.
  It should have potential value for future conversations.
- Do not create memories from the assistant's response unless it contains
  meaningful information about the user.

RECALL:

Determine whether previous memory could help answer or understand the CURRENT MESSAGE.

- Recall memories when they are relevant or potentially useful to the
  CURRENT MESSAGE.
- Prefer memories that provide context, continuity, or information about
  the user's previous statements.
- When the CURRENT MESSAGE is ambiguous or refers to something from the
  user's past, prefer recalling rather than omitting potentially relevant
  memories.
- Do not recall memories for casual conversation, greetings, jokes,
  acknowledgements, or requests that can be answered without memory.
- Do not recall unrelated memories or large amounts of weakly related
  information.
- Do not recall temporary conversational details unless they are relevant
  to the CURRENT MESSAGE.
- If memory could help, you MUST generate at least one specific semantic
  search query in the "recall" array.
- The query should describe the information being searched for, not simply
  repeat the user's wording.
- If the message does not need memory, return an empty "recall" array.

Graphiti handles entities and relationships.

Return only valid JSON.
"""


# ============================================================
# Analyze conversation
# ============================================================

async def analyze_message(
    current_message: str,
    recent_context: str = "",
):
    """
    Analyze a message using recent conversation context.

    Returns:

    {
        "remember": [...],
        "recall": [...]
    }
    """

    if not current_message or not current_message.strip():
        return {
            "remember": [],
            "recall": [],
        }

    context = recent_context.strip()

    if not context:
        context = "(No previous conversation context.)"

    prompt = f"""
RECENT CONVERSATION:
--------------------
{context}

CURRENT MESSAGE:
----------------
{current_message}
"""

    _stop = timed("Qwen manager")
    response = await manager.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": MANAGER_PROMPT,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0,
    )
    _stop()

    text = response.choices[0].message.content.strip()

    # --------------------------------------------------------
    # Remove markdown JSON fences if Qwen adds them
    # --------------------------------------------------------

    if text.startswith("```"):
        text = text.replace("```json", "")
        text = text.replace("```", "")
        text = text.strip()

    try:
        result = json.loads(text)

    except json.JSONDecodeError as error:
        print("\nQwen returned invalid JSON:")
        print(text)

        raise ValueError(
            "Memory manager returned invalid JSON."
        ) from error

    # --------------------------------------------------------
    # Validate output
    # --------------------------------------------------------

    remember_list = result.get("remember", [])
    recall_list = result.get("recall", [])

    if not isinstance(remember_list, list):
        remember_list = []

    if not isinstance(recall_list, list):
        recall_list = []

    remember_list = [
        item.strip()
        for item in remember_list
        if isinstance(item, str) and item.strip()
    ]

    recall_list = [
        item.strip()
        for item in recall_list
        if isinstance(item, str) and item.strip()
    ]

    return {
        "remember": remember_list,
        "recall": recall_list,
    }


# ============================================================
# Store ONE memory in temporary memory
# ============================================================

async def remember(content: str):
    if not content or not content.strip():
        return

    timestamp = datetime.now(timezone.utc)

    _stop = timed("BGE temporary memory")

    embedding = await embedder.create(content)

    _stop()

    _stop = timed("PostgreSQL remember")

    async with await psycopg.AsyncConnection.connect(POSTGRES_DSN) as conn:
        await conn.execute(
            """
            INSERT INTO temporary_memories
                (memory, vector, created_at)
            VALUES
                (%s, %s::vector, %s)
            """,
            (content, embedding, timestamp),
        )
        await conn.commit()

    _stop()


# ============================================================
# Recall ONE query
# ============================================================

async def recall(
    query: str,
    similarity_threshold: float = 0.50,
    max_results: int = 10,
):
    if not query or not query.strip():
        return []

    results = []

    # -------------------------
    # Temporary memory
    # -------------------------

    query_embedding = await embedder.create(query)

    _stop = timed("PostgreSQL recall")

    async with await psycopg.AsyncConnection.connect(POSTGRES_DSN) as conn:
        rows = await conn.execute(
            """
            SELECT
                memory,
                created_at,
                1 - (vector <=> %s::vector) AS similarity
            FROM temporary_memories
            WHERE 1 - (vector <=> %s::vector) >= %s
            ORDER BY vector <=> %s::vector
            LIMIT %s
            """,
            (
                query_embedding,
                query_embedding,
                similarity_threshold,
                query_embedding,
                max_results,
            ),
        )

        temp_rows = await rows.fetchall()

    _stop()

    for memory, created_at, similarity in temp_rows:
        results.append({
            "fact": (
                f"{memory} "
                f"[temporary, {created_at.astimezone().strftime('%Y-%m-%d %H:%M')}]"
            ),
            "valid_at": created_at,
            "invalid_at": None,
        })

    # -------------------------
    # Long-term memory
    # -------------------------

    _stop = timed("Graphiti recall")

    graph_results = await graphiti.search_(
        query=query,
        config=search_config,
    )
    edges = dict(graph_results)["edges"]

    _stop()

    for result in edges:
        results.append({
            "fact": (
                f"{result.fact} "
                f"[long-term, {result.valid_at.strftime('%Y-%m-%d %H:%M')}]"
            ),
            "valid_at": result.valid_at,
            "invalid_at": result.invalid_at,
        })

    return results

# ============================================================
# Process a message
# ============================================================

async def process_message(
    current_message: str,
    recent_context: str = "",
):
    """
    Main live memory operation.

    1. Analyze current message using recent context.
    2. Store atomic memories in TEMP.
    3. Run recall queries against TEMP + MAIN.
    4. Return all recalled facts.
    """

    _stop_total = timed("process_message TOTAL")
    analysis = await analyze_message(
        current_message=current_message,
        recent_context=recent_context,
    )

    memories = analysis["remember"]
    queries = analysis["recall"]

    # --------------------------------------------------------
    # Store memories
    # --------------------------------------------------------

    for memory in memories:
        await remember(memory)

    # --------------------------------------------------------
    # Recall previous memories
    # --------------------------------------------------------

    recalled = []

    for query in queries:

        results = await recall(query)

        for result in results:

            recalled.append({
                "query": query,
                "fact": result["fact"],
                "valid_at": result["valid_at"],
                "invalid_at": result["invalid_at"],
            })

    result = {
        "remember": memories,
        "recall": queries,
        "results": recalled,
    }
    _stop_total()
    return result


# ============================================================
# Clear Neo4j database
# ============================================================

async def clear_database():
    """
    WARNING:
    Deletes ALL nodes and relationships in the Neo4j database.

    Do not call this unless the database contains only Skippey data.
    """

    driver = graphiti.driver

    async with driver.session() as session:
        await session.run(
            "MATCH (n) DETACH DELETE n"
        )

    print("Neo4j database cleared.")


# ============================================================
# Test
# ============================================================

async def main():

    print("\nBuilding Neo4j indices...")

    await graphiti.build_indices_and_constraints()

    print("Graphiti initialized!")

    # ========================================================
    # Test conversation context
    # ========================================================

    test_conversation = [
        {
            "context": "",
            "message": (
                "I've been working on a personal AI assistant called Skippey. "
                "I'm building its memory system with Neo4j and Graphiti."
            ),
        },
        {
            "context": (
                "User: I've been working on a personal AI assistant called Skippey. "
                "I'm building its memory system with Neo4j and Graphiti."
            ),
            "message": (
                "I'm running Qwen3 locally through Ollama because I want the "
                "assistant to work without relying on the internet."
            ),
        },
        {
            "context": (
                "User: I've been working on a personal AI assistant called Skippey. "
                "I'm building its memory system with Neo4j and Graphiti.\n"
                "User: I'm running Qwen3 locally through Ollama because I want "
                "the assistant to work without relying on the internet."
            ),
            "message": (
                "I also want its memories to be split into temporary and "
                "long-term storage."
            ),
        },
        {
            "context": (
                "User: I've been working on a personal AI assistant called Skippey. "
                "I'm building its memory system with Neo4j and Graphiti.\n"
                "User: I'm running Qwen3 locally through Ollama because I want "
                "the assistant to work without relying on the internet.\n"
                "User: I also want its memories to be split into temporary and "
                "long-term storage."
            ),
            "message": (
                "What database am I using for its memory system?"
            ),
        },
        {
            "context": (
                "User: I'm running Qwen3 locally through Ollama because I want "
                "the assistant to work without relying on the internet.\n"
                "User: I also want its memories to be split into temporary and "
                "long-term storage."
            ),
            "message": (
                "What model am I using for the assistant?"
            ),
        },
        {
            "context": (
                "User: I also want its memories to be split into temporary and "
                "long-term storage."
            ),
            "message": (
                "I think the temporary memories should be processed once a day "
                "and promoted to long-term memory when they're useful. and what model am i using rn?"
            ),
        },
    ]
    for i, test in enumerate(test_conversation, 1):

        print("\n" + "=" * 60)
        print(f"TURN {i}")
        print("=" * 60)

        result = await process_message(
            current_message=test["message"],
            recent_context=test["context"],
        )

        print("\nREMEMBER:")
        for item in result["remember"]:
            print("  -", item)

        print("\nRECALL:")
        for item in result["recall"]:
            print("  -", item)

        print("\nRECALLED:")
        for item in result["results"]:
            print("  -", item["fact"])

    # --------------------------------------------------------
    # Close
    # --------------------------------------------------------

    await graphiti.close()

    print("\nDone.")


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    asyncio.run(main())