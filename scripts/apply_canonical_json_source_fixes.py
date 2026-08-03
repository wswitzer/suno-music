from __future__ import annotations

from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 match, found {count}")
    return text.replace(old, new, 1)


def replace_between(text: str, start: str, end: str, replacement: str, label: str) -> str:
    start_idx = text.find(start)
    if start_idx < 0:
        raise RuntimeError(f"{label}: start marker not found")
    end_idx = text.find(end, start_idx)
    if end_idx < 0:
        raise RuntimeError(f"{label}: end marker not found")
    return text[:start_idx] + replacement + text[end_idx:]


def patch_sources() -> None:
    path = "src/acim_suno/sources.py"
    text = read(path)
    start = "class ACIMJsonSourceProvider:\n"
    end = "REVIEW_LESSON_RANGES ="
    replacement = '''class ACIMJsonSourceProvider:\n    """Canonical structured workbook source provider.\n\n    The enhanced JSON is the deterministic source for generation and validation.\n    Editorial numbering/reference metadata is intentionally excluded from\n    ``SourceSentence.text``; only clean authorial text is exposed to lyric stages.\n    """\n\n    def __init__(\n        self,\n        json_path: str | Path,\n        *,\n        source_language: str = "en",\n    ) -> None:\n        self._path = Path(json_path)\n        with self._path.open("r", encoding="utf-8") as f:\n            self._data = json.load(f)\n        declared_language = self._declared_language()\n        if declared_language is not None and declared_language != source_language:\n            raise ValueError(\n                f"Source declares language {declared_language!r}, not {source_language!r}"\n            )\n        self._source_language = source_language\n        self._source_hash = self._compute_hash()\n\n    def _declared_language(self) -> str | None:\n        for key in ("language", "lang", "source_language"):\n            value = self._data.get(key)\n            if isinstance(value, str) and value.strip():\n                return value.strip()\n        metadata = self._data.get("metadata")\n        if isinstance(metadata, dict):\n            for key in ("language", "lang", "source_language"):\n                value = metadata.get(key)\n                if isinstance(value, str) and value.strip():\n                    return value.strip()\n        return None\n\n    def _compute_hash(self) -> str:\n        return hashlib.sha256(self._path.read_bytes()).hexdigest()\n\n    def get_source_hash(self) -> str:\n        """Return the complete source-file identity hash."""\n        return self._source_hash\n\n    def fetch_lessons(\n        self,\n        start: int = 116,\n        end: int = 199,\n        language: str = "en",\n    ) -> list[LessonRecord]:\n        if language != self._source_language:\n            raise ValueError(\n                f"Source provider is bound to {self._source_language!r}; requested {language!r}"\n            )\n        parts = self._data.get("parts", {})\n        all_lessons: dict[str, dict] = {}\n        for part in parts.values():\n            lesson_dict = part.get("lessons", {})\n            for key, value in lesson_dict.items():\n                if key not in all_lessons:\n                    all_lessons[key] = value\n\n        missing = [num for num in range(start, end + 1) if str(num) not in all_lessons]\n        if missing:\n            preview = ", ".join(str(num) for num in missing[:10])\n            raise ValueError(\n                f"JSON source is missing {len(missing)} requested lesson(s): {preview}"\n            )\n\n        records: list[LessonRecord] = []\n        for num in range(start, end + 1):\n            raw = all_lessons[str(num)]\n            title = raw.get("title_clean") or raw.get("title", "") or f"Lesson {num}"\n            paragraphs = raw.get("paragraphs", [])\n            practice_raw = raw.get("practice_instructions", {})\n            practice_instructions: dict[str, str] = {}\n            if isinstance(practice_raw, dict):\n                for key, value in practice_raw.items():\n                    if isinstance(value, str):\n                        practice_instructions[key] = value\n                    elif isinstance(value, (list, dict)):\n                        practice_instructions[key] = json.dumps(value, ensure_ascii=False)\n\n            reviewed = raw.get("reviewed_lessons")\n            is_review = _is_review_lesson(num) or reviewed is not None\n            is_experiential = any(\n                marker in title.lower()\n                for marker in ("stillness", "quiet", "experiential", "meditation")\n            )\n            if is_review:\n                lesson_type = LessonType.REVIEW\n            elif is_experiential:\n                lesson_type = LessonType.EXPERIENTIAL\n            else:\n                lesson_type = LessonType.STANDARD\n\n            paragraph_texts = self._extract_paragraph_texts(paragraphs)\n            sentences = self._build_sentences(raw, num)\n            lesson_source_hash = self._lesson_hash(\n                lesson_number=num,\n                language=language,\n                title=title,\n                sentences=sentences,\n                paragraphs=paragraph_texts,\n                practice_instructions=practice_instructions,\n                reviewed_lessons=reviewed,\n            )\n\n            records.append(\n                LessonRecord(\n                    lesson_number=num,\n                    language=language,\n                    title=title,\n                    lesson_type=lesson_type,\n                    source=SourceMetadata(\n                        edition="acim-workbook-enhanced",\n                        url=f"file://{self._path}",\n                        source_hash=lesson_source_hash,\n                        rights_status="review_required",\n                    ),\n                    sentences=sentences,\n                    paragraphs=paragraph_texts,\n                    practice_instructions=practice_instructions,\n                    reviewed_lessons=reviewed,\n                )\n            )\n        return records\n\n    def _extract_paragraph_texts(self, paragraphs: list) -> list[str]:\n        texts: list[str] = []\n        if not isinstance(paragraphs, list):\n            return texts\n        for paragraph in paragraphs:\n            if isinstance(paragraph, str):\n                if paragraph.strip():\n                    texts.append(paragraph.strip())\n                continue\n            if not isinstance(paragraph, dict):\n                continue\n            sentence_texts = self._extract_atomic_paragraph_sentences([paragraph])\n            if sentence_texts:\n                texts.append(" ".join(sentence_texts))\n                continue\n            direct_text = paragraph.get("text")\n            if isinstance(direct_text, str) and direct_text.strip():\n                texts.append(direct_text.strip())\n        return texts\n\n    def _extract_atomic_paragraph_sentences(self, paragraphs: object) -> list[str]:\n        texts: list[str] = []\n        if not isinstance(paragraphs, list):\n            return texts\n        for paragraph in paragraphs:\n            if isinstance(paragraph, str):\n                if paragraph.strip():\n                    texts.append(paragraph.strip())\n                continue\n            if not isinstance(paragraph, dict):\n                continue\n            sentence_items = paragraph.get("sentences", [])\n            if isinstance(sentence_items, list):\n                for sentence in sentence_items:\n                    if isinstance(sentence, str) and sentence.strip():\n                        texts.append(sentence.strip())\n                    elif isinstance(sentence, dict):\n                        value = sentence.get("text")\n                        if isinstance(value, str) and value.strip():\n                            texts.append(value.strip())\n            if not sentence_items:\n                direct_text = paragraph.get("text")\n                if isinstance(direct_text, str) and direct_text.strip():\n                    texts.append(direct_text.strip())\n        return texts\n\n    def _build_sentences(self, raw: dict, lesson_number: int) -> list[SourceSentence]:\n        sentences: list[SourceSentence] = []\n        sentence_id_counter = 0\n\n        def add_sentence(text: str, category: str) -> None:\n            nonlocal sentence_id_counter\n            text = text.strip()\n            if not text:\n                return\n            sentence_id_counter += 1\n            sentences.append(\n                SourceSentence(\n                    sentence_id=f"L{lesson_number}_{sentence_id_counter:03d}",\n                    text=text,\n                    category=category,\n                )\n            )\n\n        title = raw.get("title_clean") or raw.get("title", "")\n        if isinstance(title, str) and title.strip():\n            add_sentence(title, "title")\n\n        idea = raw.get("idea_clean") or raw.get("idea", "")\n        if isinstance(idea, str) and idea.strip():\n            add_sentence(idea, "teaching")\n\n        for text in self._extract_atomic_paragraph_sentences(raw.get("paragraphs", [])):\n            add_sentence(text, "teaching")\n\n        practice_raw = raw.get("practice_instructions", {})\n        if isinstance(practice_raw, dict):\n            for field in ("description", "method"):\n                value = practice_raw.get(field, "")\n                if isinstance(value, str) and value.strip():\n                    add_sentence(value, "practice")\n\n        prayer = raw.get("prayer", "")\n        if isinstance(prayer, str) and prayer.strip():\n            add_sentence(prayer, "prayer")\n\n        if not sentences:\n            raise ValueError(f"Lesson {lesson_number} contains no canonical source text")\n        return sentences\n\n    def _lesson_hash(\n        self,\n        *,\n        lesson_number: int,\n        language: str,\n        title: str,\n        sentences: list[SourceSentence],\n        paragraphs: list[str],\n        practice_instructions: dict[str, str],\n        reviewed_lessons: object,\n    ) -> str:\n        payload = {\n            "lesson_number": lesson_number,\n            "language": language,\n            "title": title,\n            "sentences": [sentence.model_dump(mode="json") for sentence in sentences],\n            "paragraphs": paragraphs,\n            "practice_instructions": practice_instructions,\n            "reviewed_lessons": reviewed_lessons,\n        }\n        canonical = json.dumps(\n            payload,\n            sort_keys=True,\n            ensure_ascii=False,\n            separators=(",", ":"),\n        )\n        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()\n\n\n'''
    text = replace_between(text, start, end, replacement, "canonical JSON provider")
    write(path, text)


