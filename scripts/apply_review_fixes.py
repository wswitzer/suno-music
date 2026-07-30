from __future__ import annotations

from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def patch_models() -> None:
    path = "src/acim_suno/models.py"
    text = read(path)
    text = replace_once(
        text,
        "from pydantic import BaseModel, ConfigDict, Field, model_validator",
        "from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator",
        "models import",
    )
    anchor = '''class CompatibilityScore(StrictModel):
    lesson_number: int
    language: str = "en"
    style_id: str
    total: float = Field(ge=0, le=10)
    dimensions: dict[str, float] = Field(default_factory=dict)
    reason: str | None = None
    risks: list[str] = Field(default_factory=list)
'''
    replacement = anchor + '''

class CompatibilityScoreBatch(RootModel[list[CompatibilityScore]]):
    """Structured-output wrapper for one lesson's style scores."""


class SongArchetypeSelection(StrictModel):
    """Structured-output wrapper for an archetype enum."""

    archetype: SongArchetype
'''
    text = replace_once(text, anchor, replacement, "score response wrappers")
    text = replace_once(
        text,
        '''class LyricPlan(StrictModel):
    lesson_number: int
    archetype: SongArchetype
''',
        '''class LyricPlan(StrictModel):
    lesson_number: int
    language: str = "en"
    archetype: SongArchetype
''',
        "lyric plan language",
    )
    anchor = '''class GeneratedLyric(StrictModel):
    section_label: str
    text: str
'''
    replacement = anchor + '''

class GeneratedLyricsResponse(RootModel[list[GeneratedLyric]]):
    """Structured-output wrapper for generated lyric sections."""
'''
    text = replace_once(text, anchor, replacement, "generated lyrics response wrapper")
    write(path, text)


def patch_llm() -> None:
    path = "src/acim_suno/llm.py"
    text = read(path)
    text = text.replace("from typing import Any, Generic, TypeVar", "from typing import Any, TypeVar")
    text = text.replace("\nimport yaml\n", "\n")
    text = replace_once(
        text,
        "    CompatibilityScore,\n",
        "    CompatibilityScore,\n    CompatibilityScoreBatch,\n",
        "score wrapper import",
    )
    text = replace_once(
        text,
        "    GeneratedLyric,\n",
        "    GeneratedLyric,\n    GeneratedLyricsResponse,\n",
        "lyrics wrapper import",
    )
    text = replace_once(
        text,
        "    SongArchetype,\n",
        "    SongArchetype,\n    SongArchetypeSelection,\n",
        "archetype wrapper import",
    )
    text = replace_once(
        text,
        '''        if response_model == list[CompatibilityScore]:
            return self._mock_scores(user_prompt)
''',
        '''        if response_model is CompatibilityScoreBatch:
            return CompatibilityScoreBatch(self._mock_scores(user_prompt))
''',
        "mock score wrapper",
    )
    text = replace_once(
        text,
        '''        if response_model == list[GeneratedLyric]:
            return self._mock_lyrics(user_prompt)
        msg = f"MockLLMProvider does not support response_model={response_model.__name__}"
''',
        '''        if response_model is GeneratedLyricsResponse:
            return GeneratedLyricsResponse(self._mock_lyrics(user_prompt))
        if response_model is SongArchetypeSelection:
            return SongArchetypeSelection(
                archetype=SongArchetype.TITLE_TEACHING_PRAYER
            )
        msg = f"MockLLMProvider does not support response_model={response_model.__name__}"
''',
        "mock lyric and archetype wrappers",
    )
    text = replace_once(
        text,
        '''        schema_dict = _pydantic_to_genai_schema(response_model)
        response = self._client.models.generate_content(
            model=self._model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=temperature,
                seed=seed,
                response_mime_type="application/json",
                response_schema=schema_dict,
            ),
        )
        result = response_model.model_validate(json.loads(response.text))
''',
        '''        response = self._client.models.generate_content(
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
''',
        "Gemini structured output",
    )
    start = text.index("\ndef _pydantic_to_genai_schema(")
    end = text.index("\ndef create_llm_provider(", start)
    text = text[:start] + "\n" + text[end:]
    text = replace_once(
        text,
        "    return llm.generate_structured(system_prompt, user_prompt, list[CompatibilityScore])",
        '''    response = llm.generate_structured(
        system_prompt, user_prompt, CompatibilityScoreBatch
    )
    return response.root''',
        "compatibility response",
    )
    text = replace_once(
        text,
        "    return llm.generate_structured(system_prompt, user_prompt, SongArchetype)",
        '''    response = llm.generate_structured(
        system_prompt, user_prompt, SongArchetypeSelection
    )
    return response.archetype''',
        "archetype response",
    )
    text = replace_once(
        text,
        '''        f"Lesson type: {lesson.lesson_type.value}\n\n"
        f"Source text:\n{lesson.source_text}\n\n"
''',
        '''        f"Lesson type: {lesson.lesson_type.value}\n"
        f"Language: {lesson.language}\n\n"
        f"Source text:\n{lesson.source_text}\n\n"
''',
        "lyric plan language prompt",
    )
    text = replace_once(
        text,
        "    return llm.generate_structured(system_prompt, user_prompt, LyricPlan)",
        '''    result = llm.generate_structured(system_prompt, user_prompt, LyricPlan)
    return result.model_copy(
        update={
            "lesson_number": lesson.lesson_number,
            "language": lesson.language,
            "archetype": archetype,
        }
    )''',
        "lyric plan normalization",
    )
    text = replace_once(
        text,
        "    return llm.generate_structured(system_prompt, user_prompt, list[GeneratedLyric])",
        '''    response = llm.generate_structured(
        system_prompt, user_prompt, GeneratedLyricsResponse
    )
    return response.root''',
        "generated lyric response",
    )
    write(path, text)


