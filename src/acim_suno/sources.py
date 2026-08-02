from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Protocol

from .models import LessonRecord, LessonType, SourceMetadata, SourceSentence


class SourceProvider(Protocol):
    def fetch_lessons(self, start: int, end: int, language: str = "en") -> list[LessonRecord]: ...

    def get_source_hash(self) -> str: ...


class ACIMJsonSourceProvider:
    def __init__(
        self,
        json_path: str | Path,
        *,
        source_language: str = "en",
    ) -> None:
        self._path = Path(json_path)
        with self._path.open("r", encoding="utf-8") as f:
            self._data = json.load(f)
        declared_language = self._declared_language()
        if declared_language is not None and declared_language != source_language:
            raise ValueError(
                f"Source declares language {declared_language!r}, not {source_language!r}"
            )
        self._source_language = source_language
        self._source_hash = self._compute_hash()

    def _declared_language(self) -> str | None:
        for key in ("language", "lang", "source_language"):
            value = self._data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        metadata = self._data.get("metadata")
        if isinstance(metadata, dict):
            for key in ("language", "lang", "source_language"):
                value = metadata.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    def _compute_hash(self) -> str:
        return hashlib.sha256(self._path.read_bytes()).hexdigest()

    def get_source_hash(self) -> str:
        return self._source_hash

    def fetch_lessons(
        self,
        start: int = 116,
        end: int = 199,
        language: str = "en",
    ) -> list[LessonRecord]:
        if language != self._source_language:
            raise ValueError(
                f"Source provider is bound to {self._source_language!r}; requested {language!r}"
            )
        parts = self._data.get("parts", {})
        all_lessons: dict[str, dict] = {}
        for part in parts.values():
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

            is_review = _is_review_lesson(num) or reviewed is not None
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

    def _build_sentences(
        self, raw: dict, lesson_number: int, paragraph_texts: list[str]
    ) -> list[SourceSentence]:
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


REVIEW_LESSON_RANGES = ((111, 120), (141, 150), (171, 180))


def _is_review_lesson(lesson_number: int) -> bool:
    return any(start <= lesson_number <= end for start, end in REVIEW_LESSON_RANGES)


def _reference_sort_key(reference: str) -> tuple[int, tuple[int, ...], str]:
    numbers = tuple(int(value) for value in re.findall(r"\d+", reference))
    return (0 if numbers else 1, numbers, reference.casefold())


def _ordered_pinecone_paragraphs(
    paragraphs: list[dict[str, object]],
) -> list[dict[str, object]]:
    return sorted(
        paragraphs,
        key=lambda item: _reference_sort_key(str(item.get("reference", ""))),
    )