def patch_cli() -> None:
    path = "src/acim_suno/cli.py"
    text = read(path)
    text = text.replace("import json\n", "import json\nimport os\n", 1)

    old_ingest = '''def command_ingest_sources(args: argparse.Namespace) -> int:\n    if args.source_type == "acim_json":\n        if not args.json:\n            raise ValueError("--json is required for acim_json source type")\n        provider = ACIMJsonSourceProvider(args.json, source_language=args.language)\n    else:\n        provider = create_source_provider(\n            source_type=args.source_type, source_language=args.language\n        )\n    lessons = provider.fetch_lessons(args.min_lesson, args.max_lesson)\n'''
    new_ingest = '''def command_ingest_sources(args: argparse.Namespace) -> int:\n    if args.source_type == "acim_json":\n        source_json = args.json or os.environ.get("ACIM_WORKBOOK_JSON")\n        if not source_json:\n            raise ValueError(\n                "--json or ACIM_WORKBOOK_JSON is required for acim_json source type"\n            )\n        provider = ACIMJsonSourceProvider(\n            source_json, source_language=args.language\n        )\n    else:\n        provider = create_source_provider(\n            source_type=args.source_type, source_language=args.language\n        )\n    lessons = provider.fetch_lessons(\n        args.min_lesson, args.max_lesson, language=args.language\n    )\n'''
    text = replace_once(text, old_ingest, new_ingest, "ingest canonical source")

    old_batch_source = '''    if args.source_type == "acim_json":\n        if not args.source_json:\n            raise ValueError("--source-json required for acim_json source type")\n        source_provider = ACIMJsonSourceProvider(args.source_json)\n    else:\n        source_provider = create_source_provider(\n            source_type=args.source_type,\n            source_language=args.language or "en",\n        )\n    lessons = source_provider.fetch_lessons(\n        args.lesson_start or pipeline_config.lesson_min,\n        args.lesson_end or pipeline_config.lesson_max,\n    )\n'''
    new_batch_source = '''    source_language = args.language or "en"\n    if args.source_type == "acim_json":\n        source_json = args.source_json or os.environ.get("ACIM_WORKBOOK_JSON")\n        if not source_json:\n            raise ValueError(\n                "--source-json or ACIM_WORKBOOK_JSON required for acim_json source type"\n            )\n        source_provider = ACIMJsonSourceProvider(\n            source_json, source_language=source_language\n        )\n    else:\n        source_provider = create_source_provider(\n            source_type=args.source_type,\n            source_language=source_language,\n        )\n    lessons = source_provider.fetch_lessons(\n        args.lesson_start or pipeline_config.lesson_min,\n        args.lesson_end or pipeline_config.lesson_max,\n        language=source_language,\n    )\n'''
    text = replace_once(text, old_batch_source, new_batch_source, "run-batch canonical source")

    text = text.replace(
        'ingest.add_argument("--source-type", default="pinecone", choices=["pinecone", "acim_json"])',
        'ingest.add_argument("--source-type", default="acim_json", choices=["pinecone", "acim_json"])',
        1,
    )
    text = text.replace(
        'batch.add_argument("--source-type", default="pinecone", choices=["pinecone", "acim_json"])',
        'batch.add_argument("--source-type", default="acim_json", choices=["pinecone", "acim_json"])',
        1,
    )
    write(path, text)