def patch_validators() -> None:
    path = "src/acim_suno/validators.py"
    text = read(path)
    text = replace_once(
        text,
        'FULL_DIRECTION = re.compile(r"^\\s*\\([^)]*\\)\\s*$")',
        '''NON_LYRICAL_DIRECTION = re.compile(
    r"^\\s*\\((?:soft\\s+)?(?:instrumental(?:\\s+(?:intro|break|outro))?"
    r"|music\\s+(?:fades?|drops?|swells?)|fade\\s+(?:in|out))\\)\\s*$",
    re.IGNORECASE,
)''',
        "direction regex",
    )
    text = replace_once(
        text,
        "if not line or SECTION_LABEL.fullmatch(line) or FULL_DIRECTION.fullmatch(line):",
        '''if (
            not line
            or SECTION_LABEL.fullmatch(line)
            or NON_LYRICAL_DIRECTION.fullmatch(line)
        ):''',
        "direction validation",
    )
    write(path, text)


def patch_sources() -> None:
    path = "src/acim_suno/sources.py"
    text = read(path)
    text = replace_once(
        text,
        '''class ACIMJsonSourceProvider:
    def __init__(self, json_path: str | Path) -> None:
        self._path = Path(json_path)
        with self._path.open("r", encoding="utf-8") as f:
            self._data = json.load(f)
        self._source_hash = self._compute_hash()
''',
        '''class ACIMJsonSourceProvider:
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
                f"Source declares language {declared_language!r}, "
                f"not {source_language!r}"
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
''',
        "source language binding",
    )
    text = replace_once(
        text,
        '''    ) -> list[LessonRecord]:
        parts = self._data.get("parts", {})
''',
        '''    ) -> list[LessonRecord]:
        if language != self._source_language:
            raise ValueError(
                f"Source provider is bound to {self._source_language!r}; "
                f"requested {language!r}"
            )
        parts = self._data.get("parts", {})
''',
        "source language guard",
    )
    text = replace_once(
        text,
        '''def create_source_provider(
    source_type: str = "acim_json",
    json_path: str | Path = "/Users/trust/Projects/acim-core-data/workbook_enhanced.json",
) -> ACIMJsonSourceProvider:
    if source_type == "acim_json":
        return ACIMJsonSourceProvider(json_path)
''',
        '''def create_source_provider(
    source_type: str = "acim_json",
    json_path: str | Path = "/Users/trust/Projects/acim-core-data/workbook_enhanced.json",
    source_language: str = "en",
) -> ACIMJsonSourceProvider:
    if source_type == "acim_json":
        return ACIMJsonSourceProvider(json_path, source_language=source_language)
''',
        "source factory language",
    )
    write(path, text)


def patch_cli() -> None:
    path = "src/acim_suno/cli.py"
    text = read(path)
    text = replace_once(
        text,
        '''    plan_by_lesson = {(p.lesson_number, p.archetype): p for p in plans}
    adapt_by_lesson = {a.lesson_number: a for a in adaptations}
''',
        '''    plan_by_lesson = {(p.lesson_number, p.language): p for p in plans}
    adapt_by_lesson = {a.lesson_number: a for a in adaptations}
''',
        "plan lookup map",
    )
    text = replace_once(
        text,
        "        plan = plan_by_lesson.get((lesson.lesson_number, lesson.archetype))",
        "        plan = plan_by_lesson.get((lesson.lesson_number, lesson.language))",
        "plan lookup",
    )
    text = text.replace(
        "matching = [p for p in profiles if p.lesson_number == lesson.lesson_number]",
        '''matching = [
            p
            for p in profiles
            if p.lesson_number == lesson.lesson_number and p.language == lesson.language
        ]''',
    )
    text = text.replace(
        "plan_matches = [p for p in plans if p.lesson_number == lesson.lesson_number]",
        '''plan_matches = [
            p
            for p in plans
            if p.lesson_number == lesson.lesson_number and p.language == lesson.language
        ]''',
    )
    write(path, text)


