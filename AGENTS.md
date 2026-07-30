# Local Agent Handoff

## Goal

Extend this starter into the production pipeline for ACIM Workbook Lessons 116–199 without weakening deterministic assignment or source validation.

## Preserve these invariants

1. Never let an LLM greedily assign styles one lesson at a time.
2. Preserve every curated `core_prompt` byte-for-byte; append adaptations separately.
3. Freeze and version the assignment manifest before lyrics are generated.
4. Do not retrieve lesson text from model memory.
5. Require a configured, rights-reviewed source record for each language and lesson.
6. Under `verbatim_only`, all sung and spoken content—including ad-libs—must match the approved source.
7. Repair only failed sections rather than regenerating complete passing artifacts.

## Recommended augmentation order

1. Locate the real `suno_metadata_songs.csv`, inspect its headers, and extract Lessons 290–361 styles.
2. Add an LLM-backed style normalization stage with caching, strict JSON validation, and manual overrides.
3. Implement a local JSON/CSV source provider before any web source provider.
4. Add one provider-neutral structured-output LLM gateway.
5. Generate and persist all lesson-style compatibility scores.
6. Tune the global optimizer against the real 84 lessons and ~47 styles.
7. Implement archetype selection, lyric planning, bounded style adaptation, and lyric generation.
8. Repair only validator failures, with a maximum of three attempts.
9. Export one folder per lesson plus a compact CSV for Suno.

## Required optimizer defaults

- every style used at least once;
- no style used more than twice;
- exact style separated by at least eight lesson numbers;
- no more than two consecutive songs from one primary bucket;
- no silent random fallback when constraints are infeasible.

## Song-form rule

The Lesson 338 title-mantra / spoken-teaching / prayer structure is one archetype, not the universal form. Review lessons must preserve both reviewed ideas. Lessons centered on stillness or experience should be allowed to use fewer words and more musical space.

## Public-repository caution

Do not commit copyrighted lesson text, API keys, or private datasets. Keep source-edition metadata, source hashes, and rights status in every generated artifact.

## Quality gate

Run a six-lesson pilot spanning review, standard, short, long, practice-centered, and experiential lessons. Lock prompt versions after manual review, then assign all 84 styles before generating final lyrics.
