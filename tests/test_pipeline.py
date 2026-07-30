from __future__ import annotations

from pathlib import Path

from acim_suno.extract_styles import extract_styles_from_csv
from acim_suno.models import (
    AssignmentConstraints,
    CompatibilityScore,
    LessonRecord,
    SourceMetadata,
    SourceSentence,
    StyleAdaptation,
    StyleRecord,
)
from acim_suno.optimizer import optimize_assignments
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
