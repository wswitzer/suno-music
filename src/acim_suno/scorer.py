from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .llm import LLMProvider, score_compatibility
from .models import CompatibilityScore, LessonRecord, StyleRecord


def build_score_cache_key(
    lesson_number: int,
    lesson_hash: str,
    style_hash: str,
    prompt_version: str,
    model_name: str,
) -> str:
    raw = f"{lesson_number}:{lesson_hash}:{style_hash}:{prompt_version}:{model_name}"
    return hashlib.sha256(raw.encode()).hexdigest()


def compute_compatibility_scores(
    lessons: list[LessonRecord],
    styles: list[StyleRecord],
    llm: LLMProvider,
    *,
    prompt_version: str = "0.1.0",
    cache_dir: str | Path = "outputs/scores",
    force_recompute: bool = False,
) -> list[CompatibilityScore]:
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)

    scores: list[CompatibilityScore] = []

    for lesson in lessons:
        style_hash = hashlib.sha256(
            json.dumps([s.model_dump(mode="json") for s in styles], sort_keys=True).encode()
        ).hexdigest()
        lesson_hash = lesson.source.source_hash
        cache_key = build_score_cache_key(
            lesson.lesson_number, lesson_hash, style_hash, prompt_version, llm.model_name
        )
        cache_file = cache_path / f"{cache_key}.jsonl"

        if cache_file.exists() and not force_recompute:
            with cache_file.open("r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        scores.append(CompatibilityScore.model_validate(json.loads(line)))
            continue

        lesson_scores = score_compatibility(lesson, styles, llm, prompt_version)

        with cache_file.open("w", encoding="utf-8") as f:
            for sc in lesson_scores:
                f.write(json.dumps(sc.model_dump(mode="json"), ensure_ascii=False) + "\n")

        scores.extend(lesson_scores)

    return scores


def filter_scores_for_optimizer(
    scores: list[CompatibilityScore],
    lessons: list[LessonRecord],
    styles: list[StyleRecord],
) -> list[CompatibilityScore]:
    lesson_numbers = {l.lesson_number for l in lessons}
    style_ids = {s.style_id for s in styles}
    return [
        s for s in scores
        if s.lesson_number in lesson_numbers and s.style_id in style_ids
    ]
