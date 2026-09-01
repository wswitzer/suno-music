from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .llm import LLMProvider, score_compatibility
from .models import CompatibilityScore, SourceUnit, StyleRecord


def build_score_cache_key(
    unit_ref: str,
    source_hash: str,
    style_hash: str,
    prompt_version: str,
    model_name: str,
) -> str:
    raw = f"{unit_ref}:{source_hash}:{style_hash}:{prompt_version}:{model_name}"
    return hashlib.sha256(raw.encode()).hexdigest()


def compute_compatibility_scores(
    lessons: list[SourceUnit],
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
    style_hash = hashlib.sha256(
        json.dumps([s.model_dump(mode="json") for s in styles], sort_keys=True).encode()
    ).hexdigest()

    for unit in lessons:
        cache_key = build_score_cache_key(
            unit.unit_ref,
            unit.source.source_hash,
            style_hash,
            prompt_version,
            llm.model_name,
        )
        cache_file = cache_path / f"{cache_key}.jsonl"

        if cache_file.exists() and not force_recompute:
            with cache_file.open("r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        scores.append(CompatibilityScore.model_validate(json.loads(line)))
            continue

        unit_scores = score_compatibility(unit, styles, llm, prompt_version)
        normalized_scores: list[CompatibilityScore] = []
        for score in unit_scores:
            normalized_scores.append(
                score.model_copy(
                    update={
                        "unit_ref": unit.unit_ref,
                        "sequence_index": unit.sequence_index,
                        "lesson_number": unit.lesson_number,
                        "language": unit.language,
                    }
                )
            )

        with cache_file.open("w", encoding="utf-8") as f:
            for score in normalized_scores:
                f.write(json.dumps(score.model_dump(mode="json"), ensure_ascii=False) + "\n")

        scores.extend(normalized_scores)

    return scores


def filter_scores_for_optimizer(
    scores: list[CompatibilityScore],
    lessons: list[SourceUnit],
    styles: list[StyleRecord],
) -> list[CompatibilityScore]:
    unit_refs = {unit.unit_ref for unit in lessons}
    style_ids = {style.style_id for style in styles}
    return [score for score in scores if score.unit_ref in unit_refs and score.style_id in style_ids]
