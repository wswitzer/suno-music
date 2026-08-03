# ACIM Suno Pipeline

Starter implementation for assigning a curated pool of Suno styles to ACIM Workbook lessons and preparing a reproducible lyric-generation workflow.

The code implements the parts that should be deterministic:

- extraction of reusable style prompts from a song metadata CSV;
- typed lesson, style, compatibility, assignment, and song schemas;
- global mixed-integer style assignment rather than greedy pool exhaustion;
- style usage, spacing, and bucket-run constraints;
- verbatim-source lyric validation;
- style-adaptation and batch-diversity validation;
- versioned prompt templates for the LLM stages.

It intentionally does **not** scrape or bundle ACIM text. Source records must be supplied from an edition the operator is authorized to use. Provider-specific LLM calls are also left behind an interface for the local agent to implement.

## Architecture

```text
approved lesson sources
        ↓
lesson analysis (LLM, structured JSON)
        ↓
normalized curated style registry
        ↓
lesson × style compatibility scores (LLM)
        ↓
global MILP assignment (code)
        ↓
archetype and lyric plan (LLM)
        ↓
bounded style adaptation + lyrics (LLM)
        ↓
source/style/batch validators (code)
        ↓
targeted repair + export
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
```

## Quick demo

```bash
acim-suno optimize \
  --lessons examples/lessons.json \
  --styles examples/styles.json \
  --scores examples/scores.jsonl \
  --config config/demo.yaml \
  --out /tmp/assignment_manifest.json

cat /tmp/assignment_manifest.json
```

## Extract curated styles from the existing CSV

The extractor looks for common column names such as `lesson_number`, `title`, `styles_raw`, `suno_style`, and `style`.

```bash
acim-suno extract-styles \
  --csv /path/to/suno_metadata_songs.csv \
  --out data/styles/raw_styles.json \
  --min-lesson 290 \
  --max-lesson 361
```

The resulting prompts are preserved verbatim. A later LLM/manual normalization pass should add buckets, tags, locked traits, mutable traits, and ranges without overwriting `core_prompt`.

## Canonical workbook source

For deterministic English generation, use the clean structured `workbook_enhanced.json` from the separate `acim-core-data` project. Keep that file local and pass its path with `--source-json` or the `ACIM_WORKBOOK_JSON` environment variable; do not copy it into this public repository. Pinecone is retained for semantic search and cross-checking, but strict generation/validation should use the clean JSON representation so editorial numbering and references are not mistaken for lyric text.

```bash
ACIM_WORKBOOK_JSON=/path/to/acim-core-data/workbook_enhanced.json \
acim-suno run-batch \
  --source-type acim_json \
  --language en \
  --lesson-start 116 \
  --lesson-end 125 \
  --provider gemini
```

Under `verbatim_only`, exact source phrases may be repeated, reordered, and interleaved as separate lyric lines or sections. Combining words from noncontiguous source spans into a new phrase remains invalid.

## Validate verbatim-only lyrics

```bash
acim-suno validate-lyrics \
  --source-file /path/to/approved_lesson.txt \
  --lyrics-file /path/to/generated_lyrics.txt
```

Section labels and fully parenthesized production directions are ignored. Sung ad-libs are not ignored and must occur in the approved source.

## Data contracts

See `src/acim_suno/models.py`. Important invariants:

- the curated `core_prompt` is immutable;
- lesson-specific changes live in `adaptation`;
- assignments are frozen before lyric generation;
- every artifact records source, prompt, model, registry, and assignment versions;
- English and Spanish are independent source records;
- `verbatim_only` means every sung/spoken phrase must map to approved source text.

## Local-agent next steps

See [`AGENTS.md`](AGENTS.md) for the exact augmentation sequence.
