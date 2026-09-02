from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UnitType(StrEnum):
    WORKBOOK_LESSON = "workbook_lesson"
    TEXT_SECTION = "text_section"


class LyricPolicy(StrEnum):
    VERBATIM_ONLY = "verbatim_only"
    VERBATIM_ANCHORS = "verbatim_anchors"
    PARAPHRASE_ALLOWED = "paraphrase_allowed"


class LessonType(StrEnum):
    STANDARD = "standard"
    REVIEW = "review"
    EXPERIENTIAL = "experiential"
    TEXT_SECTION = "text_section"


class SongArchetype(StrEnum):
    TITLE_TEACHING_PRAYER = "title_teaching_prayer"
    PAIRED_REVIEW = "paired_review"
    DECLARATION_DEVELOPMENT = "declaration_and_development"
    PRACTICE_MEDITATION = "practice_centered_meditation"
    SHORT_MANTRA = "short_mantra"
    LONG_TEACHING = "long_teaching_compression"
    SPACIOUS_EXPERIENTIAL = "spacious_experiential"


class UnitIdentity(StrictModel):
    """Stable generic identity for a Workbook lesson or Text section.

    `lesson_number` remains as a backwards-compatible Workbook field. Generic
    code should join on `unit_ref` and order on `sequence_index`.
    """

    unit_ref: str = ""
    sequence_index: int = Field(default=0, ge=0)
    lesson_number: int | None = Field(default=None, ge=1, le=365)

    @model_validator(mode="after")
    def populate_workbook_identity(self) -> UnitIdentity:
        if not self.unit_ref and self.lesson_number is not None:
            self.unit_ref = f"L{self.lesson_number}"
        if self.sequence_index == 0 and self.lesson_number is not None:
            self.sequence_index = self.lesson_number
        if not self.unit_ref:
            raise ValueError("unit_ref is required when lesson_number is absent")
        if self.sequence_index < 1:
            raise ValueError("sequence_index must be at least 1")
        return self


class SourceSentence(StrictModel):
    sentence_id: str
    text: str = Field(min_length=1)
    category: Literal["title", "teaching", "practice", "prayer", "other"] = "other"


class SourceMetadata(StrictModel):
    edition: str
    url: str | None = None
    source_hash: str
    rights_status: Literal["authorized", "public_domain", "user_supplied", "review_required"] = (
        "review_required"
    )


