from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from .models import (
    CompatibilityScore,
    CompatibilityScoreBatch,
    GeneratedLyric,
    GeneratedLyricsResponse,
    LessonAnalysisProfile,
    LyricPlan,
    PlanSection,
    SongArchetype,
    SongArchetypeSelection,
    SourceUnit,
    StyleAdaptation,
    StyleRecord,
    UnitType,
)

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    @abstractmethod
    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        temperature: float = 0.0,
        seed: int | None = None,
    ) -> T: ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...


def _log_request(
    provider: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    response: Any,
    log_dir: str | Path = "outputs/llm_logs",
) -> None:
    log_dir_path = Path(log_dir)
    log_dir_path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
    log_file = log_dir_path / f"{provider}_{model}_{timestamp}.json"
    entry = {
        "provider": provider,
        "model": model,
        "timestamp": timestamp,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "response": response.model_dump(mode="json")
        if isinstance(response, BaseModel)
        else response,
    }
    log_file.write_text(
        json.dumps(entry, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


_PROMPTS_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "PIPELINE_PROMPTS.md"
_PROMPTS_CACHE: dict[str, str] | None = None


def _load_prompt_section(section_key: str) -> str:
    global _PROMPTS_CACHE
    if _PROMPTS_CACHE is None:
        raw = _PROMPTS_PATH.read_text(encoding="utf-8")
        sections: dict[str, str] = {}
        current_key = "header"
        current_lines: list[str] = []
        for line in raw.splitlines():
            if line.startswith("## "):
                if current_lines:
                    sections[current_key] = "\n".join(current_lines).strip()
                current_key = line.removeprefix("## ").strip().lower()
                current_lines = []
            else:
                current_lines.append(line)
        if current_lines:
            sections[current_key] = "\n".join(current_lines).strip()
        _PROMPTS_CACHE = sections
    return _PROMPTS_CACHE.get(section_key, "")


def _unit_context(unit: SourceUnit) -> str:
    lesson_line = (
        f"Lesson number: {unit.lesson_number}\n" if unit.lesson_number is not None else ""
    )
    return (
        f"Unit ref: {unit.unit_ref}\n"
        f"Sequence index: {unit.sequence_index}\n"
        f"Unit type: {unit.unit_type.value}\n"
        f"{lesson_line}"
        f"Title: {unit.title}\n"
        f"Content type: {unit.lesson_type.value}\n"
    )


def _identity_from_prompt(user_prompt: str) -> tuple[str, int, int | None]:
    unit_match = re.search(r"Unit ref:\s*([^\s]+)", user_prompt)
    seq_match = re.search(r"Sequence index:\s*(\d+)", user_prompt)
    lesson_match = re.search(r"Lesson number:\s*(\d+)", user_prompt)
    if lesson_match is None:
        lesson_match = re.search(r"Lesson\s+(\d+)", user_prompt)
    lesson_number = int(lesson_match.group(1)) if lesson_match else None
    unit_ref = unit_match.group(1) if unit_match else (f"L{lesson_number}" if lesson_number else "L116")
    sequence_index = int(seq_match.group(1)) if seq_match else (lesson_number or 116)
    return unit_ref, sequence_index, lesson_number


class MockLLMProvider(LLMProvider):
    def __init__(self, model: str = "mock-0.1.0") -> None:
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        temperature: float = 0.0,
        seed: int | None = None,
    ) -> T:
        if response_model is LessonAnalysisProfile:
            return self._mock_analysis(user_prompt)
        if response_model is CompatibilityScoreBatch:
            return CompatibilityScoreBatch(self._mock_scores(user_prompt))
        if response_model is LyricPlan:
            return self._mock_plan(user_prompt)
        if response_model is StyleAdaptation:
            return self._mock_adaptation(user_prompt)
        if response_model is GeneratedLyricsResponse:
            return GeneratedLyricsResponse(self._mock_lyrics(user_prompt))
        if response_model is SongArchetypeSelection:
            return SongArchetypeSelection(archetype=SongArchetype.TITLE_TEACHING_PRAYER)
        msg = f"MockLLMProvider does not support response_model={response_model.__name__}"
        raise ValueError(msg)

    def _mock_analysis(self, user_prompt: str) -> LessonAnalysisProfile:
        unit_ref, sequence_index, lesson_number = _identity_from_prompt(user_prompt)
        lesson_type = "text_section" if "Unit type: text_section" in user_prompt else "standard"
        return LessonAnalysisProfile(
            unit_ref=unit_ref,
            sequence_index=sequence_index,
            lesson_number=lesson_number,
            lesson_type=lesson_type,
            themes=["forgiveness", "peace"],
            emotional_start="confusion",
            emotional_destination="clarity",
            energy_target=0.5,
            lyric_density="medium",
            repetition_affinity=0.5,
            spoken_word_need=0.4,
            clarity_requirement=0.6,
            preferred_arc="build_up",
            suitable_traits=["warm", "clear vocal"],
            unsuitable_traits=["aggressive", "distorted"],
            ranked_archetypes=[SongArchetype.TITLE_TEACHING_PRAYER],
            analyzed_source_hash="mock_hash",
            analysis_version="0.1.0",
        )

    def _mock_scores(self, user_prompt: str) -> list[CompatibilityScore]:
        unit_ref, sequence_index, lesson_number = _identity_from_prompt(user_prompt)
        style_ids = re.findall(r"style_id=([^\s,]+)", user_prompt)
        styles_found = sorted(set(style_ids))

        scores = []
        for si, style_id in enumerate(styles_found):
            score = min(10.0, max(0.0, 7.0 + (si % 3) * 0.5 - (sequence_index % 5) * 0.2))
            scores.append(
                CompatibilityScore(
                    unit_ref=unit_ref,
                    sequence_index=sequence_index,
                    lesson_number=lesson_number,
                    style_id=style_id,
                    total=round(score, 1),
                    dimensions={
                        "theme": round(score, 1),
                        "energy": 6.0,
                        "density": 7.0,
                        "repetition": 5.0,
                        "clarity": 6.5,
                        "arc": 7.0,
                        "form": 6.0,
                    },
                )
            )
        return scores

    def _mock_plan(self, user_prompt: str) -> LyricPlan:
        unit_ref, sequence_index, lesson_number = _identity_from_prompt(user_prompt)
        sentence_ids = re.findall(r"^\s+([^\s]+) \[[^\]]+\]:", user_prompt, re.MULTILINE)
        first = sentence_ids[0] if sentence_ids else f"{unit_ref}.title"
        teaching = sentence_ids[1:3] or [first]
        return LyricPlan(
            unit_ref=unit_ref,
            sequence_index=sequence_index,
            lesson_number=lesson_number,
            archetype=SongArchetype.TITLE_TEACHING_PRAYER,
            sections=[
                PlanSection(
                    label="Intro",
                    function="setting",
                    source_sentence_ids=[first],
                    treatment="instrumental",
                ),
                PlanSection(
                    label="Verse 1",
                    function="teaching",
                    source_sentence_ids=teaching,
                    treatment="sung",
                    repetition_count=1,
                ),
                PlanSection(
                    label="Chorus",
                    function="title_mantra",
                    source_sentence_ids=[first],
                    treatment="sung",
                    repetition_count=3,
                ),
                PlanSection(
                    label="Outro",
                    function="resolution",
                    source_sentence_ids=[first],
                    treatment="sung",
                    repetition_count=2,
                ),
            ],
            total_word_count=200,
            spoken_word_count=0,
        )

    def _mock_adaptation(self, user_prompt: str) -> StyleAdaptation:
        unit_ref, sequence_index, lesson_number = _identity_from_prompt(user_prompt)
        style_match = re.search(r"style_id=([^\s,]+)|Style:\s*([^\s]+)", user_prompt)
        style_id = next((group for group in style_match.groups() if group), "STYLE_1") if style_match else "STYLE_1"
        core_match = re.search(r"Core prompt:\s*(.+)", user_prompt)
        core_prompt = core_match.group(1).strip() if core_match else "Warm acoustic folk."
        adaptation = "Set the tempo to 85 BPM. Emphasize vocal intimacy and clear diction."
        return StyleAdaptation(
            unit_ref=unit_ref,
            sequence_index=sequence_index,
            lesson_number=lesson_number,
            style_id=style_id,
            core_prompt=core_prompt,
            adaptation=adaptation,
            final_prompt=f"{core_prompt} {adaptation}",
            bpm=85,
            core_identity_preserved=True,
        )

    def _mock_lyrics(self, user_prompt: str) -> list[GeneratedLyric]:
        sentences_section = (
            user_prompt.split("Source sentences:")[-1].strip()
            if "Source sentences:" in user_prompt
            else ""
        )
        lines = [line.strip() for line in sentences_section.split("\n") if line.strip() and ":" in line]
        source_lines = [line.split(":", 1)[1].strip() for line in lines]
        if not source_lines:
            source_lines = ["For morning and evening review."]
        first = source_lines[0]
        second = source_lines[1] if len(source_lines) > 1 else first
        return [
            GeneratedLyric(section_label="Intro", text="(Soft instrumental)"),
            GeneratedLyric(section_label="Verse 1", text=second),
            GeneratedLyric(section_label="Chorus", text=first),
            GeneratedLyric(section_label="Outro", text=first),
        ]


class GeminiLLMProvider(LLMProvider):
    def __init__(self, model: str = "gemini-2.0-flash") -> None:
        self._model = model
        self._client = None

    @property
    def model_name(self) -> str:
        return self._model

    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        temperature: float = 0.0,
        seed: int | None = None,
    ) -> T:
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise ImportError("Install google-genai for Gemini support")

        if self._client is None:
            self._client = genai.Client()

        response = self._client.models.generate_content(
            model=self._model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=temperature,
                seed=seed,
                response_mime_type="application/json",
                response_schema=response_model,
            ),
        )
        result = response_model.model_validate_json(response.text)
        _log_request("gemini", self._model, system_prompt, user_prompt, result)
        return result


