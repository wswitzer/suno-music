from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from .models import (
    BatchExport,
    FinalSongArtifact,
    SongArtifact,
    ValidationReport,
)


def convert_to_final_artifact(
    song: SongArtifact,
    report: ValidationReport | None = None,
    repair_count: int = 0,
) -> FinalSongArtifact:
    return FinalSongArtifact(
        lesson_number=song.lesson_number,
        language=song.language,
        title=song.title,
        style_id=song.style_id,
        style_prompt=song.style_adaptation.final_prompt,
        lyrics=song.full_lyrics_text,
        archetype=song.archetype.value,
        lesson_type=song.lesson_type.value,
        source_hash=song.source_hash,
        assignment_version=song.assignment_version,
        generator_version=song.generator_version,
        repair_count=repair_count,
        passed_validation=report.passed if report else True,
    )


def export_suno_batch(
    songs: list[SongArtifact],
    reports: list[ValidationReport] | None = None,
    *,
    output_dir: str | Path = "outputs/exports",
    export_version: str = "0.1.0",
) -> BatchExport:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if reports is not None:
        artifacts = [
            convert_to_final_artifact(song, report)
            for song, report in zip(songs, reports, strict=False)
        ]
    else:
        artifacts = [convert_to_final_artifact(s) for s in songs]

    passed_count = sum(1 for a in artifacts if a.passed_validation)
    failed_count = len(artifacts) - passed_count

    batch = BatchExport(
        export_version=export_version,
        generated_at=datetime.now(UTC).isoformat(),
        songs=artifacts,
        total_lessons=len(artifacts),
        passed_count=passed_count,
        failed_count=failed_count,
    )

    jsonl_path = out_dir / "complete_artifacts.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for song in artifacts:
            f.write(json.dumps(song.model_dump(mode="json"), ensure_ascii=False) + "\n")

    csv_path = out_dir / "suno_batch.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "lesson_number",
                "title",
                "archetype",
                "style_id",
                "style_prompt",
                "lyrics",
                "source_hash",
                "passed_validation",
            ],
        )
        writer.writeheader()
        for song in artifacts:
            writer.writerow(
                {
                    "lesson_number": song.lesson_number,
                    "title": song.title,
                    "archetype": song.archetype,
                    "style_id": song.style_id,
                    "style_prompt": song.style_prompt,
                    "lyrics": song.lyrics,
                    "source_hash": song.source_hash,
                    "passed_validation": str(song.passed_validation),
                }
            )

    batch_json_path = out_dir / "batch_export.json"
    batch_json_path.write_text(
        json.dumps(batch.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Exported {len(artifacts)} songs to {out_dir}")
    print(f"  CSV: {csv_path}")
    print(f"  JSONL: {jsonl_path}")
    print(f"  Passed: {passed_count}, Failed: {failed_count}")

    return batch


def export_lesson_folder(
    song: SongArtifact,
    report: ValidationReport | None = None,
    *,
    output_dir: str | Path = "outputs/lessons",
) -> Path:
    lesson_dir = Path(output_dir) / f"lesson_{song.lesson_number:03d}"
    lesson_dir.mkdir(parents=True, exist_ok=True)

    lyrics_path = lesson_dir / "lyrics.txt"
    lyrics_path.write_text(song.full_lyrics_text, encoding="utf-8")

    artifact_path = lesson_dir / "artifact.json"
    artifact_path.write_text(
        json.dumps(
            convert_to_final_artifact(song, report).model_dump(mode="json"),
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    return lesson_dir
