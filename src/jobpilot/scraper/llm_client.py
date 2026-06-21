"""
OpenRouter LLM client wrapper for JobPilot agents.

Provides a unified interface for calling any OpenRouter model with
JSON-structured output.  Used by the keyword generator and job matcher.
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional
from openai import OpenAI

logger = logging.getLogger(__name__)

# Auto-load .env so this module works standalone
_dotenv_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
if _dotenv_path.exists():
    from dotenv import load_dotenv
    load_dotenv(_dotenv_path)

# Default model — free/cheap and good at structured output
DEFAULT_MODEL = "deepseek/deepseek-chat"


def get_client() -> Optional[OpenAI]:
    """Return an OpenRouter client if OPENROUTER_API_KEY is set."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        logger.warning("OPENROUTER_API_KEY not set — LLM features disabled")
        return None
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )


def call_llm_json(
    system_prompt: str,
    user_prompt: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.1,
    max_tokens: int = 2000,
) -> dict | None:
    """
    Call an LLM via OpenRouter and return the response as a parsed JSON dict.

    Args:
        system_prompt: System-level instructions.
        user_prompt: User message content.
        model: OpenRouter model ID (default: deepseek/deepseek-chat).
        temperature: Sampling temperature (0.1 for deterministic).
        max_tokens: Max output tokens.

    Returns:
        Parsed JSON dict, or None on failure.
    """
    client = get_client()
    if not client:
        return None

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=temperature,
            max_tokens=max_tokens,
        )

        content = response.choices[0].message.content
        if not content:
            logger.warning("LLM returned empty content")
            return None

        # Strip markdown code fences (```json ... ```) if present
        content = content.strip()
        if content.startswith("```"):
            # Remove opening fence (```json, ```, etc.) and closing fence
            content = content.split("\n", 1)[-1] if "\n" in content else content[3:]
            content = content.rsplit("```", 1)[0] if "```" in content else content
            content = content.strip()

        return json.loads(content)

    except json.JSONDecodeError as e:
        logger.error("LLM response was not valid JSON: %s", e)
        logger.debug("Raw content: %s", content[:500] if content else "(empty)")
        return None
    except Exception as e:
        logger.error("LLM call failed: %s", e)
        return None
