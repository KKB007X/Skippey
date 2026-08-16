import asyncio
import os

import requests
from dotenv import load_dotenv

import memory

load_dotenv()

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
if not NVIDIA_API_KEY:
    raise RuntimeError("NVIDIA_API_KEY is not set")

API_URL = os.getenv(
    "MAIN_LLM_BASE_URL",
    "https://integrate.api.nvidia.com/v1/chat/completions",
)
MODEL = os.getenv("MAIN_LLM_MODEL", "meta/llama-3.1-8b-instruct")

SYSTEM_PROMPT = """
You are Skippey, a friendly personal AI assistant.

You have access to long-term memories retrieved by a separate memory system.
Use them as background context when relevant, but never mention the memory
system, retrieval, Graphiti, Neo4j, databases, or internal processes unless
the user explicitly asks how Skippey's memory works.

If a retrieved memory conflicts with the user's current message, prefer the
current message. Never invent memories that were not provided.

Maintain continuity with the conversation history and answer the user's
actual question directly. Match the user's level of technical knowledge and
avoid unnecessary formality.
"""

messages = [{"role": "system", "content": SYSTEM_PROMPT}]


def chat_with_ai() -> str:
    response = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {NVIDIA_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "messages": messages,
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


async def main():
    await memory.initialize()

    try:
        while True:
            user_input = input("You : ").strip()

            if user_input.lower() in {"exit", "quit"}:
                break
            if not user_input:
                continue

            recalled_memories = await memory.process_message(user_input)
            memory_context = "\n".join(
                f"- {fact}" for fact in recalled_memories
            ) or "None"

            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"User message:\n{user_input}\n\n"
                        f"Relevant long-term memory:\n{memory_context}"
                    ),
                }
            )

            reply = await asyncio.to_thread(chat_with_ai)
            print(f"\nSkippey : {reply}\n")

            messages.append({"role": "assistant", "content": reply})

            # Keep the system prompt plus a bounded recent conversation.
            max_messages = 20
            while len(messages) > max_messages:
                messages.pop(1)
    finally:
        await memory.close()


if __name__ == "__main__":
    asyncio.run(main())
