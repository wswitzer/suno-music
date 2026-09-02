# ACIM Text Chapter → Song-per-Section Extension

## Goal

Extend the existing pipeline so an ACIM Text chapter can generate one song per top-level section without creating a second lyric/style pipeline.

## Architecture

Generalize the pipeline processing unit rather than forking it. Workbook lessons and Text sections both feed the same analysis → scoring → optimization → planning → style adaptation → lyric generation → validation → repair → export pipeline.

### Generic source identity

Every processing unit carries:

- `unit_type`
- `unit_ref`
- `sequence_index`
- `language`
- `title`
- `source`
- `sentences`
- `paragraphs`

Workbook example: `unit_type=workbook_lesson`, `unit_ref=L116`, `sequence_index=116`.

Text example: `unit_type=text_section`, `unit_ref=T-27.I`, `sequence_index=1`.

Text sections additionally carry `chapter`, `section`, and subsection metadata.

## Implementation scope

1. Introduce `SourceUnit`, retain `LessonRecord`, and add `TextSectionRecord`.
2. Generalize downstream identity from `lesson_number` to `unit_ref` plus `sequence_index` while preserving Workbook compatibility fields where useful.
3. Preserve real sentence-level structure and paragraph order in Text ingestion.
4. Add deterministic local JSON Text ingestion and Text-oriented Pinecone support only where metadata can be verified safely.
5. Generalize optimizer joins/order/gap calculations to source units.
6. Generalize LLM prompts from Workbook-only wording to source-unit context.
7. Default to one song per top-level Text section.
8. Preserve verbatim/source/style safeguards and targeted repair.
9. Add Text-oriented export paths and metadata.
10. Add CLI support for `run-batch --book text --chapter <n>`.

## Chapter-sized style assignment

When a chapter has fewer units than the style pool, default to distinct styles where feasible:

- `minimum_style_usage = 0`
- `maximum_style_usage = 1`
- `minimum_exact_style_gap = 0`
- `maximum_consecutive_primary_bucket = 2`

Do not require every available style to appear in a single chapter.

## Granularity

Default: one top-level Text section = one song. Long sections should be represented by selected verbatim passages across the teaching arc rather than automatically split. Subsection splitting is an explicit fallback only.

## Tests

Use synthetic/non-copyrighted fixtures for Text JSON ingestion, stable IDs, ordering, optimizer joins, distinct-style chapter assignment, planning, verbatim validation, repair, export, and Workbook regression coverage.