class OpenAILLMProvider(LLMProvider):
    def __init__(self, model: str = "gpt-4o") -> None:
        self._model = model
        self._client = None

    @property
    def model_name(self) -> str:
        return self._model

    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        temperature: float = 0.0,
        seed: int | None = None,
    ) -> T:
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("Install openai for OpenAI support")

        if self._client is None:
            self._client = OpenAI()

        response = self._client.beta.chat.completions.parse(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format=response_model,
            temperature=temperature,
            seed=seed,
        )
        result = response.choices[0].message.parsed
        _log_request("openai", self._model, system_prompt, user_prompt, result)
        return result


def create_llm_provider(
    provider: str = "mock",
    model: str | None = None,
) -> LLMProvider:
    if provider == "mock":
        return MockLLMProvider(model or "mock-0.1.0")
    if provider == "gemini":
        return GeminiLLMProvider(model or "gemini-2.0-flash")
    if provider == "openai":
        return OpenAILLMProvider(model or "gpt-4o")
    raise ValueError(f"Unknown provider: {provider}")


def analyze_lesson(
    lesson: SourceUnit,
    llm: LLMProvider,
    prompt_version: str = "0.1.0",
) -> LessonAnalysisProfile:
    system_prompt = _load_prompt_section("lesson analyzer")
    user_prompt = (
        "Analyze the following approved ACIM source unit.\n\n"
        f"{_unit_context(lesson)}\n"
        f"Source text:\n{lesson.source_text}\n"
    )
    result = llm.generate_structured(system_prompt, user_prompt, LessonAnalysisProfile)
    return result.model_copy(
        update={
            "unit_ref": lesson.unit_ref,
            "sequence_index": lesson.sequence_index,
            "lesson_number": lesson.lesson_number,
            "language": lesson.language,
            "lesson_type": lesson.lesson_type,
            "analyzed_source_hash": lesson.source.source_hash,
        }
    )


