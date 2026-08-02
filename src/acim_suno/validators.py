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

SECTION_LABEL = re.compile(r"^\s*\[{1,2}[^\]]+\]{1,2}\s*$")
NON_LYRICAL_DIRECTION = re.compile(
    r"^\s*\((?:soft\s+)?(?:instrumental(?:\s+(?:intro|break|outro))?"
    r"|music\s+(?:fades?|drops?|swells?)|fade\s+(?:in|out))\)\s*$",
    re.IGNORECASE,
)
AD_LIB = re.compile(r"^\s*\((.*)\)\s*$", re.DOTALL)
TREATMENT_MARKER = re.compile(r"^\s*\((?:spoken|sung)\)\s*(?::\s*)?", re.IGNORECASE)
BPM_PATTERN = re.compile(r"(?<!\d)(\d{2,3})\s*BPM\b", re.IGNORECASE)
EDITORIAL_MARKER = re.compile(
    r"\s*W-pI\.[0-9]+\.[0-9]+\.|\s*\(\d+\)|\s\d+\s+(?=[A-Z])"
)


def normalize_source_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("—", "-").replace("–", "-")
    value = EDITORIAL_MARKER.sub(" ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip().casefold()


def _match_positions(source: str, chunk: str) -> list[int]:
    positions: list[int] = []
    start = 0
    while True:
        idx = source.find(chunk, start)
        if idx == -1:
            break
        positions.append(idx)
        start = idx + 1
    return positions


def _is_verbatim_line(norm_line: str, norm_source: str) -> bool:
    if not norm_line:
        return False
    if norm_line in norm_source:
        return True
    n = len(norm_line)
    words = norm_line.split()
    if words:
        for count in range(2, len(words) + 1):
            if len(words) % count:
                continue
            unit_words = words[: len(words) // count]
            if unit_words * count == words:
                unit = " ".join(unit_words)
                if unit in norm_source:
                    return True

    position = 0
    previous_start = -1
    previous_end = -1
    while position < n:
        matched = False
        for end in range(n, position, -1):
            chunk = norm_line[position:end]
            positions = _match_positions(norm_source, chunk)
            candidates = [
                p
                for p in positions
                if previous_start == -1
                or p == previous_end
                or p + len(chunk) == previous_start
            ]
            if candidates:
                position = end
                previous_start = candidates[0]
                previous_end = candidates[0] + len(chunk)
                matched = True
                break
        if not matched:
            return False
    return True


def validate_verbatim_lyrics(lyrics: str, source_text: str) -> ValidationReport:
    normalized_source = normalize_source_text(source_text)
    issues: list[ValidationIssue] = []
    checked_lines = 0

    for line_number, raw_line in enumerate(lyrics.splitlines(), start=1):
        line = raw_line.strip()
        if not line or SECTION_LABEL.fullmatch(line) or NON_LYRICAL_DIRECTION.fullmatch(line):
            continue
        checked_lines += 1
        ad_lib = AD_LIB.fullmatch(line)
        if ad_lib:
            line = ad_lib.group(1).strip()
        else:
            line = TREATMENT_MARKER.sub("", line).strip()
        if not _is_verbatim_line(normalize_source_text(line), normalized_source):
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
    for item in sorted(assignments, key=lambda x: (x.language, x.lesson_number)):
        by_language.setdefault(item.language, []).append(item)

    for language, items in by_language.items():
        for left_index, left in enumerate(items):
            for right in items[left_index + 1 :]:
                gap = right.lesson_number - left.lesson_number
                if gap >= constraints.minimum_exact_style_gap:
                    break
                if left.style_id == right.style_id:
                    issues.append(
                        ValidationIssue(
                            code="exact_style_gap",
                            message=(
                                f"{left.style_id} repeats at lessons "
                                f"{left.lesson_number} and {right.lesson_number} ({language})"
                            ),
                        )
                    )

    return ValidationReport(
        passed=not issues,
        issues=issues,
        metadata={"style_usage": dict(sorted(counts.items()))},
    )
