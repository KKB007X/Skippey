import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

from graphiti_core import Graphiti
from graphiti_core.cross_encoder.bge_reranker_client import BGERerankerClient
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.nodes import EpisodeType

load_dotenv()


class BGEEmbedder(EmbedderClient):
    """Local BGE-large embedder used by Graphiti."""

    def __init__(self, model_name: str = "BAAI/bge-large-en-v1.5"):
        print(f"Loading embedding model: {model_name}")
        self.model = SentenceTransformer(model_name)
        print("Embedding model loaded.")

    async def create(self, input_data):
        if isinstance(input_data, list):
            if len(input_data) != 1:
                raise ValueError(f"Expected one input, got {len(input_data)}")
            input_data = input_data[0]

        embedding = self.model.encode(input_data, convert_to_numpy=True)
        return [float(value) for value in embedding]

    async def create_batch(self, input_data_list):
        embeddings = self.model.encode(input_data_list, convert_to_numpy=True)
        return [[float(value) for value in embedding] for embedding in embeddings]


NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

if not NEO4J_PASSWORD:
    raise RuntimeError("NEO4J_PASSWORD is not set")


llm_config = LLMConfig(
    api_key=os.getenv("GRAPHITI_LLM_API_KEY", "ollama"),
    model=os.getenv("GRAPHITI_LLM_MODEL", "qwen3:4b-instruct"),
    small_model=os.getenv("GRAPHITI_LLM_SMALL_MODEL", "qwen3:4b-instruct"),
    base_url=os.getenv("GRAPHITI_LLM_BASE_URL", "http://localhost:11434/v1"),
)

llm_client = OpenAIGenericClient(config=llm_config)
embedder = BGEEmbedder()
cross_encoder = BGERerankerClient()

graphiti = Graphiti(
    NEO4J_URI,
    NEO4J_USER,
    NEO4J_PASSWORD,
    llm_client=llm_client,
    embedder=embedder,
    cross_encoder=cross_encoder,
)

_initialized = False


async def initialize():
    """Initialize Graphiti indices. Safe to call more than once."""
    global _initialized
    if not _initialized:
        await graphiti.build_indices_and_constraints()
        _initialized = True


async def recall(query: str, limit: int = 10) -> list[str]:
    """Retrieve multiple relevant facts for one natural-language query."""
    await initialize()

    results = await graphiti.search(query=query)
    facts = []

    for result in results[:limit]:
        fact = getattr(result, "fact", None)
        if fact:
            facts.append(fact)

    return facts


async def remember(message: str, *, group_id: str = "skippey"):
    """Store a conversation message as a Graphiti episode."""
    await initialize()

    return await graphiti.add_episode(
        name=f"conversation_{datetime.now(timezone.utc).isoformat()}",
        episode_body=message,
        source=EpisodeType.message,
        source_description="Skippey conversation",
        reference_time=datetime.now(timezone.utc),
        group_id=group_id,
    )


async def process_message(message: str, *, group_id: str = "skippey") -> list[str]:
    """Recall relevant long-term memory, then store the current message."""
    memories = await recall(message)
    await remember(message, group_id=group_id)
    return memories


async def close():
    await graphiti.close()
    

if __name__ == "__main__":
    import asyncio

    async def demo():
        memories = await process_message("Kamalesh said that pizza is his favorite food.")
        print("Recalled memories:")
        for memory in memories:
            print(f"- {memory}")
        await close()

    asyncio.run(demo())
