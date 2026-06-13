"""
business_logic/roleplay/roleplay_runner.py
Run a turn of the property-pitch roleplay (Rule 10).

On an end phrase, deletes the session and returns LLM feedback. Otherwise advances
the session and returns Carol's next line. Always uses the local Ollama model.
"""

from __future__ import annotations

from business_logic.roleplay.prompts import ROLEPLAY_SYSTEM, build_feedback_prompt
from business_logic.roleplay.roleplay_detection import is_end_phrase
from business_logic.roleplay.roleplay_state import (
    delete_roleplay_session,
    get_roleplay_session,
    upsert_roleplay_session,
)
from config.model_settings import MODEL_FAST
from model_runtime.providers import ollama_provider


async def run_roleplay(conversation_id: str, user_msg: str, history: list) -> str:
    """Advance the roleplay or, on an end phrase, end it and return feedback."""
    # End session → generate feedback.
    if is_end_phrase(user_msg):
        session = delete_roleplay_session(conversation_id)
        exchanges = session.get("exchanges", 0)
        prompt = build_feedback_prompt(exchanges, history)
        feedback = await ollama_provider.complete(
            [{"role": "user", "content": prompt}], model=MODEL_FAST
        )
        return f"**[End of practice — here's your feedback:]**\n\n{feedback}"

    # Active session → Carol responds.
    session = get_roleplay_session(conversation_id)
    exchanges = (session["exchanges"] if session else 0) + 1
    upsert_roleplay_session(conversation_id, exchanges)

    messages = [{"role": "system", "content": ROLEPLAY_SYSTEM}]
    for m in history:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_msg})

    return await ollama_provider.complete(messages, model=MODEL_FAST)
