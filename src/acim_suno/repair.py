from __future__ import annotations

from .llm import LLMProvider
from .models import (
    GeneratedLyric,
    LessonRecord,
    SongArtifact,
    TargetedRepairRequest,
    ValidationReport,
)
from .validators import validate_verbatim_lyrics


def create_repair_request(
    artifact: SongArtifact,
    report: ValidationReport,
    max_retries: int = 3,
) -> TargetedRepairRequest:
    failed_fields: list[str] = []
    for issue in report.issues:
        if issue.code == "non_verbatim_line" or issue.code == "no_lyric_content":
            failed_fields.append("lyrics")
        elif issue.code in ("core_prompt_changed", "final_prompt_missing_core"):
            failed_fields.append("style_adaptation")
        elif issue.code in ("bpm_above_range", "bpm_below_range"):
            failed_fields.append("adaptation.bpm")
        else:
            failed_fields.append(issue.code)

    return TargetedRepairRequest(
        lesson_number=artifact.lesson_number,
        language=artifact.language,
        failed_fields=sorted(set(failed_fields)),
        validator_report=report,
        current_artifact=artifact,
        max_retries=max_retries,
        error_messages=[issue.message for issue in report.issues],
    )


def repair_song(
    request: TargetedRepairRequest,
    lesson: LessonRecord,
    llm: LLMProvider,
    prompt_version: str = "0.1.0",
) -> tuple[SongArtifact | None, TargetedRepairRequest, ValidationReport]:
    if request.retry_count >= request.max_retries:
        return (
            None,
            request,
            ValidationReport(
                passed=False,
                issues=[
                    {
                        "code": "max_retries_exceeded",
                        "message": f"Exceeded {request.max_retries} repair attempts",
                        "severity": "error",
                    }
                ],
            ),
        )

    artifact = request.current_artifact
    if artifact is None:
        return (
            None,
            request,
            ValidationReport(
                passed=False,
                issues=[
                    {"code": "no_artifact", "message": "No artifact to repair", "severity": "error"}
                ],
            ),
        )

    needs_lyrics_repair = "lyrics" in request.failed_fields
    any("adaptation" in f for f in request.failed_fields)

    repaired_lyrics: list[GeneratedLyric] = list(artifact.lyrics)

    if needs_lyrics_repair:
        system_prompt = (
            "Repair only the validator-listed fields. Preserve all passing material byte-for-byte. "
            "For source failures, select a contiguous approved source phrase that matches. "
            "Output JSON with repaired lyrics only."
        )
        user_prompt = (
            f"Repair lyrics for Lesson {request.lesson_number}.\n"
            f"Errors: {'; '.join(request.error_messages)}\n\n"
            f"Current lyrics:\n{artifact.full_lyrics_text}\n\n"
            f"Source sentences:\n"
            + "\n".join(s.text for s in lesson.sentences)
            + "\n\nReplacement must use contiguous approved source text."
        )
        result = llm.generate_structured(system_prompt, user_prompt, list[GeneratedLyric])
        if result:
            repaired_lyrics = result

    from .generator import build_full_lyrics_text

    new_full_text = build_full_lyrics_text(repaired_lyrics)
    repaired_artifact = SongArtifact(
        lesson_number=artifact.lesson_number,
        title=artifact.title,
        archetype=artifact.archetype,
        lesson_type=artifact.lesson_type,
        language=artifact.language,
        style_id=artifact.style_id,
        style_adaptation=artifact.style_adaptation,
        lyric_plan=artifact.lyric_plan,
        lyrics=repaired_lyrics,
        full_lyrics_text=new_full_text,
        source_hash=artifact.source_hash,
        assignment_version=artifact.assignment_version,
        generator_version=artifact.generator_version,
    )

    new_report = validate_verbatim_lyrics(new_full_text, lesson.source_text)

    updated_request = TargetedRepairRequest(
        lesson_number=request.lesson_number,
        language=request.language,
        failed_fields=request.failed_fields,
        validator_report=request.validator_report,
        current_artifact=artifact,
        retry_count=request.retry_count + 1,
        max_retries=request.max_retries,
        error_messages=request.error_messages,
    )

    if new_report.passed:
        return repaired_artifact, updated_request, new_report

    if updated_request.retry_count < updated_request.max_retries:
        next_request = TargetedRepairRequest(
            lesson_number=request.lesson_number,
            language=request.language,
            failed_fields=request.failed_fields,
            validator_report=new_report,
            current_artifact=repaired_artifact,
            retry_count=updated_request.retry_count,
            max_retries=request.max_retries,
            error_messages=[issue.message for issue in new_report.issues],
        )
        return repair_song(next_request, lesson, llm, prompt_version)

    return None, updated_request, new_report
