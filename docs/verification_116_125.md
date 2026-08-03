# 116–125 Pilot Verification Notes

Status of the end-to-end real-data pilot (Pinecone → Gemini Vertex), and the
outstanding strict-verbatim question for the review agent.

## Pipeline stages verified

Everything below ran with the real source provider (`pinecone`) and the real
LLM (`gemini-3.1-pro-preview`, Vertex AI, project `sinless-sounds`, location
`global`). Artifacts live under `outputs/verification/` (gitignored).

- **Sources** — 10 lessons (116–125) ingested; numeric (non-lexicographic)
  reference ordering verified (`W-pI.121.1..13`); per-lesson content hashes
  unique. See `_ordered_pinecone_paragraphs`, `_pinecone_lesson_hash`.
- **Review classification** — boundaries correct: 116–120, 141–150, 171–180 are
  REVIEW; 121, 140, 151, 170, 181 are not. Committed `_reviewed_lesson_numbers`
  so review lessons expose the idea pair they recapitulate (e.g. L120 → `[109,110]`).
- **Profiles** — Gemini analysis valid for all 10; `analyzed_source_hash` matches
  the lesson source hash exactly.
- **Scoring** — 430 records (10 lessons × 43 styles), no duplicate/missing/
  unexpected IDs; the batch retry loop caught and recovered one invalid batch.
  Profile data confirmed present in the scoring prompt.
- **Assignments** — 10 distinct styles, max 2 consecutive same primary bucket,
  good bucket diversity. Pilot config relaxes min style usage to 0
  (`config/pipeline.pilot116_125.yaml`); the global default holds for the full
  84-lesson run.
- **Plans** — 116–120 all `paired_review`; non-reviews use their ranked archetypes.
- **Generated lyrics** — 10 songs produced. Review songs preserve both reviewed
  ideas (L118, L119 verified phrase-level).

Tests: 18 passing, `ruff check src tests` clean.

## Open issue: strict-verbatim validation

4 of 10 songs fail strict verbatim (L116, 117, 120, 122) when validated against
the **Pinecone-derived** `source_text`. Root cause and resolution explored:

1. The **generator joins sentences and strips the editorial numbering**
   (`2 / 3 / 4`). Pinecone's text keeps those numbers inline, so a clean lyric
   line (`Do you want peace? Forgiveness offers it.`) is not a **contiguous**
   substring of the numbered source. This is the main mismatch.

2. The clean, number-free canonical text already exists in the central store:
   - `workbook_enhanced.json` → per-lesson `idea_clean` field, and
   - the `ACIMJsonSourceProvider` (same file) builds `source_text` from
     per-sentence `.text`, which is **already clean** (zero editorial numbers,
     zero `W-pI` refs).
   Validating against that clean source resolves most failures:

   | Lesson | fails vs Pinecone | fails vs JSON clean |
   |--------|-------------------|---------------------|
   | 116    | 4                 | 1                   |
   | 117    | 4                 | 1                   |
   | 118    | 0                 | 0                   |
   | 119    | 0                 | 0                   |
   | 120    | 2                 | 3                   |
   | 121    | 0                 | 0                   |
   | 122    | 4                 | 0                   |
   | 124    | 0                 | 0                   |
   | 125    | 0                 | 0                   |

3. Two genuinely separate issues remain (not source-related):
   - **L120** — generated lyrics emit the **raw numbered source verbatim**
     (`(109) ... 2 ... W-pI.120.W-pI.2 ...`), including a malformed reference
     `W-pI.120.W-pI.2`. This looks like a generator/prompt defect, not a source
     problem. Whatever else, the lyric writer should output clean text.
   - **L116 / L117 outros** weave **two ideas together** (`God's Will ... I share
     God's Will ...`), which is not a contiguous quote of any source span. Valid
     as a musical refrain, but not strictly verbatim. Needs a product decision
     (allow idea-interleaving refrains under `verbatim_only`, or disallow).

## Decision sought (not yet made — do not silently change)

- Which source does the verbatim validator compare against? Recommended: the
  **clean JSON source** (single source of truth from `acim-core-data`), not the
  number-retaining Pinecone text.
- **Resolved policy:** musical interleaving is allowed at the arrangement level, but
  each interleaved unit must remain its own exact contiguous source phrase/line.
  L116/L117's fused outro lines therefore remain invalid and should be targeted-repaired
  into separate exact source lines. L120 should be regenerated from the clean JSON source
  before any special-case repair is considered.

## Data integrity / source-of-truth notes

- `acim-core-data` is the intended single source of truth. The project should
  consume the clean `idea_clean` (or the JSON provider's per-sentence text)
  rather than re-cleaning Pinecone output with regex, and must not duplicate
  cleaned datasets across projects.
- There is a malformed reference in the Pinecone data: `W-pI.120.W-pI.2`.
  Ordering is unaffected (L120 has a single vector `W-pI.120.1`), but the string
  leaks into generated lyrics, so the source record is worth auditing.

## Resolution adopted after review

- Keep the strict validator unchanged.
- Use `workbook_enhanced.json` through `ACIMJsonSourceProvider` as the canonical English generation/validation source; Pinecone is secondary.
- Preserve clean paragraph sentences as atomic `SourceSentence` units.
- Do not emit source IDs, editorial numbering, or workbook references as lyrics.
- Re-run 116–125 from ingestion onward because source hashes/profiles/score caches change.