def patch_llm() -> None:
    path = "src/acim_suno/llm.py"
    text = read(path)
    old = '''        + "\\n\\nSource sentences:\\n"\n        + "\\n".join(f"  {s.sentence_id}: {s.text}" for s in lesson.sentences)\n        + "\\n\\nProduce lyrics with [Section] headers and (ad-lib) directions."\n    )\n'''
    new = '''        + "\\n\\nSource sentences follow. The L###_### tokens are metadata labels only; "\n        "never output them as lyrics.\\n"\n        + "\\n".join(f"  {s.sentence_id}: {s.text}" for s in lesson.sentences)\n        + (\n            "\\n\\nProduce lyrics with [Section] headers. Exact contiguous source phrases may "\n            "be repeated, reordered, and interleaved as separate lyric lines or sections, "\n            "but never splice noncontiguous source spans into one new lyric phrase. "\n            "Never emit source IDs, workbook references (such as W-pI.*), paragraph/sentence "\n            "numbers, or editorial metadata unless those characters are themselves part of "\n            "the approved clean source text. Treatment markers such as (Spoken) or (Sung) "\n            "are metadata, not lyric content."\n        )\n    )\n'''
    text = replace_once(text, old, new, "lyric writer source-metadata contract")
    write(path, text)


def patch_repair() -> None:
    path = "src/acim_suno/repair.py"
    text = read(path)
    text = text.replace(
        "    GeneratedLyric,\n",
        "    GeneratedLyric,\n    GeneratedLyricsResponse,\n",
        1,
    )
    old = '''        result = llm.generate_structured(system_prompt, user_prompt, list[GeneratedLyric])\n        if result:\n            repaired_lyrics = result\n'''
    new = '''        result = llm.generate_structured(\n            system_prompt, user_prompt, GeneratedLyricsResponse\n        )\n        if result.root:\n            repaired_lyrics = result.root\n'''
    text = replace_once(text, old, new, "repair structured wrapper")
    old_prompt = '''            "For source failures, select a contiguous approved source phrase that matches. "\n            "Output JSON with repaired lyrics only."\n'''
    new_prompt = '''            "For source failures, select a contiguous approved source phrase that matches. "\n            "Separate exact source phrases into separate lyric lines rather than splicing "\n            "noncontiguous spans together. Never emit source IDs or editorial references. "\n            "Output JSON with repaired lyrics only."\n'''
    text = replace_once(text, old_prompt, new_prompt, "repair phrase contract")
    write(path, text)


