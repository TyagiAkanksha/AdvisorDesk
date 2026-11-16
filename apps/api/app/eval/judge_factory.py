"""`build_judge(settings)` — picks the judge implementation for `settings.effective_judge_provider`.

A separate module so `groundedness` (which hosts `OpenAIJudge`) and `anthropic_judge` (which
imports `groundedness`) never import each other.
"""

from __future__ import annotations

from app.config import Settings
from app.eval.anthropic_judge import AnthropicJudge
from app.eval.groundedness import OpenAIJudge

__all__ = ["build_judge"]


def build_judge(settings: Settings) -> AnthropicJudge | OpenAIJudge:
    if settings.effective_judge_provider == "anthropic":
        return AnthropicJudge.from_settings(settings)
    return OpenAIJudge.from_settings(settings)
