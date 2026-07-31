from __future__ import annotations

from .llm import LLMProvider, generate_lyrics
from .models import (
    GeneratedLyric,
    LessonRecord,
    LyricPlan,
    SongArtifact,
    StyleAdaptation,
)


def build_full_lyrics_text(lyrics: list[GeneratedLyric]) -> str:
    parts: list[str] = []
    for lyric in lyrics:
        if lyric.text.strip():
            parts.append(f"[{lyric.section_label}]")
            parts.append(lyric.text.strip())
    return "\n".join(parts)


def create_song_artifact(
    lesson: LessonRecord,
    plan: LyricPlan,
    adaptation: StyleAdaptation,
    lyrics: list[GeneratedLyric],
    *,
    assignment_version: str = "scipy-milp-0.1.0",
    generator_version: str = "0.1.0",
) -> SongArtifact:
    full_text = build_full_lyrics_text(lyrics)
    return SongArtifact(
        lesson_number=lesson.lesson_number,
        title=lesson.title,
        archetype=plan.archetype,
        lesson_type=lesson.lesson_type,
        language=lesson.language,
        style_id=adaptation.style_id,
        style_adaptation=adaptation,
        lyric_plan=plan,
        lyrics=lyrics,
        full_lyrics_text=full_text,
        source_hash=lesson.source.source_hash,
        assignment_version=assignment_version,
        generator_version=generator_version,
    )


def generate_song(
    lesson: LessonRecord,
    plan: LyricPlan,
    adaptation: StyleAdaptation,
    llm: LLMProvider,
    prompt_version: str = "0.1.0",
) -> SongArtifact:
    lyrics = generate_lyrics(lesson, plan, adaptation, llm, prompt_version)
    return create_song_artifact(lesson, plan, adaptation, lyrics)
