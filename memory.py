import asyncio
from datetime import datetime

from sentence_transformers import SentenceTransformer

from graphiti_core import Graphiti
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.nodes import EpisodeType
from graphiti_core.cross_encoder.bge_reranker_client import BGERerankerClient

import time
# ============================================================
# Local BGE embedding model
# ============================================================

class BGEEmbedder(EmbedderClient):

    def __init__(self):
        print("Loading BGE...")
        self.model = SentenceTransformer("BAAI/bge-large-en-v1.5")
        print("BGE loaded!")

    async def create(self, input_data):
        """
        Create ONE embedding.

        Graphiti may call this with either:
            "some text"
        or:
            ["some text"]

        Graphiti expects this method to return:
            list[float]
        """

        if isinstance(input_data, list):
            if len(input_data) != 1:
                raise ValueError(
                    f"BGEEmbedder.create() expected one input, "
                    f"got {len(input_data)}"
                )
            input_data = input_data[0]

        embedding = self.model.encode(
            input_data,
            convert_to_numpy=True,
        )

        return [float(x) for x in embedding]

    async def create_batch(self, input_data_list):
        """
        Create embeddings for multiple texts.

        Returns:
            list[list[float]]
        """

        embeddings = self.model.encode(
            input_data_list,
            convert_to_numpy=True,
        )

        return [
            [float(x) for x in embedding]
            for embedding in embeddings
        ]


# ============================================================
# Neo4j configuration
# ============================================================

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "skippey123"


# ============================================================
# Cross encoder / reranker
# ============================================================

cross_encoder = BGERerankerClient()


# ============================================================
# Local Ollama LLM
# ============================================================

llm_config = LLMConfig(
    api_key="ollama",
    model="qwen3:4b-instruct",
    small_model="qwen3:4b-instruct",
    base_url="http://localhost:11434/v1",
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
# Test
# ============================================================

async def main():

    # --------------------------------------------------------
    # Verify our embedder
    # --------------------------------------------------------

    print("\nTesting embedder...")

    test = await embedder.create("test")

    print("TYPE:", type(test))
    print("LEN:", len(test))
    print("FIRST:", type(test[0]), test[0])
    print("NESTED:", isinstance(test[0], (list, tuple)))

    # This is the important Graphiti case:
    test_list = await embedder.create(["test"])

    print("\nTesting Graphiti-style single-item input...")
    print("TYPE:", type(test_list))
    print("LEN:", len(test_list))
    print("FIRST:", type(test_list[0]), test_list[0])
    print("NESTED:", isinstance(test_list[0], (list, tuple)))

    # --------------------------------------------------------
    # Build Graphiti indices
    # --------------------------------------------------------

    print("\nBuilding Neo4j indices...")

    await graphiti.build_indices_and_constraints()

    print("Graphiti initialized!")

    # --------------------------------------------------------
    # Add test memory
    # --------------------------------------------------------
    # print("Adding memory...")
    start = time.perf_counter()

    await graphiti.add_episode(
        name=f"skippey_memory_test_{datetime.now().isoformat()}",
        episode_body="Kamalesh said 'Pizza is my fav food'",
        source=EpisodeType.text,
        source_description="Skippey conversation",
        reference_time=datetime.now(),
    )
    # print("\nSearching memory...")

    # results = await graphiti.search(
    #     query="What is my favorite programming language?"
    # )

    # for result in results:
    #     print("FACT:", result.fact)
    #     print("VALID AT:", result.valid_at)
    #     print("INVALID AT:", result.invalid_at)
    #     print("---")

    print(f"Memory retrived in {time.perf_counter() - start:.2f}s")

        # --------------------------------------------------------
        # Close
        # --------------------------------------------------------

    await graphiti.close()

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())