def patch_tests() -> None:
    path = "tests/test_pipeline.py"
    text = read(path)
    text = text.replace(
        "from pathlib import Path\n",
        "from argparse import Namespace\nfrom pathlib import Path\n\nimport pytest\n",
        1,
    )
    text = text.replace(
        "from acim_suno.extract_styles import extract_styles_from_csv\n",
        '''from acim_suno.cli import command_generate_lyrics
from acim_suno.extract_styles import extract_styles_from_csv
from acim_suno.io import dump_json
from acim_suno.llm import MockLLMProvider, generate_lyrics, score_compatibility, select_archetype
''',
        1,
    )
    text = text.replace(
        "    LessonRecord,\n",
        '''    CompatibilityScoreBatch,
    GeneratedLyricsResponse,
    LessonAnalysisProfile,
    LessonRecord,
    LyricPlan,
    PlanSection,
    SongArchetype,
    SongArchetypeSelection,
''',
        1,
    )
    text = text.replace(
        "from acim_suno.optimizer import optimize_assignments\n",
        "from acim_suno.optimizer import optimize_assignments\nfrom acim_suno.sources import ACIMJsonSourceProvider\n",
        1,
    )
    text += r'''


def test_parenthesized_invented_adlib_is_rejected() -> None:
    report = validate_verbatim_lyrics("(Peace is within.)", "I am safe.")
    assert not report.passed
    assert report.issues[0].code == "non_verbatim_line"

    direction = validate_verbatim_lyrics("(Soft instrumental)\nI am safe.", "I am safe.")
    assert direction.passed


def test_provider_rejects_language_relabeling(tmp_path: Path) -> None:
    source_path = tmp_path / "workbook.json"
    source_path.write_text(
        '{"language":"en","parts":{"one":{"lessons":{}}}}',
        encoding="utf-8",
    )
    provider = ACIMJsonSourceProvider(source_path, source_language="en")
    with pytest.raises(ValueError, match="requested 'es'"):
        provider.fetch_lessons(116, 116, language="es")
    with pytest.raises(ValueError, match="Source declares language"):
        ACIMJsonSourceProvider(source_path, source_language="es")


def test_high_level_llm_calls_use_pydantic_wrappers() -> None:
    llm = MockLLMProvider()
    item = lesson(116)
    style = StyleRecord(
        style_id="STYLE_1",
        name="Demo",
        core_prompt="Warm acoustic folk.",
    )
    scores = score_compatibility(item, [style], llm)
    assert scores
    assert CompatibilityScoreBatch(scores).root == scores

    profile = LessonAnalysisProfile(
        lesson_number=116,
        lesson_type="standard",
        ranked_archetypes=[],
    )
    archetype = select_archetype(item, profile, llm)
    assert SongArchetypeSelection(archetype=archetype).archetype is archetype

    plan = LyricPlan(
        lesson_number=116,
        language="en",
        archetype=SongArchetype.TITLE_TEACHING_PRAYER,
        sections=[
            PlanSection(
                label="Chorus",
                function="title",
                source_sentence_ids=["title"],
            )
        ],
    )
    adaptation = StyleAdaptation(
        style_id="STYLE_1",
        lesson_number=116,
        core_prompt=style.core_prompt,
        adaptation="Gentle delivery.",
        final_prompt=f"{style.core_prompt} Gentle delivery.",
    )
    lyrics = generate_lyrics(item, plan, adaptation, llm)
    assert GeneratedLyricsResponse(lyrics).root == lyrics


def test_staged_generate_lyrics_command_uses_plan_language(tmp_path: Path) -> None:
    item = lesson(116)
    plan = LyricPlan(
        lesson_number=116,
        language="en",
        archetype=SongArchetype.TITLE_TEACHING_PRAYER,
        sections=[
            PlanSection(
                label="Chorus",
                function="title",
                source_sentence_ids=["title"],
            )
        ],
    )
    adaptation = StyleAdaptation(
        style_id="STYLE_1",
        lesson_number=116,
        core_prompt="Warm acoustic folk.",
        adaptation="Gentle delivery.",
        final_prompt="Warm acoustic folk. Gentle delivery.",
    )
    lessons_path = tmp_path / "lessons.json"
    plans_path = tmp_path / "plans.json"
    adaptations_path = tmp_path / "adaptations.json"
    output_path = tmp_path / "songs.json"
    dump_json(lessons_path, [item])
    dump_json(plans_path, [plan])
    dump_json(adaptations_path, [adaptation])

    result = command_generate_lyrics(
        Namespace(
            lessons=str(lessons_path),
            plans=str(plans_path),
            adaptations=str(adaptations_path),
            provider="mock",
            model=None,
            prompt_version="0.1.0",
            out=str(output_path),
        )
    )
    assert result == 0
    assert output_path.exists()
'''
    write(path, text)


def main() -> None:
    patch_models()
    patch_llm()
    patch_validators()
    patch_sources()
    patch_cli()
    patch_tests()


if __name__ == "__main__":
    main()
