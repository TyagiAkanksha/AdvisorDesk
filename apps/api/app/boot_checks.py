"""Pure boot-time credential checks, kept out of `app.main` so they are unit-testable.

`missing_api_key_errors` validates the ACTIVE `llm_provider`'s key and the ACTIVE
`embedding_provider`'s key (they differ under `llm_provider="anthropic"`, which still embeds
through OpenAI). Dev is exempt: the offline path boots with every key blank.
"""

from __future__ import annotations

from typing import Literal

from app.config import Settings

__all__ = ["missing_api_key_errors"]

_KEY_FIELDS: dict[str, tuple[str, str]] = {
    "openai": ("OPENAI_API_KEY", "openai_api_key"),
    "nvidia": ("NVIDIA_API_KEY", "nvidia_api_key"),
    "anthropic": ("ANTHROPIC_API_KEY", "anthropic_api_key"),
}


def _message(provider: Literal["openai", "nvidia", "anthropic"]) -> str:
    env_var, attr = _KEY_FIELDS[provider]
    return (
        f"{env_var} is required to run app.main but Settings().{attr} "
        f"is empty. Set the {env_var} environment variable (PRD §9)."
    )


def missing_api_key_errors(settings: Settings) -> list[str]:
    """One error message per missing active-provider key (deduped); `[]` in dev."""
    if settings.is_dev:
        return []
    errors: list[str] = []
    if not settings.llm_api_key.get_secret_value():
        errors.append(_message(settings.llm_provider))
    if not settings.embedding_api_key.get_secret_value():
        message = _message(settings.embedding_provider)
        if message not in errors:
            errors.append(message)
    return errors