analyze_unit = analyze_lesson


def score_compatibility(
    lesson: SourceUnit,
    styles: list[StyleRecord],
    llm: LLMProvider,
    prompt_version: str = "0.1.0",
) -> list[CompatibilityScore]:
    system_prompt = _load_prompt_section("compatibility scorer")
    styles_info = "\n".join(
        f"style_id={style.style_id}, name={style.name}, bucket={style.primary_bucket}, "
        f"energy={style.energy}, density={style.lyric_density}, prompt={style.core_prompt[:100]}"
        for style in styles
    )
    user_prompt = f"{_unit_context(lesson)}\nAvailable styles:\n{styles_info}\n"
    response = llm.generate_structured(system_prompt, user_prompt, CompatibilityScoreBatch)
    return [
        score.model_copy(
            update={
                "unit_ref": lesson.unit_ref,
                "sequence_index": lesson.sequence_index,
                "lesson_number": lesson.lesson_number,
                "language": lesson.language,
            }
        )
        for score in response.root
    ]


def select_archetype(
    lesson: SourceUnit,
    profile: LessonAnalysisProfile,
    llm: LLMProvider,
    prompt_version: str = "0.1.0",
) -> SongArchetype:
    system_prompt = _load_prompt_section("archetype selector")
    ineligible = [SongArchetype.PAIRED_REVIEW.value] if lesson.unit_type == UnitType.TEXT_SECTION else []
    user_prompt = (
        f"{_unit_context(lesson)}"
        f"Themes: {', '.join(profile.themes)}\n"
        f"Ranked archetypes: {[archetype.value for archetype in profile.ranked_archetypes]}\n"
        f"Ineligible archetypes: {ineligible}\n"
        f"Number of paragraphs: {len(lesson.paragraphs)}\n"
    )
    response = llm.generate_structured(system_prompt, user_prompt, SongArchetypeSelection)
    if lesson.unit_type == UnitType.TEXT_SECTION and response.archetype == SongArchetype.PAIRED_REVIEW:
        return SongArchetype.DECLARATION_DEVELOPMENT
    return response.archetype


