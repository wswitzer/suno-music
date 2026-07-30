from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from acim_suno.cli import command_generate_lyrics
from acim_suno.extract_styles import extract_styles_from_csv
from acim_suno.io import dump_json
from acim_suno.llm import MockLLMProvider, generate_lyrics, score_compatibility, select_archetype
from acim_suno.models import (
    AssignmentConstraints,
    CompatibilityScore,
    CompatibilityScoreBatch,
    GeneratedLyricsResponse,
    LessonAnalysisProfile,
    LessonRecord,
    LyricPlan,
    PlanSection,
    SongArchetype,
    SongArchetypeSelection,
    SourceMetadata,
    SourceSentence,
    StyleAdaptation,
    StyleRecord,
)
from acim_suno.optimizer import optimize_assignments
from acim_suno.sources import ACIMJsonSourceProvider
from acim_suno.validators import (
    validate_assignment_batch,
    validate_style_adaptation,
    validate_verbatim_lyrics,
)


def lesson(number: int) -> LessonRecord:
    return LessonRecord(
        lesson_number=number,
        language="en",
        title=f"Demo {number}",
        source=SourceMetadata(
            edition="synthetic-demo",
            source_hash=f"demo-{number}",
            rights_status="user_supplied",
        ),
        sentences=[SourceSentence(sentence_id="title", text=f"Demo {number}")],
    )


def test_global_optimizer_uses_all_styles() -> None:
    lessons = [lesson(number) for number in range(116, 120)]
    styles = [
        StyleRecord(style_id="A", name="A", core_prompt="Ambient", primary_bucket="ambient"),
        StyleRecord(style_id="B", name="B", core_prompt="Soul", primary_bucket="soul"),
        StyleRecord(style_id="C", name="C", core_prompt="Chant", primary_bucket="chant"),
    ]
    values = {
        116: {"A": 8.5, "B": 7.0, "C": 9.0},
        117: {"A": 8.8, "B": 8.0, "C": 7.2},
        118: {"A": 6.5, "B": 9.2, "C": 8.4},
        119: {"A": 9.4, "B": 7.4, "C": 6.8},
    }
    scores = [
        CompatibilityScore(lesson_number=number, style_id=style_id, total=score)
        for number, style_scores in values.items()
        for style_id, score in style_scores.items()
    ]
    constraints = AssignmentConstraints(
        minimum_style_usage=1,
        maximum_style_usage=2,
        minimum_exact_style_gap=2,
    )

    assignments = optimize_assignments(lessons, styles, scores, constraints)
    report = validate_assignment_batch(assignments, styles, constraints)

    assert report.passed, report.model_dump()
    assert {item.style_id for item in assignments} == {"A", "B", "C"}
    assert sum(item.fit_score for item in assignments) >= 35.0


def test_verbatim_validator_rejects_invented_adlib() -> None:
    assert validate_verbatim_lyrics("[Chorus]\nI am safe.\nI am safe.", "I am safe.").passed
    report = validate_verbatim_lyrics("I am safe. (Peace is within.)", "I am safe.")
    assert not report.passed
    assert report.issues[0].code == "non_verbatim_line"


def test_style_validator_rejects_mutated_core_and_bpm() -> None:
    style = StyleRecord(
        style_id="X",
        name="Test",
        core_prompt="Warm acoustic folk.",
        tempo_min=70,
        tempo_max=90,
    )
    adaptation = StyleAdaptation(
        style_id="X",
        lesson_number=120,
        core_prompt="Changed prompt.",
        adaptation="Set the tempo to 110 BPM.",
        final_prompt="Changed prompt. Set the tempo to 110 BPM.",
        bpm=110,
    )
    codes = {issue.code for issue in validate_style_adaptation(adaptation, style).issues}
    assert {"core_prompt_changed", "final_prompt_missing_core", "bpm_above_range"} <= codes


