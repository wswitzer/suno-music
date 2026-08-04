from __future__ import annotations

import json
import logging
import os
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
    LessonRecord,
    LyricPlan,
    PlanSection,
    SongArchetype,
    SongArchetypeSelection,
    StyleAdaptation,
    StyleRecord,
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
        return LessonAnalysisProfile(
            lesson_number=116,
            lesson_type="standard",
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
        import re

        lesson_match = re.search(r"Lesson\s+(\d+):", user_prompt)
        lesson_number = int(lesson_match.group(1)) if lesson_match else 116
        style_ids = re.findall(r"style_id=([^\s,]+)", user_prompt)
        styles_found = sorted(set(style_ids))

        scores = []
        for si, sid in enumerate(styles_found):
            score = min(10.0, max(0.0, 7.0 + (si % 3) * 0.5 - (lesson_number % 5) * 0.2))
            scores.append(
                CompatibilityScore(
                    lesson_number=lesson_number,
                    style_id=sid,
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
        import re

        lesson_match = re.search(r"Lesson\s+(\d+):", user_prompt)
        lesson_number = int(lesson_match.group(1)) if lesson_match else 116
        return LyricPlan(
            lesson_number=lesson_number,
            archetype=SongArchetype.TITLE_TEACHING_PRAYER,
            sections=[
                PlanSection(
                    label="Intro",
                    function="setting",
                    source_sentence_ids=["L116_001"],
                    treatment="instrumental",
                ),
                PlanSection(
                    label="Verse 1",
                    function="teaching",
                    source_sentence_ids=["L116_002", "L116_003"],
                    treatment="sung",
                    repetition_count=1,
                ),
                PlanSection(
                    label="Chorus",
                    function="title_mantra",
                    source_sentence_ids=["L116_001"],
                    treatment="sung",
                    repetition_count=3,
                ),
                PlanSection(
                    label="Bridge - Guided Practice",
                    function="practice",
                    source_sentence_ids=["L116_010"],
                    treatment="spoken",
                    repetition_count=1,
                ),
                PlanSection(
                    label="Outro",
                    function="resolution",
                    source_sentence_ids=["L116_001"],
                    treatment="sung",
                    repetition_count=2,
                ),
            ],
            total_word_count=200,
            spoken_word_count=50,
        )

    def _mock_adaptation(self, user_prompt: str) -> StyleAdaptation:
        import re

        lesson_match = re.search(r"for Lesson\s+(\d+)|lesson_number=(\d+)", user_prompt)
        lesson_number = int(lesson_match.group(1) or lesson_match.group(2)) if lesson_match else 116
        style_match = re.search(r"style_id=([^\s,]+)|STYLE_\d+", user_prompt)
        style_id = style_match.group(1) or style_match.group(0) if style_match else "STYLE_1"
        return StyleAdaptation(
            style_id=style_id,
            lesson_number=lesson_number,
            core_prompt="Warm acoustic folk.",
            adaptation="Set the tempo to 85 BPM. Emphasize vocal intimacy, gentle choir, and a build-up arrangement.",
            final_prompt="Warm acoustic folk. Set the tempo to 85 BPM. Emphasize vocal intimacy, gentle choir, and a build-up arrangement.",
            bpm=85,
            core_identity_preserved=True,
        )

    def _mock_lyrics(self, user_prompt: str) -> list[GeneratedLyric]:
        import re

        lesson_match = re.search(r"Lesson\s+(\d+):", user_prompt)
        int(lesson_match.group(1)) if lesson_match else 116
        source_text = user_prompt
        sentences_section = (
            source_text.split("Source sentences:")[-1].strip()
            if "Source sentences:" in source_text
            else ""
        )
        lines = [l.strip() for l in sentences_section.split("\n") if l.strip() and ":" in l]
        sung_lines = (
            [l.split(":", 1)[1].strip() for l in lines[:3]]
            if len(lines) >= 3
            else ["For morning and evening review."]
        )
        spoken_lines = (
            [l.split(":", 1)[1].strip() for l in lines[3:6]]
            if len(lines) >= 6
            else ["On the hour:"]
        )
        return [
            GeneratedLyric(section_label="Intro", text="(Soft instrumental)"),
            GeneratedLyric(
                section_label="Verse 1",
                text=sung_lines[0] if len(sung_lines) > 0 else "This is the day of peace.",
            ),
            GeneratedLyric(
                section_label="Chorus", text=sung_lines[1] if len(sung_lines) > 1 else sung_lines[0]
            ),
            GeneratedLyric(
                section_label="Bridge - Guided Practice",
                text=f"(Spoken) {spoken_lines[0]}" if spoken_lines else "(Spoken) Let us review.",
            ),
            GeneratedLyric(section_label="Outro", text=sung_lines[-1]),
        ]


class GeminiLLMProvider(LLMProvider):
    def __init__(
        self,
        model: str = "gemini-3.1-pro-preview",
        *,
        project: str | None = None,
        location: str | None = None,
    ) -> None:
        self._model = model
        self._project = project or os.environ.get("GOOGLE_CLOUD_PROJECT")
        self._location = location or os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
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
            from google.genai import Client, types
        except ImportError:
            raise ImportError("Install google-genai for Gemini Vertex AI support")

        if self._client is None:
            if not self._project:
                raise ValueError("GOOGLE_CLOUD_PROJECT is required for Gemini Vertex AI access")
            self._client = Client(
                vertexai=True,
                project=self._project,
                location=self._location,
            )

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
        return GeminiLLMProvider(model or "gemini-3.1-pro-preview")
    if provider == "openai":
        return OpenAILLMProvider(model or "gpt-4o")
    raise ValueError(f"Unknown provider: {provider}")


# Stage -> default model policy. The A/B studies showed creative leverage is
# concentrated in lyric planning (use the stronger model there), while Flash
# executes analysis/scoring/adaptation/writing/repair efficiently. `--model`
# on any command overrides its stage default; nothing here forces a global model.
STAGE_MODEL_DEFAULTS: dict[str, str] = {
    "analysis": "gemini-3.6-flash",
    "compatibility": "gemini-3.6-flash",
    "planning": "gemini-3.1-pro-preview",
    "style_adaptation": "gemini-3.6-flash",
    "lyric_writing": "gemini-3.6-flash",
    "repair": "gemini-3.6-flash",
}


def create_stage_provider(
    provider: str,
    stage: str,
    model: str | None = None,
    prompt_version: str = "0.1.0",
) -> LLMProvider:
    """Build an LLMProvider bound to the model policy for `stage`.

    `model` (passed from a `--model` flag) overrides the stage default; otherwise
    the stage-specific default from STAGE_MODEL_DEFAULTS is used. Because the
    provider's model_name flows into cache keys and request logs, a Pro-produced
    upstream artifact can never be silently reused as a Flash one or vice versa.
    """
    if model is not None:
        return create_llm_provider(provider, model)
    return create_llm_provider(provider, STAGE_MODEL_DEFAULTS.get(stage))


def analyze_lesson(
    lesson: LessonRecord,
    llm: LLMProvider,
    prompt_version: str = "0.1.0",
) -> LessonAnalysisProfile:
    system_prompt = _load_prompt_section("lesson analyzer")
    user_prompt = (
        f"Analyze the following ACIM Workbook lesson {lesson.lesson_number}:\n\n"
        f"Title: {lesson.title}\n\n"
        f"Source text:\n{lesson.source_text}\n\n"
        f"Lesson type: {lesson.lesson_type.value}\n"
    )
    result = llm.generate_structured(system_prompt, user_prompt, LessonAnalysisProfile)
    return result.model_copy(
        update={
            "lesson_number": lesson.lesson_number,
            "language": lesson.language,
            "lesson_type": lesson.lesson_type,
            "analyzed_source_hash": lesson.source.source_hash,
            "analysis_version": prompt_version,
        }
    )


def score_compatibility(
    lesson: LessonRecord,
    styles: list[StyleRecord],
    llm: LLMProvider,
    prompt_version: str = "0.1.0",
    max_attempts: int = 3,
    profile: LessonAnalysisProfile | None = None,
) -> list[CompatibilityScore]:
    from collections import Counter

    system_prompt = _load_prompt_section("compatibility scorer")
    expected_ids = {style.style_id for style in styles}
    if len(expected_ids) != len(styles):
        raise ValueError("Style registry contains duplicate style IDs")

    profile_info = "No lesson-analysis profile supplied."
    if profile is not None:
        profile_info = (
            f"Themes: {', '.join(profile.themes) or 'none'}\n"
            f"Emotional arc: {profile.emotional_start} -> "
            f"{profile.emotional_destination}\n"
            f"Energy target: {profile.energy_target}\n"
            f"Lyric density: {profile.lyric_density}\n"
            f"Repetition affinity: {profile.repetition_affinity}\n"
            f"Spoken-word need: {profile.spoken_word_need}\n"
            f"Clarity requirement: {profile.clarity_requirement}\n"
            f"Preferred arc: {profile.preferred_arc}\n"
            f"Suitable traits: {profile.suitable_traits}\n"
            f"Unsuitable traits: {profile.unsuitable_traits}"
        )

    lesson_info = (
        f"Lesson {lesson.lesson_number}:\n"
        f"Title: {lesson.title}\n"
        f"Type: {lesson.lesson_type.value}\n"
        f"Language: {lesson.language}\n"
        f"Lesson analysis:\n{profile_info}\n"
        f"Source excerpt:\n{lesson.source_text[:2500]}\n"
    )
    styles_info = "\n".join(
        f"style_id={style.style_id}, name={style.name}, "
        f"bucket={style.primary_bucket}, energy={style.energy}, "
        f"density={style.lyric_density}, prompt={style.core_prompt[:100]}"
        for style in styles
    )
    user_prompt = (
        f"{lesson_info}\nAvailable styles ({len(styles)} total):\n{styles_info}\n"
        f"\nReturn exactly {len(styles)} score records, one per style_id listed above. "
        "Do not add unknown IDs or duplicate IDs."
    )

    last_error: str | None = None
    for attempt in range(1, max_attempts + 1):
        response = llm.generate_structured(system_prompt, user_prompt, CompatibilityScoreBatch)
        scores = [
            score.model_copy(
                update={
                    "lesson_number": lesson.lesson_number,
                    "language": lesson.language,
                }
            )
            for score in response.root
        ]
        counts = Counter(score.style_id for score in scores)
        returned_ids = set(counts)
        missing = sorted(expected_ids - returned_ids)
        unexpected = sorted(returned_ids - expected_ids)
        duplicates = sorted(style_id for style_id, count in counts.items() if count != 1)
        valid = len(scores) == len(styles) and returned_ids == expected_ids and not duplicates
        if valid:
            return scores

        details: list[str] = []
        if len(scores) != len(styles):
            details.append(f"count {len(scores)} != {len(styles)}")
        if missing:
            details.append(f"missing: {', '.join(missing[:5])}")
        if unexpected:
            details.append(f"unexpected: {', '.join(unexpected[:5])}")
        if duplicates:
            details.append(f"duplicates: {', '.join(duplicates[:5])}")
        last_error = "; ".join(details) or "invalid score batch"
        logger.warning(
            "Compatibility score batch invalid (attempt %d/%d): %s",
            attempt,
            max_attempts,
            last_error,
        )
        if attempt < max_attempts:
            user_prompt += (
                f"\n\nPrevious attempt was invalid: {last_error}. "
                f"Return exactly one record for every one of the {len(styles)} expected IDs."
            )

    raise ValueError(
        f"Compatibility scoring failed for lesson {lesson.lesson_number} after "
        f"{max_attempts} attempts: {last_error}"
    )


def select_archetype(
    lesson: LessonRecord,
    profile: LessonAnalysisProfile,
    llm: LLMProvider,
    prompt_version: str = "0.1.0",
) -> SongArchetype:
    system_prompt = _load_prompt_section("archetype selector")
    user_prompt = (
        f"Lesson {lesson.lesson_number}: {lesson.title}\n"
        f"Type: {lesson.lesson_type.value}\n"
        f"Themes: {', '.join(profile.themes)}\n"
        f"Ranked archetypes: {[a.value for a in profile.ranked_archetypes]}\n"
        f"Number of paragraphs: {len(lesson.paragraphs)}\n"
    )
    response = llm.generate_structured(system_prompt, user_prompt, SongArchetypeSelection)
    return response.archetype


def plan_lyrics(
    lesson: LessonRecord,
    archetype: SongArchetype,
    llm: LLMProvider,
    prompt_version: str = "0.1.0",
) -> LyricPlan:
    system_prompt = _load_prompt_section("lyric planner")
    user_prompt = (
        f"Create a lyric plan for Lesson {lesson.lesson_number}: {lesson.title}\n"
        f"Archetype: {archetype.value}\n"
        f"Lesson type: {lesson.lesson_type.value}\n\n"
        f"Source text:\n{lesson.source_text}\n\n"
        f"Sentences:\n"
        + "\n".join(f"  {s.sentence_id} [{s.category}]: {s.text[:120]}" for s in lesson.sentences)
        + "\n"
    )
    result = llm.generate_structured(system_prompt, user_prompt, LyricPlan)
    return result.model_copy(
        update={
            "lesson_number": lesson.lesson_number,
            "language": lesson.language,
            "archetype": archetype,
        }
    )


def adapt_style(
    lesson: LessonRecord,
    style: StyleRecord,
    plan: LyricPlan,
    llm: LLMProvider,
    prompt_version: str = "0.1.0",
) -> StyleAdaptation:
    system_prompt = _load_prompt_section("bounded style adapter")
    user_prompt = (
        f"Adapt style {style.style_id} ({style.name}) for Lesson {lesson.lesson_number}.\n\n"
        f"Core prompt: {style.core_prompt}\n"
        f"Primary bucket: {style.primary_bucket}\n"
        f"Tempo range: {style.tempo_min}-{style.tempo_max} BPM\n"
        f"Energy: {style.energy}\n"
        f"Density: {style.lyric_density}\n"
        f"Locked traits: {style.locked_traits}\n"
        f"Mutable traits: {style.mutable_traits}\n\n"
        f"Lesson: {lesson.title}\n"
        f"Archetype: {plan.archetype.value}\n"
    )
    return llm.generate_structured(system_prompt, user_prompt, StyleAdaptation)


def generate_lyrics(
    lesson: LessonRecord,
    plan: LyricPlan,
    adaptation: StyleAdaptation,
    llm: LLMProvider,
    prompt_version: str = "0.1.0",
) -> list[GeneratedLyric]:
    system_prompt = _load_prompt_section("lyric writer")
    user_prompt = (
        f"Generate verbatim-only lyrics for Lesson {lesson.lesson_number}: {lesson.title}\n\n"
        f"Archetype: {plan.archetype.value}\n"
        f"Style: {adaptation.final_prompt}\n\n"
        f"Plan:\n"
        + "\n".join(
            f"  [{s.label}] {s.function} - {s.treatment} x{s.repetition_count} - "
            f"source IDs: {s.source_sentence_ids}"
            for s in plan.sections
        )
        + "\n\nSource sentences follow. The L###_### tokens are metadata labels only; "
        "never output them as lyrics.\n"
        + "\n".join(f"  {s.sentence_id}: {s.text}" for s in lesson.sentences)
        + (
            "\n\nProduce lyrics with [Section] headers. Exact contiguous source phrases may "
            "be repeated, reordered, and interleaved as separate lyric lines or sections, "
            "but never splice noncontiguous source spans into one new lyric phrase. "
            "Never emit source IDs, workbook references (such as W-pI.*), paragraph/sentence "
            "numbers, or editorial metadata unless those characters are themselves part of "
            "the approved clean source text. Treatment markers such as (Spoken) or (Sung) "
            "are metadata, not lyric content."
        )
    )
    response = llm.generate_structured(system_prompt, user_prompt, GeneratedLyricsResponse)
    return response.root
