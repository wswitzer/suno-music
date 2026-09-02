from __future__ import annotations

from .llm import LLMProvider
from .models import (
    GeneratedLyric,
    GeneratedLyricsResponse,
    SongArtifact,
    SourceUnit,
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
        if issue.code in ("non_verbatim_line", "no_lyric_content"):
            failed_fields.append("lyrics")
        elif issue.code in ("core_prompt_changed", "final_prompt_missing_core"):
            failed_fields.append("style_adaptation")
        elif issue.code in ("bpm_above_range", "bpm_below_range"):
            failed_fields.append("adaptation.bpm")
        else:
            failed_fields.append(issue.code)

    return TargetedRepairRequest(
        unit_ref=artifact.unit_ref,
        sequence_index=artifact.sequence_index,
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
    lesson: SourceUnit,
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

    repaired_lyrics: list[GeneratedLyric] = list(artifact.lyrics)

    if "lyrics" in request.failed_fields:
        system_prompt = (
            "Repair only the validator-listed fields. Preserve all passing material byte-for-byte. "
            "For source failures, select a contiguous approved source phrase that matches. "
            "Output repaired lyric sections only."
        )
        user_prompt = (
            f"Repair lyrics for source unit {request.unit_ref}.\n"
            f"Errors: {'; '.join(request.error_messages)}\n\n"
            f"Current lyrics:\n{artifact.full_lyrics_text}\n\n"
            "Source sentences:\n"
            + "\n".join(sentence.text for sentence in lesson.sentences)
            + "\n\nReplacement must use contiguous approved source text."
        )
        result = llm.generate_structured(system_prompt, user_prompt, GeneratedLyricsResponse)
        if result.root:
            repaired_lyrics = result.root

    from .generator import build_full_lyrics_text

    new_full_text = build_full_lyrics_text(repaired_lyrics)
    repaired_artifact = artifact.model_copy(
        update={
            "lyrics": repaired_lyrics,
            "full_lyrics_text": new_full_text,
        }
    )

    new_report = validate_verbatim_lyrics(new_full_text, lesson.source_text)

    updated_request = request.model_copy(
        update={
            "retry_count": request.retry_count + 1,
        }
    )

    if new_report.passed:
        return repaired_artifact, updated_request, new_report

    if updated_request.retry_count < updated_request.max_retries:
        next_request = updated_request.model_copy(
            update={
                "validator_report": new_report,
                "current_artifact": repaired_artifact,
                "error_messages": [issue.message for issue in new_report.issues],
            }
        )
        return repair_song(next_request, lesson, llm, prompt_version)

    return None, updated_request, new_report