class SourceUnit(UnitIdentity):
    unit_type: UnitType = UnitType.WORKBOOK_LESSON
    language: str = Field(pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")
    title: str = Field(min_length=1)
    lesson_type: LessonType = LessonType.STANDARD
    source: SourceMetadata
    sentences: list[SourceSentence] = Field(min_length=1)
    paragraphs: list[str] = Field(default_factory=list)

    @property
    def source_text(self) -> str:
        return "\n".join(sentence.text for sentence in self.sentences)


class LessonRecord(SourceUnit):
    lesson_number: int = Field(ge=1, le=365)
    unit_type: UnitType = UnitType.WORKBOOK_LESSON
    practice_instructions: dict[str, str] = Field(default_factory=dict)
    reviewed_lessons: list[dict] | None = None


class TextSectionRecord(SourceUnit):
    lesson_number: None = None
    unit_type: UnitType = UnitType.TEXT_SECTION
    lesson_type: LessonType = LessonType.TEXT_SECTION
    chapter: int = Field(ge=1)
    section: str = Field(min_length=1)
    subsections: dict[str, object] = Field(default_factory=dict)


class StyleRecord(StrictModel):
    style_id: str = Field(pattern=r"^[A-Za-z0-9_.-]+$")
    source_lesson: int | None = Field(default=None, ge=1, le=365)
    name: str
    core_prompt: str = Field(min_length=1)
    primary_bucket: str = "unclassified"
    secondary_buckets: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    energy: float = Field(default=0.5, ge=0, le=1)
    tempo_min: int | None = Field(default=None, ge=20, le=240)
    tempo_max: int | None = Field(default=None, ge=20, le=240)
    lyric_density: Literal["low", "medium", "high"] = "medium"
    spoken_word_support: float = Field(default=0.5, ge=0, le=1)
    repetition_affinity: float = Field(default=0.5, ge=0, le=1)
    vocal_clarity: float = Field(default=0.5, ge=0, le=1)
    locked_traits: list[str] = Field(default_factory=list)
    mutable_traits: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_tempo_range(self) -> StyleRecord:
        if (
            self.tempo_min is not None
            and self.tempo_max is not None
            and self.tempo_min > self.tempo_max
        ):
            raise ValueError("tempo_min cannot exceed tempo_max")
        return self


class NormalizedStyleRegistry(StrictModel):
    registry_version: str
    styles: list[StyleRecord]
    source_csv_hash: str | None = None


class CompatibilityScore(UnitIdentity):
    language: str = "en"
    style_id: str
    total: float = Field(ge=0, le=10)
    dimensions: dict[str, float] = Field(default_factory=dict)
    reason: str | None = None
    risks: list[str] = Field(default_factory=list)


class CompatibilityScoreBatch(RootModel[list[CompatibilityScore]]):
    """Structured-output wrapper for one source unit's style scores."""


class SongArchetypeSelection(StrictModel):
    """Structured-output wrapper for an archetype enum."""

    archetype: SongArchetype


class AssignmentConstraints(StrictModel):
    minimum_style_usage: int = Field(default=1, ge=0)
    maximum_style_usage: int = Field(default=2, ge=1)
    minimum_exact_style_gap: int = Field(default=8, ge=0)
    maximum_consecutive_primary_bucket: int = Field(default=2, ge=1)
    missing_score_policy: Literal["error", "zero"] = "error"

    @model_validator(mode="after")
    def validate_usage(self) -> AssignmentConstraints:
        if self.minimum_style_usage > self.maximum_style_usage:
            raise ValueError("minimum_style_usage cannot exceed maximum_style_usage")
        return self


class AssignmentRecord(UnitIdentity):
    language: str
    style_id: str
    primary_bucket: str
    fit_score: float
    assignment_version: str


class AssignmentManifest(StrictModel):
    manifest_version: str
    generated_at: str
    assignments: list[AssignmentRecord]
    constraints: AssignmentConstraints


class StyleAdaptation(UnitIdentity):
    style_id: str
    core_prompt: str
    adaptation: str
    final_prompt: str
    bpm: int | None = None
    core_identity_preserved: bool = True


class LessonAnalysisProfile(UnitIdentity):
    language: str = "en"
    lesson_type: LessonType
    themes: list[str] = Field(default_factory=list)
    emotional_start: str = "neutral"
    emotional_destination: str = "peace"
    energy_target: float = Field(default=0.5, ge=0, le=1)
    lyric_density: Literal["low", "medium", "high"] = "medium"
    repetition_affinity: float = Field(default=0.5, ge=0, le=1)
    spoken_word_need: float = Field(default=0.3, ge=0, le=1)
    clarity_requirement: float = Field(default=0.5, ge=0, le=1)
    preferred_arc: str = "build_up"
    suitable_traits: list[str] = Field(default_factory=list)
    unsuitable_traits: list[str] = Field(default_factory=list)
    ranked_archetypes: list[SongArchetype] = Field(default_factory=list)
    analyzed_source_hash: str = ""
    analysis_version: str = "0.1.0"


class PlanSection(StrictModel):
    label: str
    function: str
    source_sentence_ids: list[str] = Field(default_factory=list)
    treatment: Literal["sung", "spoken", "instrumental"] = "sung"
    repetition_count: int = 1


class LyricPlan(UnitIdentity):
    language: str = "en"
    archetype: SongArchetype
    sections: list[PlanSection]
    total_word_count: int = 0
    spoken_word_count: int = 0


class GeneratedLyric(StrictModel):
    section_label: str
    text: str


class GeneratedLyricsResponse(RootModel[list[GeneratedLyric]]):
    """Structured-output wrapper for generated lyric sections."""


class SongArtifact(UnitIdentity):
    title: str
    archetype: SongArchetype
    lesson_type: LessonType
    language: str = "en"
    style_id: str
    style_adaptation: StyleAdaptation
    lyric_plan: LyricPlan
    lyrics: list[GeneratedLyric]
    full_lyrics_text: str
    source_hash: str
    assignment_version: str
    generator_version: str

    @property
    def total_words(self) -> int:
        return len(self.full_lyrics_text.split())


class TargetedRepairRequest(UnitIdentity):
    language: str = "en"
    failed_fields: list[str] = Field(default_factory=list)
    validator_report: ValidationReport | None = None
    current_artifact: SongArtifact | None = None
    retry_count: int = 0
    max_retries: int = 3
    error_messages: list[str] = Field(default_factory=list)


class FinalSongArtifact(UnitIdentity):
    language: str = "en"
    title: str
    style_id: str
    style_prompt: str
    lyrics: str
    archetype: str
    lesson_type: str
    source_hash: str
    assignment_version: str
    generator_version: str
    repair_count: int = 0
    passed_validation: bool = False


class ValidationIssue(StrictModel):
    code: str
    message: str
    line_number: int | None = None
    severity: Literal["error", "warning"] = "error"


class ValidationReport(StrictModel):
    passed: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


class PipelineConfig(StrictModel):
    lesson_min: int = 116
    lesson_max: int = 199
    languages: list[str] = Field(default_factory=lambda: ["en"])
    seed: int = 116199
    lyrics_policy: LyricPolicy = LyricPolicy.VERBATIM_ONLY
    maximum_total_words: int = 550
    maximum_spoken_words: int = 220
    maximum_repair_attempts: int = 3
    style_registry_version: str = "0.1.0"
    assignment_version: str = "scipy-milp-0.1.0"


class BatchExport(StrictModel):
    export_version: str
    generated_at: str
    songs: list[FinalSongArtifact]
    total_lessons: int
    passed_count: int
    failed_count: int

    @property
    def total_units(self) -> int:
        return self.total_lessons