def plan_lyrics(
    lesson: SourceUnit,
    archetype: SongArchetype,
    llm: LLMProvider,
    prompt_version: str = "0.1.0",
) -> LyricPlan:
    system_prompt = _load_prompt_section("lyric planner")
    coverage_note = (
        "For a Text section, cover the teaching arc across opening/setup, central teaching, "
        "turning point or contrast, and resolution when the source supports those roles.\n"
        if lesson.unit_type == UnitType.TEXT_SECTION
        else ""
    )
    user_prompt = (
        "Create a lyric plan for this approved ACIM source unit.\n"
        f"{_unit_context(lesson)}"
        f"Archetype: {archetype.value}\n"
        f"{coverage_note}\n"
        f"Source text:\n{lesson.source_text}\n\n"
        "Sentences:\n"
        + "\n".join(
            f"  {sentence.sentence_id} [{sentence.category}]: {sentence.text[:120]}"
            for sentence in lesson.sentences
        )
        + "\n"
    )
    result = llm.generate_structured(system_prompt, user_prompt, LyricPlan)
    return result.model_copy(
        update={
            "unit_ref": lesson.unit_ref,
            "sequence_index": lesson.sequence_index,
            "lesson_number": lesson.lesson_number,
            "language": lesson.language,
            "archetype": archetype,
        }
    )


def adapt_style(
    lesson: SourceUnit,
    style: StyleRecord,
    plan: LyricPlan,
    llm: LLMProvider,
    prompt_version: str = "0.1.0",
) -> StyleAdaptation:
    system_prompt = _load_prompt_section("bounded style adapter")
    user_prompt = (
        f"{_unit_context(lesson)}"
        f"Style: {style.style_id}\n"
        f"Style name: {style.name}\n\n"
        f"Core prompt: {style.core_prompt}\n"
        f"Primary bucket: {style.primary_bucket}\n"
        f"Tempo range: {style.tempo_min}-{style.tempo_max} BPM\n"
        f"Energy: {style.energy}\n"
        f"Density: {style.lyric_density}\n"
        f"Locked traits: {style.locked_traits}\n"
        f"Mutable traits: {style.mutable_traits}\n\n"
        f"Archetype: {plan.archetype.value}\n"
    )
    result = llm.generate_structured(system_prompt, user_prompt, StyleAdaptation)
    return result.model_copy(
        update={
            "unit_ref": lesson.unit_ref,
            "sequence_index": lesson.sequence_index,
            "lesson_number": lesson.lesson_number,
            "style_id": style.style_id,
        }
    )


def generate_lyrics(
    lesson: SourceUnit,
    plan: LyricPlan,
    adaptation: StyleAdaptation,
    llm: LLMProvider,
    prompt_version: str = "0.1.0",
) -> list[GeneratedLyric]:
    system_prompt = _load_prompt_section("lyric writer")
    user_prompt = (
        "Generate verbatim-only lyrics for this approved ACIM source unit.\n\n"
        f"{_unit_context(lesson)}"
        f"Archetype: {plan.archetype.value}\n"
        f"Style: {adaptation.final_prompt}\n\n"
        "Plan:\n"
        + "\n".join(
            f"  [{section.label}] {section.function} - {section.treatment} "
            f"x{section.repetition_count} - source IDs: {section.source_sentence_ids}"
            for section in plan.sections
        )
        + "\n\nSource sentences:\n"
        + "\n".join(f"  {sentence.sentence_id}: {sentence.text}" for sentence in lesson.sentences)
        + "\n\nProduce lyrics with conservative [Section] headers only."
    )
    response = llm.generate_structured(system_prompt, user_prompt, GeneratedLyricsResponse)
    return response.root