def _pinecone_lesson_hash(
    lesson_number: int,
    language: str,
    title: str,
    paragraphs: list[dict[str, object]],
) -> str:
    payload = {
        "lesson_number": lesson_number,
        "language": language,
        "title": title,
        "paragraphs": [
            {
                "reference": str(item.get("reference", "")),
                "text": str(item.get("text", "")),
            }
            for item in paragraphs
        ],
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


DUMMY_VECTOR = [0.01] * 768


def _pinecone_push_sentence(
    sentences: list[SourceSentence],
    counter: list[int],
    text: str,
    category: str,
    lesson_num: int,
) -> None:
    text = text.strip()
    if text:
        counter[0] += 1
        sentences.append(
            SourceSentence(
                sentence_id=f"L{lesson_num}_{counter[0]:03d}",
                text=text,
                category=category,
            )
        )


class PineconeSourceProvider:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        host: str = "https://acim-text-e2xpwpt.svc.aped-4627-b74a.pinecone.io",
        source_language: str = "en",
    ) -> None:
        self._api_key = api_key or os.environ.get("PINECONE_API_KEY", "")
        if not self._api_key:
            raise ValueError("PINECONE_API_KEY required")
        self._host = host
        self._source_language = source_language
        self._provider_hash = hashlib.sha256(
            f"pinecone:{host}:{source_language}".encode()
        ).hexdigest()

    def get_source_hash(self) -> str:
        """Return provider identity; individual lessons carry content hashes."""
        return self._provider_hash

    def fetch_lessons(
        self,
        start: int = 116,
        end: int = 199,
        language: str = "en",
    ) -> list[LessonRecord]:
        if language != self._source_language:
            raise ValueError(
                f"Source provider is bound to {self._source_language!r}; requested {language!r}"
            )

        import urllib.error
        import urllib.request

        lessons_map: dict[int, dict[str, object]] = {}

        for num in range(start, end + 1):
            payload = {
                "namespace": "workbook",
                "vector": DUMMY_VECTOR,
                "topK": 100,
                "filter": {"lesson": {"$eq": num}},
                "includeMetadata": True,
            }
            req = urllib.request.Request(
                f"{self._host}/query",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Api-Key": self._api_key, "Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    result = json.loads(resp.read().decode())
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    continue
                raise

            matches = result.get("matches", [])
            if not matches:
                continue

            paragraphs_raw: list[dict[str, object]] = []
            title = f"Lesson {num}"
            for match in matches:
                meta = match.get("metadata", {})
                ref = meta.get("reference", "")
                paragraph_text = meta.get("text", "")
                if paragraph_text:
                    paragraphs_raw.append(
                        {"reference": ref, "text": paragraph_text, "metadata": meta}
                    )
                stored_title = meta.get("title", "")
                if stored_title and len(str(stored_title)) > len(str(title)):
                    title = str(stored_title)

            paragraphs_raw = _ordered_pinecone_paragraphs(paragraphs_raw)
            lessons_map[num] = {
                "title": title,
                "paragraphs": paragraphs_raw,
            }

        missing = [num for num in range(start, end + 1) if num not in lessons_map]
        if missing:
            preview = ", ".join(str(num) for num in missing[:10])
            raise ValueError(
                f"Pinecone source is missing {len(missing)} requested lesson(s): {preview}"
            )

        records: list[LessonRecord] = []
        for lesson_num in sorted(lessons_map):
            data = lessons_map[lesson_num]
            title = str(data["title"])
            paragraphs_raw = data["paragraphs"]
            if not isinstance(paragraphs_raw, list):
                raise TypeError(f"Invalid Pinecone paragraphs for lesson {lesson_num}")

            paragraph_texts: list[str] = []
            sentences: list[SourceSentence] = []
            sentence_counter = [0]

            if title:
                _pinecone_push_sentence(sentences, sentence_counter, title, "title", lesson_num)

            for paragraph in paragraphs_raw:
                if not isinstance(paragraph, dict):
                    continue
                paragraph_text = str(paragraph.get("text", ""))
                if paragraph_text:
                    paragraph_texts.append(paragraph_text)
                    _pinecone_push_sentence(
                        sentences,
                        sentence_counter,
                        paragraph_text,
                        "teaching",
                        lesson_num,
                    )

            if _is_review_lesson(lesson_num):
                lesson_type = LessonType.REVIEW
            elif any(marker in title.lower() for marker in ("stillness", "quiet", "meditation")):
                lesson_type = LessonType.EXPERIENTIAL
            else:
                lesson_type = LessonType.STANDARD

            lesson_source_hash = _pinecone_lesson_hash(lesson_num, language, title, paragraphs_raw)
            records.append(
                LessonRecord(
                    lesson_number=lesson_num,
                    language=language,
                    title=title,
                    lesson_type=lesson_type,
                    source=SourceMetadata(
                        edition=f"pinecone-acim-text-{self._host}",
                        url=f"{self._host}/query",
                        source_hash=lesson_source_hash,
                        rights_status="review_required",
                    ),
                    sentences=sentences,
                    paragraphs=paragraph_texts,
                )
            )

        return records


def create_source_provider(
    source_type: str = "pinecone",
    json_path: str | Path | None = None,
    source_language: str = "en",
) -> ACIMJsonSourceProvider | PineconeSourceProvider:
    if source_type == "pinecone":
        return PineconeSourceProvider(source_language=source_language)
    if source_type == "acim_json":
        if json_path is None:
            raise ValueError("json_path is required for acim_json source type")
        return ACIMJsonSourceProvider(json_path, source_language=source_language)
    raise ValueError(f"Unknown source type: {source_type}")
