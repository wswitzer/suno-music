from __future__ import annotations

from .llm import LLMProvider, plan_lyrics, select_archetype
from .models import (
    LessonAnalysisProfile,
    LyricPlan,
    SongArchetype,
    SourceUnit,
    UnitType,
)


def choose_archetype(
    lesson: SourceUnit,
    profile: LessonAnalysisProfile,
    llm: LLMProvider,
    prompt_version: str = "0.1.0",
) -> SongArchetype:
    if profile.ranked_archetypes:
        ranked = profile.ranked_archetypes
        if lesson.unit_type == UnitType.TEXT_SECTION:
            ranked = [item for item in ranked if item != SongArchetype.PAIRED_REVIEW]
        if ranked:
            return ranked[0]
    return select_archetype(lesson, profile, llm, prompt_version)


def create_lyric_plan(
    lesson: SourceUnit,
    archetype: SongArchetype,
    llm: LLMProvider,
    prompt_version: str = "0.1.0",
) -> LyricPlan:
    return plan_lyrics(lesson, archetype, llm, prompt_version)