def patch_prompts() -> None:
    path = "prompts/PIPELINE_PROMPTS.md"
    text = read(path)
    old = '''## Lyric writer\n\nWrite from the approved plan and source IDs. Under `verbatim_only`, every sung or spoken phrase—including parenthetical ad-libs—must occur contiguously in the source. Repetition and line-break changes are allowed; additions, substitutions, deletions, and word rearrangement are not. Use conservative Suno labels. Keep production prose in the style field, not the lyrics field.\n'''
    new = '''## Lyric writer\n\nWrite from the approved plan and source IDs. Under `verbatim_only`, every sung or spoken phrase—including parenthetical ad-libs—must occur contiguously in the source. Exact source phrases may be repeated, reordered, and interleaved at the arrangement level when each phrase remains its own valid source line or section; never fuse noncontiguous source spans into a new lyric phrase. Line-break changes are allowed within exact source wording; additions, substitutions, deletions, and word rearrangement within a phrase are not. Source IDs, workbook references, paragraph/sentence numbers, and editorial metadata are never lyrical content unless those characters are themselves present in the approved clean source. Use conservative Suno labels. Keep production prose in the style field, not the lyrics field.\n'''
    text = replace_once(text, old, new, "versioned lyric writer contract")
    write(path, text)


def patch_agents() -> None:
    path = "AGENTS.md"
    text = read(path)
    old_start = "## Source data access\n\n"
    old_end = "## Gemini LLM access (as configured in Album Creator)\n"
    replacement = '''## Source data access\n\nFor the deterministic English Workbook generation pipeline, the canonical source is the clean structured `workbook_enhanced.json` maintained by the separate `acim-core-data` project. Pass its local path with `--source-json` or `ACIM_WORKBOOK_JSON`; never hardcode a machine-specific path and never copy the copyrighted dataset into this public repository. `ACIMJsonSourceProvider` must expose clean authorial text only to generation/validation stages, with editorial numbering and workbook references treated as metadata.\n\nPinecone remains a secondary search/cross-check representation, not the canonical serialization for strict lyric generation. Reference `vector_database.md` in `acim-core-data` for API specs when semantic search or cross-checking is needed. Key Pinecone details:\n\n- **Index:** `acim-text` (host: `https://acim-text-e2xpwpt.svc.aped-4627-b74a.pinecone.io`)\n- **Region:** `us-east-1` (AWS Serverless)\n- **Dimension:** 768 dense float dimensions\n- **Metric:** Cosine / Dot Product\n- **Embedding model:** Google Gemini `models/gemini-embedding-001` with `outputDimensionality: 768`\n- **Namespaces:** `text` and `workbook`\n- **Filter by:** `{"lesson": {"$eq": <number>}}` with a dummy `[0.01] * 768` vector (`includeMetadata: true`)\n- **API key:** `PINECONE_API_KEY` environment variable\n- **Provider:** `PineconeSourceProvider` in `src/acim_suno/sources.py`\n\nUnder `verbatim_only`, exact source phrases may be arranged, repeated, or interleaved as separate lyric lines/sections, but words from noncontiguous source spans must never be fused into a new phrase.\n\n'''
    text = replace_between(text, old_start, old_end, replacement, "agent source strategy")
    write(path, text)


