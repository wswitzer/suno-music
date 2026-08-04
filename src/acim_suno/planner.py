from __future__ import annotations

from collections import Counter

from .llm import LLMProvider, plan_lyrics, select_archetype
from .models import (
    LessonAnalysisProfile,
    LessonRecord,
    LessonType,
    LyricPlan,
    SongArchetype,
)

COVERED_TARGETS = (
    SongArchetype.SHORT_MANTRA,
    SongArchetype.LONG_TEACHING,
)


def choose_archetype(
    lesson: LessonRecord,
    profile: LessonAnalysisProfile,
    llm: LLMProvider,
    prompt_version: str = "0.1.0",
    used: Counter[SongArchetype] | None = None,
) -> SongArchetype:
    if lesson.lesson_type == LessonType.REVIEW:
        return SongArchetype.PAIRED_REVIEW
    if profile.ranked_archetypes:
        ranked = profile.ranked_archetypes
    else:
        ranked = [select_archetype(lesson, profile, llm, prompt_version)]
    used = used or Counter()
    # Coverage guarantee, not frequency bias: ensure low-ranking archetypes
    # (short_mantra, long_teaching_compression) surface at least once when a
    # lesson recommends them, but fall back to the top-ranked pick otherwise so
    # later lessons keep the best-fit archetype.
    for candidate in COVERED_TARGETS:
        if candidate in ranked and used[candidate] == 0:
            return candidate
    return ranked[0]


def create_lyric_plan(
    lesson: LessonRecord,
    archetype: SongArchetype,
    llm: LLMProvider,
    prompt_version: str = "0.1.0",
) -> LyricPlan:
    return plan_lyrics(lesson, archetype, llm, prompt_version)
