# Local Agent Handoff

## Goal

Extend this starter into the production pipeline for ACIM Workbook Lessons 116–199 without weakening deterministic assignment or source validation.

## Git workflow

See `docs/agents/git-workflow.md` for full conventions. TL;DR:

- **Atomic commits** — one logical change per commit (models, then provider, then optimizer, etc.)
- **Small diffs** — max ~400 lines per commit; commit after every passing test cycle
- **Branch** — `agent/<ticket>-<desc>` per task; never commit to `main`
- **Messages** — imperative mood, ≤72-char subject, body explains *why*
- **No generated artifacts** — exclude outputs/, __pycache__/, .env, node_modules/
- **No copyrighted text, keys, or private data** in commits

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

## Source data access

For the deterministic English Workbook generation pipeline, the canonical source is the clean structured `workbook_enhanced.json` maintained by the separate `acim-core-data` project. Pass its local path with `--source-json` or `ACIM_WORKBOOK_JSON`; never hardcode a machine-specific path and never copy the copyrighted dataset into this public repository. `ACIMJsonSourceProvider` must expose clean authorial text only to generation/validation stages, with editorial numbering and workbook references treated as metadata.

Pinecone remains a secondary search/cross-check representation, not the canonical serialization for strict lyric generation. Reference `vector_database.md` in `acim-core-data` for API specs when semantic search or cross-checking is needed. Key Pinecone details:

- **Index:** `acim-text` (host: `https://acim-text-e2xpwpt.svc.aped-4627-b74a.pinecone.io`)
- **Region:** `us-east-1` (AWS Serverless)
- **Dimension:** 768 dense float dimensions
- **Metric:** Cosine / Dot Product
- **Embedding model:** Google Gemini `models/gemini-embedding-001` with `outputDimensionality: 768`
- **Namespaces:** `text` and `workbook`
- **Filter by:** `{"lesson": {"$eq": <number>}}` with a dummy `[0.01] * 768` vector (`includeMetadata: true`)
- **API key:** `PINECONE_API_KEY` environment variable
- **Provider:** `PineconeSourceProvider` in `src/acim_suno/sources.py`

Under `verbatim_only`, exact source phrases may be arranged, repeated, or interleaved as separate lyric lines/sections, but words from noncontiguous source spans must never be fused into a new phrase.

## Gemini LLM access (as configured in Album Creator)

The Album Creator project authenticates Gemini through **Vertex AI**, not the direct `GEMINI_API_KEY` endpoint:

- **Project:** `sinless-sounds` (`GOOGLE_CLOUD_PROJECT` in `.env.local`)
- **LLM location:** `global` (Album Creator's `aiGlobal` uses `location: 'global'`; `gemini-3.1-pro-preview` is **not** served from `us-central1` — a regional call returns 404 NOT_FOUND)
- **Embedding location:** `us-central1` via Vertex AI REST endpoint (`text-embedding-004`, 768 dims)
- **Auth:** Application Default Credentials via `gcloud auth application-default login` / service account ADC
- **Models in use:** `gemini-3.1-pro-preview` for journey plans, song/lyrics, and album names (server); `gemini-2.5-pro` only in the legacy `scripts/gemini-generate-chapter.js`
- **Client:** `GoogleGenAI({ vertexai: true, project, location })` from `@google/genai`
- **No `GEMINI_API_KEY`** is used; do not assume the direct API key is available

If the pipeline's `GeminiLLMProvider` needs a key, prefer Vertex AI ADC (set `GOOGLE_APPLICATION_CREDENTIALS` or `GOOGLE_CLOUD_PROJECT`/`GOOGLE_CLOUD_LOCATION=global`) rather than adding a new direct API key.

Do not hardcode machine-specific file paths. Use Pinecone (env var API key) or require the path as a CLI argument.

## Public-repository caution

Do not commit copyrighted lesson text, API keys, or private datasets. Keep source-edition metadata, source hashes, and rights status in every generated artifact.

## Quality gate

Run a six-lesson pilot spanning review, standard, short, long, practice-centered, and experiential lessons. Lock prompt versions after manual review, then assign all 84 styles before generating final lyrics.
