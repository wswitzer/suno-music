from __future__ import annotations

from .llm import LLMProvider, plan_lyrics, select_archetype
from .models import LessonAnalysisProfile, LessonRecord, LessonType, LyricPlan, SongArchetype

# The two specialized archetypes with no automatic lesson-type mapping in the
# current source (116-199 is review/standard/experiential only). They can only
# surface when the analyzer ranks them, so the batch selector gives them a
# minimum, suitability-driven opportunity without boosting global frequency.
COVERED_TARGETS = (SongArchetype.SHORT_MANTRA, SongArchetype.LONG_TEACHING)

LessonKey = tuple[int, str]
ArchetypeMap = dict[LessonKey, SongArchetype]


def baseline_archetype(
    lesson: LessonRecord,
    profile: LessonAnalysisProfile | None,
    llm: LLMProvider,
    prompt_version: str = "0.1.0",
) -> SongArchetype:
    """Single-lesson baseline.

    Reviews are immutably paired_review. Otherwise use the analyzer's top-ranked
    archetype, falling back to the LLM only when the profile has no ranking, and
    to a stable default when no profile exists at all."""
    if lesson.lesson_type == LessonType.REVIEW:
        return SongArchetype.PAIRED_REVIEW
    if profile is None:
        return SongArchetype.TITLE_TEACHING_PRAYER
    if profile.ranked_archetypes:
        return profile.ranked_archetypes[0]
    return select_archetype(lesson, profile, llm, prompt_version)


def _rank_of(profile: LessonAnalysisProfile, target: SongArchetype) -> int | None:
    """0-based rank of the target in the analyzer's ranked list; None if absent."""
    for index, archetype in enumerate(profile.ranked_archetypes):
        if archetype == target:
            return index
    return None


def _candidate_score(
    profile: LessonAnalysisProfile, target: SongArchetype
) -> tuple[int, int, int] | None:
    """Deterministic suitability signal for choosing the best eligible lesson for
    a coverage target. Primary: analyzer rank (lower is better). Tie-breakers are
    only consulted to break rank ties and are order-independent: repetition
    affinity (higher first; inverted to sort ascending), then lesson number
    (lower first) as the stable final tie-break. Returns None when the target is
    not ranked, so an ineligible lesson can never be selected."""
    rank = _rank_of(profile, target)
    if rank is None:
        return None
    affinity_asc = round((1.0 - profile.repetition_affinity) * 1000)
    return (rank, affinity_asc, profile.lesson_number)


def _eligible_candidates(
    lessons_by_key: dict[LessonKey, LessonRecord],
    profiles_by_key: dict[LessonKey, LessonAnalysisProfile],
    target: SongArchetype,
    occupied: set[LessonKey],
) -> list[LessonKey]:
    """Best-first list of lesson keys eligible for `target`, excluding reviews
    and `occupied` keys. A lesson is eligible only if its profile ranks target."""
    scored: list[tuple[tuple[int, int, int], LessonKey]] = []
    for key, lesson in lessons_by_key.items():
        if key in occupied or lesson.lesson_type == LessonType.REVIEW:
            continue
        profile = profiles_by_key.get(key)
        if profile is None:
            continue
        score = _candidate_score(profile, target)
        if score is None:
            continue
        scored.append((score, key))
    scored.sort(key=lambda item: item[0])
    return [key for _, key in scored]


def _promote(plan: ArchetypeMap, key: LessonKey, target: SongArchetype) -> None:
    plan[key] = target


