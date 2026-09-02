from __future__ import annotations

from .llm import LLMProvider, adapt_style
from .models import LyricPlan, SourceUnit, StyleAdaptation, StyleRecord


def create_style_adaptation(
    lesson: SourceUnit,
    style: StyleRecord,
    plan: LyricPlan,
    llm: LLMProvider,
    prompt_version: str = "0.1.0",
) -> StyleAdaptation:
    return adapt_style(lesson, style, plan, llm, prompt_version)
