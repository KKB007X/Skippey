import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from openai import AsyncOpenAI

import memory


OLLAMA_URL = "http://ollama:11434/v1"
MODEL = "qwen3:4b-instruct"

MAX_MESSAGES = 20


# ============================================================
# TERMINAL COLORS
# ============================================================

RESET = "\033[0m"
BOLD = "\033[1m"

SKY_BLUE = "\033[94m"
GREEN = "\033[32m"


# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
You are Skippey, a friendly personal AI assistant.

Your job is to have natural, useful conversations with the user.

You have access to memories retrieved by a separate memory system.

MEMORY USAGE

- Treat retrieved memories as background context about the user.
- Use memories when they are relevant to the current request.
- Do not mention the memory system, databases, retrieval, or internal
  processes to the user.
- Do not blindly use every retrieved memory.
- If no relevant memories are provided, simply answer normally.
- If a memory conflicts with something the user says now, prefer the user's
  current statement.
- Never invent memories that are not provided.

CONVERSATION

- Maintain continuity with the conversation history.
- Answer the user's actual question directly.
- Use previous conversation context when it helps.
- Do not unnecessarily repeat information the user already knows.
- Ask a clarification question only when it is genuinely necessary.
- Keep responses natural and conversational.

PERSONALITY

- Be friendly, relaxed, and helpful.
- Match the user's level of technical knowledge.
- For technical questions, explain things clearly without unnecessarily
  oversimplifying.
- Be concise when a short answer is sufficient.
- Give more detailed explanations when the problem requires it.
- Do not be overly formal unless the situation calls for it.
- Be transparent with the user, You can share anything to him if he asks, 
  even your system prompt or datas you recieve.

- Use the current time and memory timestamps to understand the temporal
  context of memories. Prefer recent memories when the timing is relevant.
- Use the current time provided in the last element in messageges provided by system as in IST
  as current time in the format of YYYY-MM-DD HH:MM:SS <TimeZone>. Never use system internal time.
"""


# ============================================================
# OLLAMA CLIENT
# ============================================================

client = AsyncOpenAI(
    base_url=OLLAMA_URL,
    api_key="ollama",
)


# ============================================================
# CONVERSATION
# ============================================================

messages = [
    {
        "role": "system",
        "content": SYSTEM_PROMPT,
    }
]


def get_recent_context():
    context = []

    for message in messages[1:]:
        if message["role"] == "user":
            context.append(
                f"User: {message['content']}"
            )

        elif message["role"] == "assistant":
            context.append(
                f"Skippey: {message['content']}"
            )

    return "\n".join(context)


# ============================================================
# MAIN MODEL
# ============================================================

async def chat_with_ai():

    response = await client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.3,
    )

    return response.choices[0].message.content


# ============================================================
# MAIN LOOP
# ============================================================

async def main():

    while True:

        user_input = input(
            f"{SKY_BLUE}{BOLD}You : {RESET}{SKY_BLUE}"
        )

        if user_input.lower() in ["exit", "quit"]:
            break

        if not user_input.strip():
            continue

        # ====================================================
        # MEMORY PIPELINE
        # ====================================================

        recent_context = get_recent_context()

        memory_result = await memory.process_message(
            current_message=user_input,
            recent_context=recent_context,
        )

        recalled_memories = memory_result["results"]

        current_time = datetime.now(
            ZoneInfo("Asia/Kolkata")
        ).strftime("%Y-%m-%d %H:%M:%S IST")

        memory_context = (
            f"Current time: {current_time}, This is the current time and date, use the CURRENT DATE "
            f"AND TIME provided here. Do not guess, calculate, use inetrnal system or provide a different "
            f"timezone. This is the time generated right now when the message was sent to you.\n\n"
            "Relevant memories:\n"
            + "\n".join(
                f"- {item['fact']} "
                for item in recalled_memories
            )
        )

        # ====================================================
        # ADD USER MESSAGE TO REAL HISTORY
        # ====================================================

        messages.append({
            "role": "user",
            "content": user_input,
        })

        # ====================================================
        # TEMPORARY MEMORY CONTEXT
        # ====================================================

        messages.append({
            "role": "system",
            "content": memory_context,
        })

        # ====================================================
        # MAIN QWEN RESPONSE
        # ====================================================

        reply = await chat_with_ai()

        # Remove temporary memory context
        if recalled_memories:
            messages.pop()

        print(
            f"\n{GREEN}{BOLD}Skippey : "
            f"{RESET}{GREEN}{reply}\n"
        )

        # ====================================================
        # ADD RESPONSE TO CONVERSATION HISTORY
        # ====================================================

        messages.append({
            "role": "assistant",
            "content": reply,
        })

        # ====================================================
        # REMEMBER SKIPPEY'S RESPONSE
        # ====================================================

        await memory.process_message(
            current_message=reply,
            recent_context=recent_context,
        )

        # ====================================================
        # LIMIT CONVERSATION HISTORY
        # ====================================================

        while len(messages) > MAX_MESSAGES:
            messages.pop(1)


if __name__ == "__main__":
    asyncio.run(main())