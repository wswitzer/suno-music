from __future__ import annotations

import re
import unicodedata
from collections import Counter

from .models import (
    AssignmentConstraints,
    AssignmentRecord,
    StyleAdaptation,
    StyleRecord,
    ValidationIssue,
    ValidationReport,
)

SECTION_LABEL = re.compile(r"^\s*\[[^\]]+\]\s*$")
NON_LYRICAL_DIRECTION = re.compile(
    r"^\s*\((?:soft\s+)?(?:instrumental(?:\s+(?:intro|break|outro))?"
    r"|music\s+(?:fades?|drops?|swells?)|fade\s+(?:in|out))\)\s*$",
    re.IGNORECASE,
)
BPM_PATTERN = re.compile(r"(?<!\d)(\d{2,3})\s*BPM\b", re.IGNORECASE)


def normalize_source_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("—", "-").replace("–", "-")
    value = re.sub(r"\s+", " ", value)
    return value.strip().casefold()


def validate_verbatim_lyrics(lyrics: str, source_text: str) -> ValidationReport:
    normalized_source = normalize_source_text(source_text)
    issues: list[ValidationIssue] = []
    checked_lines = 0

    for line_number, raw_line in enumerate(lyrics.splitlines(), start=1):
        line = raw_line.strip()
        if not line or SECTION_LABEL.fullmatch(line) or NON_LYRICAL_DIRECTION.fullmatch(line):
            continue
        checked_lines += 1
        if normalize_source_text(line) not in normalized_source:
            issues.append(
                ValidationIssue(
                    code="non_verbatim_line",
                    message="Line does not occur contiguously in the approved source",
                    line_number=line_number,
                )
            )

    if checked_lines == 0:
        issues.append(ValidationIssue(code="no_lyric_content", message="No lyric lines were found"))

    return ValidationReport(
        passed=not any(issue.severity == "error" for issue in issues),
        issues=issues,
        metadata={"checked_lines": checked_lines},
    )


def validate_style_adaptation(adaptation: StyleAdaptation, style: StyleRecord) -> ValidationReport:
    issues: list[ValidationIssue] = []
    if adaptation.style_id != style.style_id:
        issues.append(ValidationIssue(code="style_id_mismatch", message="Wrong style target"))
    if adaptation.core_prompt != style.core_prompt:
        issues.append(
            ValidationIssue(code="core_prompt_changed", message="Core prompt was modified")
        )
    if not adaptation.final_prompt.startswith(style.core_prompt):
        issues.append(
            ValidationIssue(
                code="final_prompt_missing_core",
                message="Final prompt must begin with the immutable core prompt",
            )
        )
    if not adaptation.core_identity_preserved:
        issues.append(
            ValidationIssue(
                code="core_identity_not_preserved",
                message="Style identity was not preserved",
            )
        )

    bpm_values = [int(value) for value in BPM_PATTERN.findall(adaptation.adaptation)]
    if adaptation.bpm is not None:
        bpm_values.append(adaptation.bpm)
    for bpm in bpm_values:
        if style.tempo_min is not None and bpm < style.tempo_min:
            issues.append(
                ValidationIssue(
                    code="bpm_below_range",
                    message=f"BPM {bpm} is below {style.tempo_min}",
                )
            )
        if style.tempo_max is not None and bpm > style.tempo_max:
            issues.append(
                ValidationIssue(
                    code="bpm_above_range",
                    message=f"BPM {bpm} is above {style.tempo_max}",
                )
            )

    return ValidationReport(passed=not issues, issues=issues)


def validate_assignment_batch(
    assignments: list[AssignmentRecord],
    styles: list[StyleRecord],
    constraints: AssignmentConstraints,
) -> ValidationReport:
    issues: list[ValidationIssue] = []
    style_ids = {style.style_id for style in styles}
    counts = Counter(item.style_id for item in assignments)

    for style_id in sorted(style_ids):
        count = counts.get(style_id, 0)
        if count < constraints.minimum_style_usage:
            issues.append(
                ValidationIssue(
                    code="style_underused",
                    message=f"{style_id} used {count} times",
                )
            )
        if count > constraints.maximum_style_usage:
            issues.append(
                ValidationIssue(
                    code="style_overused",
                    message=f"{style_id} used {count} times",
                )
            )

    by_language: dict[str, list[AssignmentRecord]] = {}
    for item in sorted(assignments, key=lambda x: (x.language, x.sequence_index, x.unit_ref)):
        by_language.setdefault(item.language, []).append(item)

    for language, items in by_language.items():
        for left_index, left in enumerate(items):
            for right in items[left_index + 1 :]:
                gap = right.sequence_index - left.sequence_index
                if gap >= constraints.minimum_exact_style_gap:
                    break
                if left.style_id == right.style_id:
                    issues.append(
                        ValidationIssue(
                            code="exact_style_gap",
                            message=(
                                f"{left.style_id} repeats at units "
                                f"{left.unit_ref} and {right.unit_ref} ({language})"
                            ),
                        )
                    )

    return ValidationReport(
        passed=not issues,
        issues=issues,
        metadata={"style_usage": dict(sorted(counts.items()))},
    )
