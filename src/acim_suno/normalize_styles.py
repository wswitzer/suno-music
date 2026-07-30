from __future__ import annotations

import json
import re
from pathlib import Path

from .models import StyleRecord

BPM_PATTERN = re.compile(r"(?<!\d)(\d{2,3})\s*BPM\b", re.IGNORECASE)
ENERGY_KW = {
    "high": ["energetic", "upbeat", "driving", "powerful", "intense", "punchy", "high energy", "loud", "bright"],
    "low": ["ambient", "soft", "gentle", "mellow", "calm", "quiet", "minimal", "sparse", "intimate", "dreamy"],
}

DENSITY_KW = {
    "low": ["minimal", "sparse", "ambient", "simple", "open", "space", "silence"],
    "high": ["dense", "complex", "layered", "orchestral", "wall of sound", "intricate", "busy"],
}

SPOKEN_KW = ["spoken word", "narrative", "instructional", "guided", "spoken", "storytelling"]

REPETITION_KW = ["chant", "mantra", "repetitive", "loop", "hypnotic", "drone", "ostinato"]

CLARITY_KW = ["clear vocal", "articulate", "diction", "pronounced", "clean vocal", "crisp"]

RISK_PATTERNS = [
    (r"\bwhisper\b", "whisper full lesson"),
    (r"\b(repeat|echo|call)\b.*\btitle\b", "repeat title"),
    (r"\b(very\s+)?fast\b", "fast tempo may reduce clarity"),
    (r"\b(spoken|narrative).*long\b", "long spoken may exceed limits"),
]


def _extract_bpm(text: str) -> tuple[int | None, int | None]:
    values = [int(m) for m in BPM_PATTERN.findall(text)]
    if not values:
        return None, None
    return min(values), max(values)


def _classify_energy(text: str, tags: list[str]) -> float:
    lower = text.lower()
    for kw in ENERGY_KW["high"]:
        if kw in lower:
            return 0.8
    for kw in ENERGY_KW["low"]:
        if kw in lower:
            return 0.3
    for tag in tags:
        if tag.lower() in [t.lower() for t in ENERGY_KW["high"]]:
            return 0.8
        if tag.lower() in [t.lower() for t in ENERGY_KW["low"]]:
            return 0.3
    return 0.5


def _detect_lyric_density(text: str) -> str:
    lower = text.lower()
    for kw in DENSITY_KW["high"]:
        if kw in lower:
            return "high"
    for kw in DENSITY_KW["low"]:
        if kw in lower:
            return "low"
    return "medium"


def _detect_risks(text: str) -> list[str]:
    risks = []
    for pattern, risk in RISK_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            risks.append(risk)
    return risks


def _infer_bucket(text: str) -> str:
    lower = text.lower()
    bucket_map = [
        (r"\b(ambient|atmospheric|ethereal|dream|drone|space)\b", "atmospheric"),
        (r"\b(acoustic|folk|singer.songwriter|nylon|fingerpick)\b", "acoustic"),
        (r"\b(rock|electric|guitar.*riff|swamp|psychedelic|indie.*rock)\b", "rock"),
        (r"\b(pop|indie.*pop|synth.*pop|dream.*pop)\b", "pop"),
        (r"\b(soul|neo.soul|rnb|rhodes|warm.*vocal)\b", "soul"),
        (r"\b(latin|bachata|salsa|samba|tropical|bossa|reggaeton|soukous|cumbia)\b", "latin"),
        (r"\b(jazz|blues|bossa.*nova|swing)\b", "jazz"),
        (r"\b(hip.hop|rap|trap|boom.bap|dembow)\b", "hiphop"),
        (r"\b(electronic|house|techno|downtempo|electronica|synth|filter|beat)\b", "electronic"),
        (r"\b(chant|sacred|holy|gospel|choir|hymn|worship|devotional)\b", "sacred"),
        (r"\b(afrobeat|highlife|soukous|congolese)\b", "african"),
        (r"\b(flamenco|spanish.*guitar)\b", "world"),
        (r"\b(funk|groove|bass)\b", "funk"),
        (r"\b(minimal|experimental|avant)\b", "experimental"),
    ]
    for pattern, bucket in bucket_map:
        if re.search(pattern, lower):
            return bucket
    return "unclassified"


def _infer_tags(text: str) -> list[str]:
    genre_tags = ["acoustic", "electronic", "ambient", "folk", "rock", "pop", "soul", "jazz",
                  "latin", "hiphop", "sacred", "world", "funk", "experimental", "orchestral",
                  "r&b", "blues", "reggae", "country", "punk", "metal", "classical"]
    found = []
    lower = text.lower()
    for tag in genre_tags:
        if tag in lower:
            found.append(tag)
    if re.search(r"\b(male|female|vocal|singer|choir)\b", lower):
        found.append("vocal")
    if re.search(r"\b(instrumental|no vocal)\b", lower):
        found.append("instrumental")
    if re.search(r"\b(beat|drum|percussion|rhythm)\b", lower):
        found.append("percussive")
    return sorted(set(found))


def normalize_styles(
    styles: list[StyleRecord],
    *,
    registry_version: str = "0.1.0",
) -> list[StyleRecord]:
    for style in styles:
        text = style.core_prompt

        bpm_min, bpm_max = _extract_bpm(text)
        if bpm_min is not None:
            style.tempo_min = bpm_min
            style.tempo_max = bpm_max or bpm_min

        style.energy = _classify_energy(text, style.tags)
        style.lyric_density = _detect_lyric_density(text)
        style.risks = _detect_risks(text)
        style.primary_bucket = _infer_bucket(text)

        if not style.tags:
            style.tags = _infer_tags(text)

        lower = text.lower()
        if any(kw in lower for kw in SPOKEN_KW):
            style.spoken_word_support = min(1.0, style.spoken_word_support + 0.3)
        if any(kw in lower for kw in REPETITION_KW):
            style.repetition_affinity = min(1.0, style.repetition_affinity + 0.3)
        if any(kw in lower for kw in CLARITY_KW):
            style.vocal_clarity = min(1.0, style.vocal_clarity + 0.3)

        if "spoken word" in lower:
            style.mutable_traits.append("spoken_word_amount")
        if "tempo" in lower or "bpm" in lower:
            style.mutable_traits.append("bpm")
            style.locked_traits.append("overall_feel")

        if style.primary_bucket == "unclassified":
            style.risks.append("unclassified_bucket_needs_review")

    return styles


def extract_and_normalize_styles_pipeline(
    csv_path: str | Path,
    *,
    min_lesson: int = 290,
    max_lesson: int = 361,
    output_dir: str | Path = "outputs/styles",
    registry_version: str = "0.1.0",
) -> list[StyleRecord]:
    from .extract_styles import extract_styles_from_csv

    raw = extract_styles_from_csv(csv_path, min_lesson=min_lesson, max_lesson=max_lesson)
    normalized = normalize_styles(raw, registry_version=registry_version)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    raw_path = out / "raw_styles.json"
    normalized_path = out / "normalized_styles.json"
    review_path = out / "style_review_queue.json"

    raw_path.write_text(
        json.dumps([s.model_dump(mode="json") for s in raw], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    normalized_path.write_text(
        json.dumps([s.model_dump(mode="json") for s in normalized], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    needs_review = [s.model_dump(mode="json") for s in normalized
                    if "unclassified_bucket_needs_review" in s.risks]
    review_path.write_text(
        json.dumps(needs_review, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return normalized
