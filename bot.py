"""PyMind AI: a text-only chat assistant backed by the Groq API."""

import os

from dotenv import load_dotenv
from groq import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    Groq,
    RateLimitError,
)

load_dotenv()

MODEL = "openai/gpt-oss-20b"
MAX_HISTORY_MESSAGES = 16  # Most recent 8 user/assistant pairs
SYSTEM_PROMPT = (
    "You are PyMind AI, a friendly, accurate text-only assistant. "
    "Reply in the user's language. If they write in Iraqi Arabic, "
    "you may respond in friendly Iraqi Arabic. Be clear and helpful. "
    "Admit uncertainty instead of inventing facts."
)


def build_messages(history: list[dict[str, str]], question: str) -> list[dict[str, str]]:
    """Include system instructions and recent chat turns in each API request."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history[-MAX_HISTORY_MESSAGES:],
        {"role": "user", "content": question},
    ]


def main() -> None:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key or api_key == "paste_your_groq_key_here":
        print("Missing GROQ_API_KEY. Create a .env file and paste your Groq key there.")
        return

    client = Groq(api_key=api_key, timeout=60.0)
    history: list[dict[str, str]] = []

    print("\n=== PyMind AI ===")
    print("Type a message in Arabic or English.")
    print("Commands: /clear (new chat), /exit (quit)\n")

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not question:
            continue
        if question.lower() in {"/exit", "exit"}:
            print("Goodbye!")
            break
        if question.lower() == "/clear":
            history.clear()
            print("Chat history cleared.\n")
            continue

        try:
            result = client.chat.completions.create(
                model=MODEL,
                messages=build_messages(history, question),
                temperature=0.6,
                max_completion_tokens=1500,
                reasoning_effort="low",
                include_reasoning=False,
            )
            answer = (result.choices[0].message.content or "").strip()
            if not answer:
                print("Bot: The model returned an empty response. Please try again.\n")
                continue
        except AuthenticationError:
            print("Error: Invalid Groq API key. Check GROQ_API_KEY in .env.\n")
            continue
        except RateLimitError:
            print("Error: Free usage limit reached. Try again after the limit resets.\n")
            continue
        except APIConnectionError:
            print("Error: Cannot connect to Groq. Check your internet connection.\n")
            continue
        except APIStatusError as error:
            print(f"Groq API error (HTTP {error.status_code}). Check model access and try again.\n")
            continue

        print(f"\nPyMind: {answer}\n")
        history.extend(
            [
                {"role": "user", "content": question},
                {"role": "assistant", "content": answer},
            ]
        )
        history = history[-MAX_HISTORY_MESSAGES:]


if __name__ == "__main__":
    main()