def test_csv_extractor_filters_and_deduplicates(tmp_path: Path) -> None:
    csv_path = tmp_path / "songs.csv"
    csv_path.write_text(
        "lesson_number,title,styles_raw\n"
        "289,Outside,Not selected\n"
        "295,Ambient,Luminous pads and bells\n"
        "296,Duplicate,Luminous   pads and bells\n"
        "305,Chant,Sacred chant and drums\n",
        encoding="utf-8",
    )
    styles = extract_styles_from_csv(csv_path)
    assert [style.style_id for style in styles] == ["STYLE_295", "STYLE_305"]


def test_parenthesized_invented_adlib_is_rejected() -> None:
    report = validate_verbatim_lyrics("(Peace is within.)", "I am safe.")
    assert not report.passed
    assert report.issues[0].code == "non_verbatim_line"

    direction = validate_verbatim_lyrics("(Soft instrumental)\nI am safe.", "I am safe.")
    assert direction.passed


def test_provider_rejects_language_relabeling(tmp_path: Path) -> None:
    source_path = tmp_path / "workbook.json"
    source_path.write_text(
        '{"language":"en","parts":{"one":{"lessons":{}}}}',
        encoding="utf-8",
    )
    provider = ACIMJsonSourceProvider(source_path, source_language="en")
    with pytest.raises(ValueError, match="requested 'es'"):
        provider.fetch_lessons(116, 116, language="es")
    with pytest.raises(ValueError, match="Source declares language"):
        ACIMJsonSourceProvider(source_path, source_language="es")


def test_high_level_llm_calls_use_pydantic_wrappers() -> None:
    llm = MockLLMProvider()
    item = lesson(116)
    style = StyleRecord(
        style_id="STYLE_1",
        name="Demo",
        core_prompt="Warm acoustic folk.",
    )
    scores = score_compatibility(item, [style], llm)
    assert scores
    assert CompatibilityScoreBatch(scores).root == scores

    profile = LessonAnalysisProfile(
        lesson_number=116,
        lesson_type="standard",
        ranked_archetypes=[],
    )
    archetype = select_archetype(item, profile, llm)
    assert SongArchetypeSelection(archetype=archetype).archetype is archetype

    plan = LyricPlan(
        lesson_number=116,
        language="en",
        archetype=SongArchetype.TITLE_TEACHING_PRAYER,
        sections=[
            PlanSection(
                label="Chorus",
                function="title",
                source_sentence_ids=["title"],
            )
        ],
    )
    adaptation = StyleAdaptation(
        style_id="STYLE_1",
        lesson_number=116,
        core_prompt=style.core_prompt,
        adaptation="Gentle delivery.",
        final_prompt=f"{style.core_prompt} Gentle delivery.",
    )
    lyrics = generate_lyrics(item, plan, adaptation, llm)
    assert GeneratedLyricsResponse(lyrics).root == lyrics


def test_staged_generate_lyrics_command_uses_plan_language(tmp_path: Path) -> None:
    item = lesson(116)
    plan = LyricPlan(
        lesson_number=116,
        language="en",
        archetype=SongArchetype.TITLE_TEACHING_PRAYER,
        sections=[
            PlanSection(
                label="Chorus",
                function="title",
                source_sentence_ids=["title"],
            )
        ],
    )
    adaptation = StyleAdaptation(
        style_id="STYLE_1",
        lesson_number=116,
        core_prompt="Warm acoustic folk.",
        adaptation="Gentle delivery.",
        final_prompt="Warm acoustic folk. Gentle delivery.",
    )
    lessons_path = tmp_path / "lessons.json"
    plans_path = tmp_path / "plans.json"
    adaptations_path = tmp_path / "adaptations.json"
    output_path = tmp_path / "songs.json"
    dump_json(lessons_path, [item])
    dump_json(plans_path, [plan])
    dump_json(adaptations_path, [adaptation])

    result = command_generate_lyrics(
        Namespace(
            lessons=str(lessons_path),
            plans=str(plans_path),
            adaptations=str(adaptations_path),
            provider="mock",
            model=None,
            prompt_version="0.1.0",
            out=str(output_path),
        )
    )
    assert result == 0
    assert output_path.exists()
