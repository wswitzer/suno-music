from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from .adapter import create_style_adaptation
from .export import export_lesson_folder, export_suno_batch
from .extract_styles import extract_styles_from_csv
from .generator import generate_song
from .io import dump_json, load_jsonl_models, load_models, load_yaml
from .llm import (
    analyze_lesson,
    create_llm_provider,
)
from .models import (
    AssignmentConstraints,
    AssignmentManifest,
    AssignmentRecord,
    CompatibilityScore,
    FinalSongArtifact,
    LessonAnalysisProfile,
    LessonRecord,
    LyricPlan,
    NormalizedStyleRegistry,
    PipelineConfig,
    SongArchetype,
    SongArtifact,
    StyleAdaptation,
    StyleRecord,
    ValidationReport,
)
from .normalize_styles import extract_and_normalize_styles_pipeline, normalize_styles
from .optimizer import AssignmentError, optimize_assignments
from .planner import choose_archetype, create_lyric_plan
from .repair import create_repair_request, repair_song
from .scorer import compute_compatibility_scores
from .sources import ACIMJsonSourceProvider, create_source_provider
from .validators import (
    validate_assignment_batch,
    validate_style_adaptation,
    validate_verbatim_lyrics,
)


def _load_config(args: argparse.Namespace) -> PipelineConfig:
    config_data = load_yaml(args.config) if args.config else {}
    return PipelineConfig.model_validate(config_data.get("project", config_data))


def command_audit_csv(args: argparse.Namespace) -> int:
    import csv

    csv_path = Path(args.csv)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    styles_raw = set()
    range(args.min_lesson or 1, (args.max_lesson or 365) + 1)
    range_rows = [
        r
        for r in rows
        if r.get("lesson_number", "").isdigit()
        and args.min_lesson <= int(r["lesson_number"]) <= (args.max_lesson or 365)
    ]

    for r in range_rows:
        prompt = (r.get("styles_raw") or r.get("suno_style") or r.get("style") or "").strip()
        if prompt:
            styles_raw.add(prompt)

    print(f"Total rows in CSV: {len(rows)}")
    print(f"Rows in lesson range {args.min_lesson}-{args.max_lesson}: {len(range_rows)}")
    print(f"Unique styles in range: {len(styles_raw)}")
    return 0


def command_extract_styles(args: argparse.Namespace) -> int:
    if args.normalize:
        styles = extract_and_normalize_styles_pipeline(
            args.csv,
            min_lesson=args.min_lesson,
            max_lesson=args.max_lesson,
            output_dir=args.out,
        )
    else:
        styles = extract_styles_from_csv(
            args.csv,
            min_lesson=args.min_lesson,
            max_lesson=args.max_lesson,
        )
        dump_json(args.out, styles)
    print(f"Extracted {len(styles)} unique styles")
    return 0


