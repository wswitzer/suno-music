from __future__ import annotations

from .llm import LLMProvider, plan_lyrics, select_archetype
from .models import (
    LessonAnalysisProfile,
    LessonRecord,
    LessonType,
    LyricPlan,
    SongArchetype,
)


def choose_archetype(
    lesson: LessonRecord,
    profile: LessonAnalysisProfile,
    llm: LLMProvider,
    prompt_version: str = "0.1.0",
) -> SongArchetype:
    if lesson.lesson_type == LessonType.REVIEW:
        return SongArchetype.PAIRED_REVIEW
    if profile.ranked_archetypes:
        return profile.ranked_archetypes[0]
    return select_archetype(lesson, profile, llm, prompt_version)


def create_lyric_plan(
    lesson: LessonRecord,
    archetype: SongArchetype,
    llm: LLMProvider,
    prompt_version: str = "0.1.0",
) -> LyricPlan:
    return plan_lyrics(lesson, archetype, llm, prompt_version)
