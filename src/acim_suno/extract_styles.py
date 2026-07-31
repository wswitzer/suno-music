from __future__ import annotations

import csv
import re
from pathlib import Path

from .models import StyleRecord

LESSON_COLUMNS = ("lesson_number", "lesson", "number")
TITLE_COLUMNS = ("title", "lesson_title")
STYLE_COLUMNS = ("styles_raw", "suno_style", "style", "style_prompt")


def _first_present(row: dict[str, str], candidates: tuple[str, ...]) -> str | None:
    lowered = {key.strip().lower(): value for key, value in row.items() if key}
    for candidate in candidates:
        value = lowered.get(candidate)
        if value is not None and value.strip():
            return value.strip()
    return None


def _parse_lesson_number(raw: str | None) -> int | None:
    if not raw:
        return None
    match = re.search(r"\d+", raw)
    return int(match.group()) if match else None


def extract_styles_from_csv(
    csv_path: str | Path,
    *,
    min_lesson: int = 290,
    max_lesson: int = 361,
) -> list[StyleRecord]:
    styles: list[StyleRecord] = []
    seen_prompts: set[str] = set()

    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("CSV has no header row")

        for row in reader:
            lesson_number = _parse_lesson_number(_first_present(row, LESSON_COLUMNS))
            if lesson_number is None or not min_lesson <= lesson_number <= max_lesson:
                continue

            prompt = _first_present(row, STYLE_COLUMNS)
            if not prompt:
                continue

            dedupe_key = " ".join(prompt.split()).casefold()
            if dedupe_key in seen_prompts:
                continue
            seen_prompts.add(dedupe_key)

            styles.append(
                StyleRecord(
                    style_id=f"STYLE_{lesson_number}",
                    source_lesson=lesson_number,
                    name=_first_present(row, TITLE_COLUMNS) or f"Source lesson {lesson_number}",
                    core_prompt=prompt,
                )
            )

    if not styles:
        raise ValueError("No styles found; inspect the CSV headers and lesson range")
    return styles