def patch_readme() -> None:
    path = "README.md"
    text = read(path)
    marker = "## Validate verbatim-only lyrics\n"
    addition = '''## Canonical workbook source\n\nFor deterministic English generation, use the clean structured `workbook_enhanced.json` from the separate `acim-core-data` project. Keep that file local and pass its path with `--source-json` or the `ACIM_WORKBOOK_JSON` environment variable; do not copy it into this public repository. Pinecone is retained for semantic search and cross-checking, but strict generation/validation should use the clean JSON representation so editorial numbering and references are not mistaken for lyric text.\n\n```bash\nACIM_WORKBOOK_JSON=/path/to/acim-core-data/workbook_enhanced.json \\\nacim-suno run-batch \\\n  --source-type acim_json \\\n  --language en \\\n  --lesson-start 116 \\\n  --lesson-end 125 \\\n  --provider gemini\n```\n\nUnder `verbatim_only`, exact source phrases may be repeated, reordered, and interleaved as separate lyric lines or sections. Combining words from noncontiguous source spans into a new phrase remains invalid.\n\n'''
    if addition not in text:
        text = text.replace(marker, addition + marker, 1)
    write(path, text)


def patch_verification_doc() -> None:
    path = "docs/verification_116_125.md"
    text = read(path)
    old = '''- Whether idea-interleaved refrains (L116/L117 outros) count as acceptable under\n  `verbatim_only`, and how L120's numbered output should be repaired/regenerated.\n'''
    new = '''- **Resolved policy:** musical interleaving is allowed at the arrangement level, but\n  each interleaved unit must remain its own exact contiguous source phrase/line.\n  L116/L117's fused outro lines therefore remain invalid and should be targeted-repaired\n  into separate exact source lines. L120 should be regenerated from the clean JSON source\n  before any special-case repair is considered.\n'''
    text = replace_once(text, old, new, "verification policy resolution")
    text += '''\n\n## Resolution adopted after review\n\n- Keep the strict validator unchanged.\n- Use `workbook_enhanced.json` through `ACIMJsonSourceProvider` as the canonical English generation/validation source; Pinecone is secondary.\n- Preserve clean paragraph sentences as atomic `SourceSentence` units.\n- Do not emit source IDs, editorial numbering, or workbook references as lyrics.\n- Re-run 116–125 from ingestion onward because source hashes/profiles/score caches change.\n'''
    write(path, text)