def choose_archetypes_for_batch(
    lessons: list[LessonRecord],
    profiles: list[LessonAnalysisProfile],
    llm: LLMProvider,
    prompt_version: str = "0.1.0",
) -> ArchetypeMap:
    """Authoritative, order-independent archetype assignment for the whole batch.

    Algorithm:
      1. Reviews are always paired_review; coverage never touches them.
      2. Every non-review lesson starts from its analyzer top-ranked archetype
         (or the deterministic baseline fallback).
      3. A covered target already protruding as some lesson's top pick is natural
         coverage — we do not add a synthetic copy anywhere (no boosting).
      4. For each covered target that is still absent, pick its single best
         eligible lesson *across the batch* (rank, then repetition affinity,
         then lesson-number tie-break). Eligibility = the analyzer ranked it.
      5. If both absent targets would claim the same lone best lesson, choose the
         (short, long) pairing that minimizes total ranking penalty while keeping
         every assigned lesson unique (reviews fixed); if distinct candidates
         cannot be found at all, promote only the target with the strongest
         ranked candidate and leave the other absent rather than force an
         ineligible lesson.
    Returns a { (lesson_number, language): SongArchetype } mapping for every
    lesson in the batch."""
    profiles_by_key: dict[LessonKey, LessonAnalysisProfile] = {
        (p.lesson_number, p.language): p for p in profiles
    }
    lessons_by_key: dict[LessonKey, LessonRecord] = {
        (lesson.lesson_number, lesson.language): lesson for lesson in lessons
    }

    plan: ArchetypeMap = {}
    for key, lesson in lessons_by_key.items():
        plan[key] = baseline_archetype(lesson, profiles_by_key.get(key), llm, prompt_version)

    # Occupied: reviews (never reassigned) and any lesson already carrying a
    # covered archetype. A lesson that naturally protrudes a target cannot be
    # reused for another target.
    occupied = {
        key
        for key in lessons_by_key
        if lessons_by_key[key].lesson_type == LessonType.REVIEW
        or plan[key] in COVERED_TARGETS
    }

    remaining = [
        target
        for target in COVERED_TARGETS
        if not any(plan[key] == target for key in plan)
    ]
    if not remaining:
        return plan

    candidates: dict[SongArchetype, list[LessonKey]] = {
        target: _eligible_candidates(lessons_by_key, profiles_by_key, target, occupied)
        for target in remaining
    }

    # A single uncovered target: promote its best eligible lesson.
    if len(remaining) == 1:
        target = remaining[0]
        best = candidates[target][:1]
        if best:
            _promote(plan, best[0], target)
        return plan

    first, second = remaining[0], remaining[1]
    first_list, second_list = candidates[first], candidates[second]

    # Find the unique-lesson pairing of minimal total ranking penalty. Score is a
    # (rank, affinity_asc, lesson) tuple; pairs are compared lexicographically so
    # rank dominates, ties resolved deterministically.
    best_first: LessonKey | None = None
    best_second: LessonKey | None = None
    best_total: tuple[int, int, int] | None = None

    for f_key in first_list:
        for s_key in second_list:
            if f_key == s_key:
                continue
            f_profile = profiles_by_key[f_key]
            s_profile = profiles_by_key[s_key]
            f_score = _candidate_score(f_profile, first)
            s_score = _candidate_score(s_profile, second)
            assert f_score is not None and s_score is not None
            total = (f_score[0] + s_score[0], f_score[1] + s_score[1], f_score[2] + s_score[2])
            if best_total is None or total < best_total:
                best_total = total
                best_first, best_second = f_key, s_key

    if best_first is not None and best_second is not None:
        _promote(plan, best_first, first)
        _promote(plan, best_second, second)
        return plan

    # No feasible distinct pairing: promote only whichever target has the single
    # strongest available candidate; leave the other absent.
    strongest_target: SongArchetype | None = None
    strongest_key: LessonKey | None = None
    strongest_score: tuple[int, int, int] | None = None
    for target in remaining:
        if not candidates[target]:
            continue
        key = candidates[target][0]
        score = _candidate_score(profiles_by_key[key], target)
        if score is None:
            continue
        if strongest_score is None or score < strongest_score:
            strongest_score = score
            strongest_target, strongest_key = target, key
    if strongest_target is not None and strongest_key is not None:
        _promote(plan, strongest_key, strongest_target)
    return plan


def create_lyric_plan(
    lesson: LessonRecord,
    archetype: SongArchetype,
    llm: LLMProvider,
    prompt_version: str = "0.1.0",
) -> LyricPlan:
    return plan_lyrics(lesson, archetype, llm, prompt_version)