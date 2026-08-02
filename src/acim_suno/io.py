from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel, TypeAdapter

T = TypeVar("T", bound=BaseModel)


def load_env(dotenv_paths: tuple[str, ...] = (".env", "../.env")) -> None:
    """Load KEY=VALUE pairs from .env files without overwriting existing vars."""
    for candidate in dotenv_paths:
        path = Path(candidate)
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"").strip()
            if key and key not in os.environ:
                os.environ[key] = value


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_models(path: str | Path, model_type: type[T]) -> list[T]:
    return TypeAdapter(list[model_type]).validate_python(load_json(path))


def load_jsonl_models(path: str | Path, model_type: type[T]) -> list[T]:
    records: list[T] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(model_type.model_validate(json.loads(line)))
            except Exception as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
    return records


def dump_json(path: str | Path, values: list[BaseModel]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = [value.model_dump(mode="json") for value in values]
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}
