from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LyricPolicy(StrEnum):
    VERBATIM_ONLY = "verbatim_only"
    VERBATIM_ANCHORS = "verbatim_anchors"
    PARAPHRASE_ALLOWED = "paraphrase_allowed"


class LessonType(StrEnum):
    STANDARD = "standard"
    REVIEW = "review"
    EXPERIENTIAL = "experiential"


class SongArchetype(StrEnum):
    TITLE_TEACHING_PRAYER = "title_teaching_prayer"
    PAIRED_REVIEW = "paired_review"
    DECLARATION_DEVELOPMENT = "declaration_and_development"
    PRACTICE_MEDITATION = "practice_centered_meditation"
    SHORT_MANTRA = "short_mantra"
    LONG_TEACHING = "long_teaching_compression"
    SPACIOUS_EXPERIENTIAL = "spacious_experiential"


class SourceSentence(StrictModel):
    sentence_id: str
    text: str = Field(min_length=1)
    category: Literal["title", "teaching", "practice", "prayer", "other"] = "other"


class SourceMetadata(StrictModel):
    edition: str
    url: str | None = None
    source_hash: str
    rights_status: Literal[
        "authorized", "public_domain", "user_supplied", "review_required"
    ] = "review_required"


class LessonRecord(StrictModel):
    lesson_number: int = Field(ge=1, le=365)
    language: str = Field(pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")
    title: str = Field(min_length=1)
    lesson_type: LessonType = LessonType.STANDARD
    source: SourceMetadata
    sentences: list[SourceSentence] = Field(min_length=1)

    @property
    def source_text(self) -> str:
        return "\n".join(sentence.text for sentence in self.sentences)


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
        if self.tempo_min is not None and self.tempo_max is not None:
            if self.tempo_min > self.tempo_max:
                raise ValueError("tempo_min cannot exceed tempo_max")
        return self


class CompatibilityScore(StrictModel):
    lesson_number: int
    language: str = "en"
    style_id: str
    total: float = Field(ge=0, le=10)
    reason: str | None = None
    risks: list[str] = Field(default_factory=list)


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


class AssignmentRecord(StrictModel):
    lesson_number: int
    language: str
    style_id: str
    primary_bucket: str
    fit_score: float
    assignment_version: str


class StyleAdaptation(StrictModel):
    style_id: str
    lesson_number: int
    core_prompt: str
    adaptation: str
    final_prompt: str
    bpm: int | None = None
    core_identity_preserved: bool = True


class ValidationIssue(StrictModel):
    code: str
    message: str
    line_number: int | None = None
    severity: Literal["error", "warning"] = "error"


class ValidationReport(StrictModel):
    passed: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