def patch_tests() -> None:
    path = "tests/test_pipeline.py"
    text = read(path)
    if "from acim_suno.repair import create_repair_request, repair_song" not in text:
        text = text.replace(
            "from acim_suno.planner import choose_archetype\n",
            "from acim_suno.planner import choose_archetype\n"
            "from acim_suno.repair import create_repair_request, repair_song\n",
            1,
        )

    addition = r'''\n\ndef _write_canonical_workbook(path: Path, *, second_text: str = "Do you want peace?") -> None:\n    payload = {\n        "language": "en",\n        "parts": {\n            "part_1": {\n                "lessons": {\n                    "122": {\n                        "title_clean": "Forgiveness offers everything I want.",\n                        "idea_clean": "Forgiveness offers everything I want.",\n                        "paragraphs": [\n                            {\n                                "sentences": [\n                                    {"number": 2, "text": "What could you want forgiveness cannot give?"},\n                                    {"number": 3, "text": second_text},\n                                    {"number": 4, "text": "Forgiveness offers it."},\n                                ]\n                            }\n                        ],\n                        "practice_instructions": {"description": "Remember this today."},\n                    },\n                    "123": {\n                        "title_clean": "I thank my Father for His gifts to me.",\n                        "paragraphs": [\n                            {"sentences": [{"number": 1, "text": "A different lesson sentence."}]}\n                        ],\n                    },\n                }\n            }\n        },\n    }\n    path.write_text(json.dumps(payload), encoding="utf-8")\n\n\ndef test_json_provider_uses_atomic_clean_sentences_and_per_lesson_hashes(tmp_path: Path) -> None:\n    source_path = tmp_path / "workbook_enhanced.json"\n    _write_canonical_workbook(source_path)\n    provider = ACIMJsonSourceProvider(source_path, source_language="en")\n    items = provider.fetch_lessons(122, 123, language="en")\n    lesson_122, lesson_123 = items\n\n    texts = [sentence.text for sentence in lesson_122.sentences]\n    assert "What could you want forgiveness cannot give?" in texts\n    assert "Do you want peace?" in texts\n    assert "Forgiveness offers it." in texts\n    assert all("W-pI." not in value for value in texts)\n    assert all(not re.match(r"^\\d+\\s", value) for value in texts)\n    assert lesson_122.source.source_hash != lesson_123.source.source_hash\n\n\ndef test_json_provider_hash_changes_with_canonical_lesson_text(tmp_path: Path) -> None:\n    source_path = tmp_path / "workbook_enhanced.json"\n    _write_canonical_workbook(source_path)\n    first = ACIMJsonSourceProvider(source_path).fetch_lessons(122, 122)[0]\n    _write_canonical_workbook(source_path, second_text="Would you have peace?")\n    second = ACIMJsonSourceProvider(source_path).fetch_lessons(122, 122)[0]\n    assert first.source.source_hash != second.source.source_hash\n\n\ndef test_json_provider_fails_when_requested_lesson_is_missing(tmp_path: Path) -> None:\n    source_path = tmp_path / "workbook_enhanced.json"\n    _write_canonical_workbook(source_path)\n    provider = ACIMJsonSourceProvider(source_path)\n    with pytest.raises(ValueError, match="missing 1 requested lesson"):\n        provider.fetch_lessons(122, 124)\n\n\ndef test_verbatim_allows_arrangement_interleaving_but_not_phrase_splicing() -> None:\n    source = "First exact phrase. Intervening teaching. Second exact phrase."\n    separate_lines = "[Outro]\\nFirst exact phrase.\\nSecond exact phrase."\n    fused_line = "[Outro]\\nFirst exact phrase. Second exact phrase."\n    assert validate_verbatim_lyrics(separate_lines, source).passed\n    assert not validate_verbatim_lyrics(fused_line, source).passed\n\n\nclass CapturingLyricsProvider(MockLLMProvider):\n    def __init__(self) -> None:\n        super().__init__()\n        self.last_lyrics_prompt = ""\n\n    def generate_structured(\n        self, system_prompt, user_prompt, response_model, temperature=0.0, seed=None\n    ):\n        if response_model is GeneratedLyricsResponse:\n            self.last_lyrics_prompt = user_prompt\n        return super().generate_structured(\n            system_prompt, user_prompt, response_model, temperature, seed\n        )\n\n\ndef test_lyric_writer_explicitly_forbids_source_metadata_output() -> None:\n    provider = CapturingLyricsProvider()\n    item = lesson(116)\n    style = StyleRecord(style_id="STYLE_1", name="Demo", core_prompt="Warm acoustic folk.")\n    plan = LyricPlan(\n        lesson_number=116,\n        language="en",\n        archetype=SongArchetype.TITLE_TEACHING_PRAYER,\n        sections=[PlanSection(label="Chorus", function="title", source_sentence_ids=["title"])],\n    )\n    adaptation = StyleAdaptation(\n        style_id="STYLE_1",\n        lesson_number=116,\n        core_prompt=style.core_prompt,\n        adaptation="Gentle delivery.",\n        final_prompt=f"{style.core_prompt} Gentle delivery.",\n    )\n    generate_lyrics(item, plan, adaptation, provider)\n    prompt = provider.last_lyrics_prompt\n    assert "metadata labels only" in prompt\n    assert "Never emit source IDs" in prompt\n    assert "never splice noncontiguous source spans" in prompt\n\n\ndef test_repair_uses_structured_lyrics_wrapper() -> None:\n    item = lesson(116)\n    style = StyleRecord(style_id="STYLE_1", name="Demo", core_prompt="Warm acoustic folk.")\n    plan = LyricPlan(\n        lesson_number=116,\n        language="en",\n        archetype=SongArchetype.TITLE_TEACHING_PRAYER,\n        sections=[PlanSection(label="Chorus", function="title", source_sentence_ids=["title"])],\n    )\n    adaptation = StyleAdaptation(\n        style_id="STYLE_1",\n        lesson_number=116,\n        core_prompt=style.core_prompt,\n        adaptation="Gentle delivery.",\n        final_prompt=f"{style.core_prompt} Gentle delivery.",\n    )\n    artifact = __import__("acim_suno.generator", fromlist=["create_song_artifact"]).create_song_artifact(\n        item,\n        plan,\n        adaptation,\n        [__import__("acim_suno.models", fromlist=["GeneratedLyric"]).GeneratedLyric(\n            section_label="Chorus", text="Invented line"\n        )],\n    )\n    report = validate_verbatim_lyrics(artifact.full_lyrics_text, item.source_text)\n    request = create_repair_request(artifact, report, max_retries=1)\n    repaired, _, repaired_report = repair_song(request, item, MockLLMProvider())\n    assert repaired is not None\n    assert repaired_report.passed\n'''
    if "test_json_provider_uses_atomic_clean_sentences_and_per_lesson_hashes" not in text:
        text += addition
    write(path, text)


def main() -> None:
    patch_sources()
    patch_cli()
    patch_llm()
    patch_repair()
    patch_prompts()
    patch_agents()
    patch_readme()
    patch_verification_doc()
    patch_tests()


if __name__ == "__main__":
    main()
