from __future__ import annotations

import argparse
import json
from pathlib import Path

from .extract_styles import extract_styles_from_csv
from .io import dump_json, load_jsonl_models, load_models, load_yaml
from .models import (
    AssignmentConstraints,
    CompatibilityScore,
    LessonRecord,
    StyleRecord,
)
from .optimizer import AssignmentError, optimize_assignments
from .validators import validate_assignment_batch, validate_verbatim_lyrics


def command_extract_styles(args: argparse.Namespace) -> int:
    styles = extract_styles_from_csv(
        args.csv,
        min_lesson=args.min_lesson,
        max_lesson=args.max_lesson,
    )
    dump_json(args.out, styles)
    print(f"Extracted {len(styles)} unique styles to {args.out}")
    return 0


def command_optimize(args: argparse.Namespace) -> int:
    lessons = load_models(args.lessons, LessonRecord)
    styles = load_models(args.styles, StyleRecord)
    scores = load_jsonl_models(args.scores, CompatibilityScore)
    config = load_yaml(args.config)
    constraints = AssignmentConstraints.model_validate(config.get("assignment", {}))
    version = config.get("versions", {}).get(
        "assignment_algorithm", "scipy-milp-0.1.0"
    )
    assignments = optimize_assignments(
        lessons,
        styles,
        scores,
        constraints,
        assignment_version=version,
    )
    report = validate_assignment_batch(assignments, styles, constraints)
    if not report.passed:
        raise AssignmentError(json.dumps(report.model_dump(mode="json"), indent=2))
    dump_json(args.out, assignments)
    print(f"Wrote {len(assignments)} assignments to {args.out}")
    return 0


def command_validate_lyrics(args: argparse.Namespace) -> int:
    source = Path(args.source_file).read_text(encoding="utf-8")
    lyrics = Path(args.lyrics_file).read_text(encoding="utf-8")
    report = validate_verbatim_lyrics(lyrics, source)
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0 if report.passed else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="acim-suno")
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract = subparsers.add_parser("extract-styles")
    extract.add_argument("--csv", required=True)
    extract.add_argument("--out", required=True)
    extract.add_argument("--min-lesson", type=int, default=290)
    extract.add_argument("--max-lesson", type=int, default=361)
    extract.set_defaults(handler=command_extract_styles)

    optimize = subparsers.add_parser("optimize")
    optimize.add_argument("--lessons", required=True)
    optimize.add_argument("--styles", required=True)
    optimize.add_argument("--scores", required=True)
    optimize.add_argument("--config", required=True)
    optimize.add_argument("--out", required=True)
    optimize.set_defaults(handler=command_optimize)

    validate = subparsers.add_parser("validate-lyrics")
    validate.add_argument("--source-file", required=True)
    validate.add_argument("--lyrics-file", required=True)
    validate.set_defaults(handler=command_validate_lyrics)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (ValueError, AssignmentError) as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
