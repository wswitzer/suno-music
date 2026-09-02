from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from acim_suno.cli import command_run_batch


def _write_synthetic_text_source(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "language": "en",
                "chapters": {
                    "27": {
                        "sections": {
                            "I": {
                                "title": "Synthetic section one",
                                "paragraphs": [
                                    {
                                        "reference": "T-27.I.1",
                                        "number": 1,
                                        "sentences": [
                                            {"number": 1, "text": "First synthetic teaching."},
                                            {"number": 2, "text": "Second synthetic teaching."},
                                        ],
                                    }
                                ],
                                "subsections": {},
                            },
                            "II": {
                                "title": "Synthetic section two",
                                "paragraphs": [
                                    {
                                        "reference": "T-27.II.1",
                                        "number": 1,
                                        "sentences": [
                                            {"number": 1, "text": "Third synthetic teaching."}
                                        ],
                                    }
                                ],
                                "subsections": {},
                            },
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def _write_styles(path: Path) -> None:
    path.write_text(
        "lesson_number,title,styles_raw\n"
        "295,One,Warm acoustic folk with clear vocal\n"
        "296,Two,Upbeat latin percussion with clear vocal\n"
        "297,Three,Electronic soul with rhythmic pulse\n",
        encoding="utf-8",
    )


def _batch_args(source_path: Path, styles_csv: Path, output_dir: Path, *, dry_run: bool) -> Namespace:
    return Namespace(
        config="config/pipeline.example.yaml",
        provider="mock",
        model=None,
        book="text",
        source_type="acim_json",
        source_json=str(source_path),
        language="en",
        csv=str(styles_csv),
        chapter=27,
        lesson_start=116,
        lesson_end=120,
        output_dir=str(output_dir),
        dry_run=dry_run,
    )


def test_text_run_batch_dry_run_assigns_one_style_per_section(tmp_path: Path) -> None:
    source_path = tmp_path / "text.json"
    styles_csv = tmp_path / "styles.csv"
    _write_synthetic_text_source(source_path)
    _write_styles(styles_csv)

    output_dir = tmp_path / "chapter_27"
    result = command_run_batch(_batch_args(source_path, styles_csv, output_dir, dry_run=True))

    assert result == 0
    manifest = json.loads(
        (output_dir / "assignments" / "assignment_manifest.json").read_text(encoding="utf-8")
    )
    assignments = manifest["assignments"]
    assert [item["unit_ref"] for item in assignments] == ["T-27.I", "T-27.II"]
    assert len({item["style_id"] for item in assignments}) == 2


def test_text_run_batch_mock_reaches_validated_exports(tmp_path: Path) -> None:
    source_path = tmp_path / "text.json"
    styles_csv = tmp_path / "styles.csv"
    _write_synthetic_text_source(source_path)
    _write_styles(styles_csv)

    output_dir = tmp_path / "chapter_27"
    result = command_run_batch(_batch_args(source_path, styles_csv, output_dir, dry_run=False))

    assert result == 0
    artifacts = json.loads((output_dir / "artifacts.json").read_text(encoding="utf-8"))
    assert [artifact["unit_ref"] for artifact in artifacts] == ["T-27.I", "T-27.II"]
    assert all(artifact["lesson_number"] is None for artifact in artifacts)

    batch = json.loads((output_dir / "exports" / "batch_export.json").read_text(encoding="utf-8"))
    assert batch["passed_count"] == 2
    assert batch["failed_count"] == 0
    assert (output_dir / "sections" / "T-27.I" / "lyrics.txt").exists()
    assert (output_dir / "sections" / "T-27.II" / "artifact.json").exists()
