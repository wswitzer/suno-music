# Versioned LLM Prompt Contracts

## Style annotator

Normalize one curated Suno prompt into `StyleRecord`. Preserve `core_prompt` exactly. Add buckets, energy, tempo range, lyric density, spoken-word support, repetition affinity, vocal clarity, tags, locked traits, mutable traits, and risks. Identify lesson-specific clauses without silently rewriting the core. Output JSON only.

## Lesson analyzer

Analyze only the supplied approved source. Return lesson type, themes, emotional start/destination, energy target, lyric density, repetition affinity, spoken-word need, clarity requirement, preferred arc, suitable/unsuitable traits, categorized source sentence IDs, and ranked song archetypes. Do not assign a style or write lyrics. Output JSON only.

## Compatibility scorer

Score each supplied lesson-style pair from 0–10. Weight thematic/emotional fit 30%, energy 20%, lyric density 15%, repetition 10%, vocal clarity 10%, emotional arc 10%, and song-form fit 5%. Do not choose a winner or default to ambient/chant. Output compact JSON records only.

Return exactly one score record per supplied style ID — no fewer, no more. The output count must equal the number of style IDs given. If any style is skipped, the run fails.

## Archetype selector

Choose one:

1. `title_teaching_prayer`
2. `paired_review`
3. `declaration_and_development`
4. `practice_centered_meditation`
5. `short_mantra`
6. `long_teaching_compression`
7. `spacious_experiential`

The Lesson 338 mantra/spoken-teaching/prayer form is optional, not universal. Review lessons must preserve both reviewed ideas.

## Lyric planner

Create a section plan, not lyrics. For each section provide label, function, approved source IDs, sung/spoken/instrumental treatment, and repetition count. Under `verbatim_only`, do not propose paraphrases, invented ad-libs, reordered words, or shortened meanings. A short chant must be a contiguous source phrase.

## Bounded style adapter

Append a concise adaptation to the immutable core. Allowed: BPM within range, vocal intimacy/strength, spoken-word amount, choir intensity, intro/outro texture, one secondary instrument, arrangement build, diction/melisma guidance, repetition intensity, and ending treatment. Do not replace genre, rhythmic foundation, signature instrumentation, energy category, or defining vocal identity.

## Lyric writer

Write from the approved plan and source IDs. Under `verbatim_only`, every sung or spoken phrase—including parenthetical ad-libs—must occur contiguously in the source. Repetition and line-break changes are allowed; additions, substitutions, deletions, and word rearrangement are not. Use conservative Suno labels. Keep production prose in the style field, not the lyrics field.

## Targeted repair

Repair only validator-listed fields or sections and preserve all passing material byte-for-byte. For source failures, select a contiguous approved source phrase. For style failures, change only the adaptation suffix. Cap automatic retries and flag unresolved artifacts for review.