def command_normalize_styles(args: argparse.Namespace) -> int:
    styles = load_models(args.input, StyleRecord)
    normalized = normalize_styles(styles)
    registry = NormalizedStyleRegistry(
        registry_version=args.version or "0.1.0",
        styles=normalized,
        source_csv_hash=None,
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(registry.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Normalized {len(normalized)} styles to {args.out}")
    return 0


def command_ingest_sources(args: argparse.Namespace) -> int:
    if args.source_type == "acim_json":
        if not args.json:
            raise ValueError("--json is required for acim_json source type")
        provider = ACIMJsonSourceProvider(args.json, source_language=args.language)
    else:
        provider = create_source_provider(source_type=args.source_type, source_language=args.language)
    lessons = provider.fetch_lessons(args.min_lesson, args.max_lesson)
    dump_json(args.out, lessons)
    print(f"Ingested {len(lessons)} lessons to {args.out}")
    return 0


def command_analyze_lessons(args: argparse.Namespace) -> int:
    lessons = load_models(args.input, LessonRecord)
    llm = create_llm_provider(args.provider, args.model)
    profiles = []
    for lesson in lessons:
        profile = analyze_lesson(lesson, llm, prompt_version=args.prompt_version)
        profiles.append(profile)
    dump_json(args.out, profiles)
    print(f"Analyzed {len(profiles)} lessons to {args.out}")
    return 0


def command_score_compatibility(args: argparse.Namespace) -> int:
    lessons = load_models(args.lessons, LessonRecord)
    styles = load_models(args.styles, StyleRecord)
    llm = create_llm_provider(args.provider, args.model)
    scores = compute_compatibility_scores(
        lessons,
        styles,
        llm,
        prompt_version=args.prompt_version,
        cache_dir=args.cache_dir,
        force_recompute=args.force,
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for sc in scores:
            f.write(json.dumps(sc.model_dump(mode="json"), ensure_ascii=False) + "\n")
    print(f"Computed {len(scores)} scores to {args.out}")
    return 0


def command_optimize(args: argparse.Namespace) -> int:
    lessons = load_models(args.lessons, LessonRecord)
    styles = load_models(args.styles, StyleRecord)
    scores = load_jsonl_models(args.scores, CompatibilityScore)
    config = load_yaml(args.config)
    constraints = AssignmentConstraints.model_validate(config.get("assignment", {}))
    version = config.get("assignment_algorithm", "scipy-milp-0.1.0")

    assignments = optimize_assignments(
        lessons, styles, scores, constraints, assignment_version=version
    )
    report = validate_assignment_batch(assignments, styles, constraints)
    if not report.passed:
        raise AssignmentError(json.dumps(report.model_dump(mode="json"), indent=2))

    manifest = AssignmentManifest(
        manifest_version="1.0",
        generated_at=datetime.now(UTC).isoformat(),
        assignments=assignments,
        constraints=constraints,
    )
    dump_json(args.out, manifest.assignments)
    print(f"Wrote {len(assignments)} assignments to {args.out}")
    return 0


def command_plan_lyrics(args: argparse.Namespace) -> int:
    lessons = load_models(args.lessons, LessonRecord)
    profiles = load_models(args.profiles, LessonAnalysisProfile)
    llm = create_llm_provider(args.provider, args.model)
    plans = []
    for lesson in lessons:
        matching = [
            p
            for p in profiles
            if p.lesson_number == lesson.lesson_number and p.language == lesson.language
        ]
        profile = matching[0] if matching else None
        archetype = (
            choose_archetype(lesson, profile, llm, args.prompt_version)
            if profile
            else "title_teaching_prayer"
        )
        plan = create_lyric_plan(lesson, archetype, llm, args.prompt_version)
        plans.append(plan)
    dump_json(args.out, plans)
    print(f"Created {len(plans)} lyric plans to {args.out}")
    return 0


def command_adapt_styles(args: argparse.Namespace) -> int:
    lessons = load_models(args.lessons, LessonRecord)
    plans = load_models(args.plans, LyricPlan)
    styles = load_models(args.styles, StyleRecord)
    assignments = load_models(args.assignments, AssignmentRecord)
    llm = create_llm_provider(args.provider, args.model)

    style_by_id = {s.style_id: s for s in styles}
    assignment_by_lesson = {(a.lesson_number, a.language): a for a in assignments}

    adaptations = []
    for lesson in lessons:
        match = assignment_by_lesson.get((lesson.lesson_number, lesson.language))
        if not match:
            continue
        style = style_by_id.get(match.style_id)
        if not style:
            continue
        plan_matches = [
            p
            for p in plans
            if p.lesson_number == lesson.lesson_number and p.language == lesson.language
        ]
        plan = plan_matches[0] if plan_matches else None
        adaptation = create_style_adaptation(lesson, style, plan, llm, args.prompt_version)
        adaptations.append(adaptation)
    dump_json(args.out, adaptations)
    print(f"Created {len(adaptations)} adaptations to {args.out}")
    return 0


def command_generate_lyrics(args: argparse.Namespace) -> int:
    lessons = load_models(args.lessons, LessonRecord)
    plans = load_models(args.plans, LyricPlan)
    adaptations = load_models(args.adaptations, StyleAdaptation)
    llm = create_llm_provider(args.provider, args.model)

    plan_by_lesson = {(p.lesson_number, p.language): p for p in plans}
    adapt_by_lesson = {a.lesson_number: a for a in adaptations}

    artifacts = []
    for lesson in lessons:
        plan = plan_by_lesson.get((lesson.lesson_number, lesson.language))
        adaptation = adapt_by_lesson.get(lesson.lesson_number)
        if not (plan and adaptation):
            continue
        artifact = generate_song(lesson, plan, adaptation, llm, args.prompt_version)
        artifacts.append(artifact)
    dump_json(args.out, artifacts)
    print(f"Generated {len(artifacts)} songs to {args.out}")
    return 0


def command_validate(args: argparse.Namespace) -> int:
    if args.type == "lyrics":
        source = Path(args.source_file).read_text(encoding="utf-8")
        lyrics = Path(args.lyrics_file).read_text(encoding="utf-8")
        report = validate_verbatim_lyrics(lyrics, source)
    elif args.type == "assignment":
        assignments = load_models(args.assignments, AssignmentRecord)
        styles = load_models(args.styles, StyleRecord)
        config = load_yaml(args.config)
        constraints = AssignmentConstraints.model_validate(config.get("assignment", {}))
        report = validate_assignment_batch(assignments, styles, constraints)
    elif args.type == "style":
        adaptation = load_models(args.adaptation, StyleAdaptation)
        styles = load_models(args.styles, StyleRecord)
        style_by_id = {s.style_id: s for s in styles}
        issues = []
        for a in adaptation:
            style = style_by_id.get(a.style_id)
            if style:
                r = validate_style_adaptation(a, style)
                if not r.passed:
                    issues.extend(r.issues)
        report = ValidationReport(passed=not issues, issues=issues)
    else:
        raise ValueError(f"Unknown validation type: {args.type}")

    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0 if report.passed else 2


def command_repair(args: argparse.Namespace) -> int:
    artifacts = load_models(args.artifacts, SongArtifact)
    lessons = load_models(args.lessons, LessonRecord)
    llm = create_llm_provider(args.provider, args.model)

    lesson_by_number = {l.lesson_number: l for l in lessons}
    repaired_all: list[SongArtifact] = []
    failed_all: list[FinalSongArtifact] = []

    for artifact in artifacts:
        lesson = lesson_by_number.get(artifact.lesson_number)
        if not lesson:
            continue
        report = validate_verbatim_lyrics(artifact.full_lyrics_text, lesson.source_text)
        if report.passed:
            repaired_all.append(artifact)
            continue
        request = create_repair_request(artifact, report)
        repaired, _, _final_report = repair_song(request, lesson, llm, args.prompt_version)
        if repaired:
            repaired_all.append(repaired)
            print(f"  Repaired lesson {artifact.lesson_number}")
        else:
            failed_all.append(
                FinalSongArtifact(
                    lesson_number=artifact.lesson_number,
                    title=artifact.title,
                    style_id=artifact.style_id,
                    style_prompt=artifact.style_adaptation.final_prompt,
                    lyrics=artifact.full_lyrics_text,
                    archetype=artifact.archetype.value,
                    lesson_type=artifact.lesson_type.value,
                    source_hash=artifact.source_hash,
                    assignment_version=artifact.assignment_version,
                    generator_version=artifact.generator_version,
                    repair_count=request.retry_count,
                    passed_validation=False,
                )
            )
            print(f"  Failed to repair lesson {artifact.lesson_number}")

    dump_json(args.out, repaired_all)
    print(f"Repaired {len(repaired_all)} artifacts, {len(failed_all)} still failing")
    return 0


def command_export(args: argparse.Namespace) -> int:
    artifacts = load_models(args.artifacts, SongArtifact)
    lessons_path = Path(args.lessons) if args.lessons else None
    reports: list[ValidationReport] | None = None

    if lessons_path and lessons_path.exists():
        lessons = load_models(lessons_path, LessonRecord)
        lesson_by_num = {l.lesson_number: l for l in lessons}
        reports = []
        for a in artifacts:
            lesson = lesson_by_num.get(a.lesson_number)
            if lesson:
                reports.append(validate_verbatim_lyrics(a.full_lyrics_text, lesson.source_text))
            else:
                reports.append(ValidationReport(passed=True))

    export_suno_batch(artifacts, reports, output_dir=args.out)

    if args.lesson_folders:
        lessons = load_models(args.lessons, LessonRecord) if lessons_path else []
        lesson_by_num = {l.lesson_number: l for l in lessons}
        for a in artifacts:
            lesson = lesson_by_num.get(a.lesson_number)
            report = None
            if lesson:
                report = validate_verbatim_lyrics(a.full_lyrics_text, lesson.source_text)
            folder = export_lesson_folder(a, report, output_dir=Path(args.out) / "lessons")
            print(f"  Exported lesson {a.lesson_number} to {folder}")

    return 0


def command_run_batch(args: argparse.Namespace) -> int:
    load_yaml(args.config)
    raw_config = load_yaml(args.config)
    pipeline_config = PipelineConfig.model_validate(raw_config.get("project", raw_config))
    assignment_config = AssignmentConstraints.model_validate(raw_config.get("assignment", {}))

    output_dir = Path(args.output_dir) if args.output_dir else Path("outputs")
    output_dir.mkdir(parents=True, exist_ok=True)

    llm = create_llm_provider(args.provider or "mock", args.model)

    if args.source_type == "acim_json":
        if not args.source_json:
            raise ValueError("--source-json required for acim_json source type")
        source_provider = ACIMJsonSourceProvider(args.source_json)
    else:
        source_provider = create_source_provider(
            source_type=args.source_type,
            source_language=args.language or "en",
        )
    lessons = source_provider.fetch_lessons(
        args.lesson_start or pipeline_config.lesson_min,
        args.lesson_end or pipeline_config.lesson_max,
    )
    print(f"Loaded {len(lessons)} lessons from source")

    if not args.dry_run:
        print("Analyzing lessons...")
        profiles = []
        for lesson in lessons:
            profile = analyze_lesson(lesson, llm)
            profiles.append(profile)
        profile_path = output_dir / "profiles.json"
        dump_json(profile_path, profiles)
        print(f"  Profiles saved to {profile_path}")

    csv_path = args.csv or "outputs/acim_playlist/suno_metadata_songs.csv"
    styles = extract_and_normalize_styles_pipeline(csv_path, output_dir=str(output_dir / "styles"))
    print(f"Loaded {len(styles)} styles")

    if len(lessons) < len(styles):
        print(f"Fewer lessons ({len(lessons)}) than styles ({len(styles)}): relaxing constraints")
        assignment_config.minimum_style_usage = 0
        assignment_config.maximum_style_usage = max(1, len(lessons))
        assignment_config.maximum_consecutive_primary_bucket = max(len(lessons), 3)
        if len(lessons) <= 10:
            assignment_config.minimum_exact_style_gap = 0

    if args.dry_run:
        print("DRY RUN: Skipping LLM scoring, using mock scores...")
        from .scorer import filter_scores_for_optimizer

        mock_scores = [
            CompatibilityScore(
                lesson_number=l.lesson_number,
                style_id=s.style_id,
                total=7.0,
                dimensions={
                    "theme": 7.0,
                    "energy": 7.0,
                    "density": 7.0,
                    "repetition": 7.0,
                    "clarity": 7.0,
                    "arc": 7.0,
                    "form": 7.0,
                },
            )
            for l in lessons
            for s in styles
        ]
        scores = filter_scores_for_optimizer(mock_scores, lessons, styles)
    else:
        print("Computing compatibility scores...")
        scores = compute_compatibility_scores(
            lessons, styles, llm, cache_dir=str(output_dir / "scores")
        )
    print(f"  {len(scores)} scores computed")

    print("Running global optimizer...")
    assignments = optimize_assignments(
        lessons,
        styles,
        scores,
        assignment_config,
        assignment_version="scipy-milp-0.1.0",
    )
    report = validate_assignment_batch(assignments, styles, assignment_config)
    if not report.passed:
        print(f"WARNING: Assignment validation failed: {report.model_dump(mode='json')}")
        return 2

    manifest = AssignmentManifest(
        manifest_version="1.0",
        generated_at=datetime.now(UTC).isoformat(),
        assignments=assignments,
        constraints=assignment_config,
    )
    manifest_path = output_dir / "assignments" / "assignment_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"  Manifest saved to {manifest_path}")

    style_by_id = {s.style_id: s for s in styles}
    assign_by_lesson = {(a.lesson_number, a.language): a for a in assignments}

    if not args.dry_run:
        print("Planning lyrics...")
        plans = []
        for lesson in lessons:
            match = assign_by_lesson.get((lesson.lesson_number, lesson.language))
            if not match:
                continue
            profile_matches = [p for p in profiles if p.lesson_number == lesson.lesson_number]
            profile = profile_matches[0] if profile_matches else None
            archetype = (
                profile.ranked_archetypes[0]
                if (profile and profile.ranked_archetypes)
                else SongArchetype.TITLE_TEACHING_PRAYER
            )
            plan = create_lyric_plan(lesson, archetype, llm)
            plans.append(plan)
        dump_json(output_dir / "plans.json", plans)

        print("Adapting styles...")
        adaptations = []
        for lesson in lessons:
            match = assign_by_lesson.get((lesson.lesson_number, lesson.language))
            if not match:
                continue
            style = style_by_id.get(match.style_id)
            if not style:
                continue
            plan_matches = [
                p
                for p in plans
                if p.lesson_number == lesson.lesson_number and p.language == lesson.language
            ]
            plan = plan_matches[0] if plan_matches else None
            adaptation = create_style_adaptation(lesson, style, plan, llm)
            adaptations.append(adaptation)
        dump_json(output_dir / "adaptations.json", adaptations)

        print("Generating lyrics...")
        artifacts = []
        for lesson in lessons:
            plan_matches = [
                p
                for p in plans
                if p.lesson_number == lesson.lesson_number and p.language == lesson.language
            ]
            adapt_matches = [a for a in adaptations if a.lesson_number == lesson.lesson_number]
            plan = plan_matches[0] if plan_matches else None
            adaptation = adapt_matches[0] if adapt_matches else None
            if not (plan and adaptation):
                continue
            artifact = generate_song(lesson, plan, adaptation, llm)
            artifacts.append(artifact)
        dump_json(output_dir / "artifacts.json", artifacts)

        print("Validating and exporting...")
        reports_list = []
        for art in artifacts:
            lesson = next((l for l in lessons if l.lesson_number == art.lesson_number), None)
            if lesson:
                reports_list.append(
                    validate_verbatim_lyrics(art.full_lyrics_text, lesson.source_text)
                )
            else:
                reports_list.append(ValidationReport(passed=True))

        export_suno_batch(artifacts, reports_list, output_dir=str(output_dir / "exports"))
    else:
        print("DRY RUN: Pipeline complete (no lyrics generated)")
        print(f"  Lessons: {len(lessons)}")
        print(f"  Styles: {len(styles)}")
        print(f"  Assignments: {len(assignments)}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="acim-suno")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # audit-csv
    audit = subparsers.add_parser("audit-csv")
    audit.add_argument("--csv", default="outputs/acim_playlist/suno_metadata_songs.csv")
    audit.add_argument("--min-lesson", type=int, default=290)
    audit.add_argument("--max-lesson", type=int, default=361)
    audit.set_defaults(handler=command_audit_csv)

    # extract-styles
    extract = subparsers.add_parser("extract-styles")
    extract.add_argument("--csv", required=True)
    extract.add_argument("--out", default="outputs/styles/raw_styles.json")
    extract.add_argument("--min-lesson", type=int, default=290)
    extract.add_argument("--max-lesson", type=int, default=361)
    extract.add_argument(
        "--normalize", action="store_true", help="Also normalize and write review queue"
    )
    extract.set_defaults(handler=command_extract_styles)

    # normalize-styles
    normalize = subparsers.add_parser("normalize-styles")
    normalize.add_argument("--input", required=True)
    normalize.add_argument("--out", default="outputs/styles/normalized_styles.json")
    normalize.add_argument("--version", default="0.1.0")
    normalize.set_defaults(handler=command_normalize_styles)

    # ingest-sources
    ingest = subparsers.add_parser("ingest-sources")
    ingest.add_argument("--source-type", default="pinecone",
                        choices=["pinecone", "acim_json"])
    ingest.add_argument("--json", help="Path to ACIM JSON file (required for acim_json source)")
    ingest.add_argument("--language", default="en")
    ingest.add_argument("--out", default="outputs/lessons.json")
    ingest.add_argument("--min-lesson", type=int, default=116)
    ingest.add_argument("--max-lesson", type=int, default=199)
    ingest.set_defaults(handler=command_ingest_sources)

    # analyze-lessons
    analyze = subparsers.add_parser("analyze-lessons")
    analyze.add_argument("--input", required=True)
    analyze.add_argument("--out", default="outputs/profiles.json")
    analyze.add_argument("--provider", default="mock")
    analyze.add_argument("--model")
    analyze.add_argument("--prompt-version", default="0.1.0")
    analyze.set_defaults(handler=command_analyze_lessons)

    # score-compatibility
    score = subparsers.add_parser("score-compatibility")
    score.add_argument("--lessons", required=True)
    score.add_argument("--styles", required=True)
    score.add_argument("--out", default="outputs/scores/compatibility.jsonl")
    score.add_argument("--cache-dir", default="outputs/scores")
    score.add_argument("--provider", default="mock")
    score.add_argument("--model")
    score.add_argument("--prompt-version", default="0.1.0")
    score.add_argument("--force", action="store_true")
    score.set_defaults(handler=command_score_compatibility)

    # optimize
    optimize = subparsers.add_parser("optimize")
    optimize.add_argument("--lessons", required=True)
    optimize.add_argument("--styles", required=True)
    optimize.add_argument("--scores", required=True)
    optimize.add_argument("--config", required=True)
    optimize.add_argument("--out", default="outputs/assignments/assignment_manifest.json")
    optimize.set_defaults(handler=command_optimize)

    # plan-lyrics
    plan = subparsers.add_parser("plan-lyrics")
    plan.add_argument("--lessons", required=True)
    plan.add_argument("--profiles", required=True)
    plan.add_argument("--out", default="outputs/plans.json")
    plan.add_argument("--provider", default="mock")
    plan.add_argument("--model")
    plan.add_argument("--prompt-version", default="0.1.0")
    plan.set_defaults(handler=command_plan_lyrics)

    # adapt-styles
    adapt = subparsers.add_parser("adapt-styles")
    adapt.add_argument("--lessons", required=True)
    adapt.add_argument("--plans", required=True)
    adapt.add_argument("--styles", required=True)
    adapt.add_argument("--assignments", required=True)
    adapt.add_argument("--out", default="outputs/adaptations.json")
    adapt.add_argument("--provider", default="mock")
    adapt.add_argument("--model")
    adapt.add_argument("--prompt-version", default="0.1.0")
    adapt.set_defaults(handler=command_adapt_styles)

    # generate-lyrics
    gen = subparsers.add_parser("generate-lyrics")
    gen.add_argument("--lessons", required=True)
    gen.add_argument("--plans", required=True)
    gen.add_argument("--adaptations", required=True)
    gen.add_argument("--out", default="outputs/artifacts.json")
    gen.add_argument("--provider", default="mock")
    gen.add_argument("--model")
    gen.add_argument("--prompt-version", default="0.1.0")
    gen.set_defaults(handler=command_generate_lyrics)

    # validate
    validate = subparsers.add_parser("validate")
    validate.add_argument("--type", choices=["lyrics", "assignment", "style"], required=True)
    validate.add_argument("--source-file")
    validate.add_argument("--lyrics-file")
    validate.add_argument("--assignments")
    validate.add_argument("--styles")
    validate.add_argument("--adaptation")
    validate.add_argument("--config")
    validate.set_defaults(handler=command_validate)

    # repair
    repair = subparsers.add_parser("repair")
    repair.add_argument("--artifacts", required=True)
    repair.add_argument("--lessons", required=True)
    repair.add_argument("--out", default="outputs/repaired_artifacts.json")
    repair.add_argument("--provider", default="mock")
    repair.add_argument("--model")
    repair.add_argument("--prompt-version", default="0.1.0")
    repair.set_defaults(handler=command_repair)

    # export
    export = subparsers.add_parser("export")
    export.add_argument("--artifacts", required=True)
    export.add_argument("--lessons")
    export.add_argument("--out", default="outputs/exports")
    export.add_argument("--lesson-folders", action="store_true")
    export.set_defaults(handler=command_export)

    # run-batch
    batch = subparsers.add_parser("run-batch")
    batch.add_argument("--config", default="config/pipeline.example.yaml")
    batch.add_argument("--provider", default="mock")
    batch.add_argument("--model")
    batch.add_argument("--source-type", default="pinecone",
                        choices=["pinecone", "acim_json"])
    batch.add_argument("--source-json", help="Path to ACIM JSON file (required for acim_json)")
    batch.add_argument("--language", default="en")
    batch.add_argument("--csv", default="outputs/acim_playlist/suno_metadata_songs.csv")
    batch.add_argument("--lesson-start", type=int, default=116)
    batch.add_argument("--lesson-end", type=int, default=120)
    batch.add_argument("--output-dir", default="outputs")
    batch.add_argument("--dry-run", action="store_true", help="Skip LLM calls, use mock scores")
    batch.set_defaults(handler=command_run_batch)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (ValueError, AssignmentError, FileNotFoundError) as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
