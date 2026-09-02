# ACIM Suno Pipeline

Pipeline for assigning a curated pool of Suno styles to approved ACIM source units and preparing a reproducible lyric-generation workflow. It supports Workbook lessons and structured Text sections without maintaining separate generation pipelines.

The code implements the parts that should be deterministic:

- extraction of reusable style prompts from a song metadata CSV;
- typed source-unit, style, compatibility, assignment, and song schemas;
- global mixed-integer style assignment rather than greedy pool exhaustion;
- style usage, spacing, and bucket-run constraints;
- verbatim-source lyric validation;
- style-adaptation and batch-diversity validation;
- versioned prompt templates for the LLM stages.

It intentionally does **not** scrape or bundle ACIM text. Source records must be supplied from an edition the operator is authorized to use.

## Architecture

```text
approved source units (Workbook lessons or Text sections)
        ↓
source-unit analysis (LLM, structured JSON)
        ↓
normalized curated style registry
        ↓
unit × style compatibility scores (LLM)
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

Generic processing identity is `unit_ref` plus `sequence_index`. Workbook lessons retain `lesson_number` for backwards compatibility. Examples: `L116` and `T-27.I`.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
```

## Generate one song per Text section

Use an approved structured JSON source containing `chapters -> <chapter> -> sections`. Each top-level section becomes one source unit and one song.

```bash
acim-suno run-batch \
  --book text \
  --chapter 27 \
  --source-type acim_json \
  --source-json /path/to/approved/text_structured.json \
  --provider gemini \
  --csv /path/to/suno_metadata_songs.csv
```

For chapter-sized batches with more available styles than sections, the run uses distinct styles where feasible rather than requiring the full style pool to be exhausted. Text-section Pinecone ingestion is intentionally not enabled until its metadata ordering/filter contract is verified; structured JSON is the deterministic source path.

A dry run exercises ingestion, style normalization, compatibility-score scaffolding, and global assignment without making lyric-generation calls:

```bash
acim-suno run-batch \
  --book text \
  --chapter 27 \
  --source-type acim_json \
  --source-json /path/to/approved/text_structured.json \
  --csv /path/to/suno_metadata_songs.csv \
  --dry-run
```

## Quick Workbook demo

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

The resulting prompts are preserved verbatim. A later LLM/manual normalization pass adds buckets, tags, locked traits, mutable traits, and ranges without overwriting `core_prompt`.

## Validate verbatim-only lyrics

```bash
acim-suno validate \
  --type lyrics \
  --source-file /path/to/approved_source.txt \
  --lyrics-file /path/to/generated_lyrics.txt
```

Section labels and approved non-lyrical production directions are ignored. Sung or spoken content must map to the approved source under `verbatim_only`.

## Data contracts

See `src/acim_suno/models.py`. Important invariants:

- the curated `core_prompt` is immutable;
- source-specific changes live in `adaptation`;
- assignments are frozen before lyric generation;
- every artifact records source, prompt, model, registry, and assignment versions;
- English and Spanish are independent source records;
- `verbatim_only` means every sung/spoken phrase must map to approved source text.

See `docs/text-chapter-song-plan.md` for the Text chapter extension design and `AGENTS.md` for repository agent constraints.
