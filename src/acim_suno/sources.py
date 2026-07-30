from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Protocol

from .models import LessonRecord, LessonType, SourceMetadata, SourceSentence


class SourceProvider(Protocol):
    def fetch_lessons(self, start: int, end: int, language: str = "en") -> list[LessonRecord]: ...

    def get_source_hash(self) -> str: ...


class ACIMJsonSourceProvider:
    def __init__(self, json_path: str | Path) -> None:
        self._path = Path(json_path)
        with self._path.open("r", encoding="utf-8") as f:
            self._data = json.load(f)
        self._source_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        return hashlib.sha256(
            self._path.read_bytes()
        ).hexdigest()

    def get_source_hash(self) -> str:
        return self._source_hash

    def fetch_lessons(
        self,
        start: int = 116,
        end: int = 199,
        language: str = "en",
    ) -> list[LessonRecord]:
        parts = self._data.get("parts", {})
        all_lessons: dict[str, dict] = {}
        for part_key, part in parts.items():
            lesson_dict = part.get("lessons", {})
            for k, v in lesson_dict.items():
                if k in all_lessons:
                    continue
                all_lessons[k] = v

        records: list[LessonRecord] = []
        for num in range(start, end + 1):
            key = str(num)
            raw = all_lessons.get(key)
            if raw is None:
                continue

            title = raw.get("title_clean") or raw.get("title", "") or f"Lesson {num}"
            paragraphs = raw.get("paragraphs", [])
            practice_raw = raw.get("practice_instructions", {})
            practice_instructions: dict[str, str] = {}
            if isinstance(practice_raw, dict):
                for pk, pv in practice_raw.items():
                    if isinstance(pv, str):
                        practice_instructions[pk] = pv
                    elif isinstance(pv, (list, dict)):
                        practice_instructions[pk] = json.dumps(pv, ensure_ascii=False)

            reviewed = raw.get("reviewed_lessons")

            is_review = reviewed is not None and len(paragraphs) <= 3
            is_experiential = (
                "stillness" in title.lower()
                or "quiet" in title.lower()
                or "experiential" in title.lower()
                or "meditation" in title.lower()
            )

            if is_review:
                lesson_type = LessonType.REVIEW
            elif is_experiential:
                lesson_type = LessonType.EXPERIENTIAL
            else:
                lesson_type = LessonType.STANDARD

            paragraph_texts = self._extract_paragraph_texts(paragraphs)
            sentences = self._build_sentences(raw, num, paragraph_texts)

            records.append(
                LessonRecord(
                    lesson_number=num,
                    language=language,
                    title=title,
                    lesson_type=lesson_type,
                    source=SourceMetadata(
                        edition="acim-workbook-enhanced",
                        url=f"file://{self._path}",
                        source_hash=self._source_hash,
                        rights_status="review_required",
                    ),
                    sentences=sentences,
                    paragraphs=paragraph_texts,
                    practice_instructions=practice_instructions,
                    reviewed_lessons=reviewed,
                )
            )
        return records

    def _extract_paragraph_texts(self, paragraphs: list) -> list[str]:
        texts: list[str] = []
        if not isinstance(paragraphs, list):
            return texts
        for para in paragraphs:
            if isinstance(para, str):
                texts.append(para)
            elif isinstance(para, dict):
                sents = para.get("sentences", [])
                if isinstance(sents, list):
                    para_text = " ".join(
                        s.get("text", "") for s in sents if isinstance(s, dict)
                    ).strip()
                    if para_text:
                        texts.append(para_text)
        return texts

    def _build_sentences(self, raw: dict, lesson_number: int,
                         paragraph_texts: list[str]) -> list[SourceSentence]:
        sentences: list[SourceSentence] = []
        sentence_id_counter = 0

        def add_sentence(text: str, category: str) -> None:
            nonlocal sentence_id_counter
            text = text.strip()
            if not text:
                return
            sentence_id_counter += 1
            sentences.append(
                SourceSentence(
                    sentence_id=f"L{lesson_number}_{sentence_id_counter:03d}",
                    text=text,
                    category=category,
                )
            )

        title = raw.get("title_clean") or raw.get("title", "")
        if title:
            add_sentence(title, "title")

        idea = raw.get("idea_clean") or raw.get("idea", "")
        if idea:
            add_sentence(idea, "teaching")

        for para_text in paragraph_texts:
            if para_text.strip():
                add_sentence(para_text.strip(), "teaching")

        practice_raw = raw.get("practice_instructions", {})
        if isinstance(practice_raw, dict):
            desc = practice_raw.get("description", "")
            if desc:
                add_sentence(desc, "practice")
            method = practice_raw.get("method", "")
            if method:
                add_sentence(method, "practice")

        prayer = raw.get("prayer", "")
        if prayer and isinstance(prayer, str) and prayer.strip():
            add_sentence(prayer.strip(), "prayer")

        if not sentences:
            add_sentence(f"Lesson {lesson_number}", "other")

        return sentences


def create_source_provider(
    source_type: str = "acim_json",
    json_path: str | Path = "/Users/trust/Projects/acim-core-data/workbook_enhanced.json",
) -> ACIMJsonSourceProvider:
    if source_type == "acim_json":
        return ACIMJsonSourceProvider(json_path)
    raise ValueError(f"Unknown source type: {source_type}")
