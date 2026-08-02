from __future__ import annotations

import re
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
    if "import re\n" not in text:
        text = text.replace("import os\n", "import os\nimport re\n", 1)

    text = text.replace(
        "            is_review = reviewed is not None and len(paragraphs) <= 3\n",
        "            is_review = _is_review_lesson(num) or reviewed is not None\n",
        1,
    )

    start = "DUMMY_VECTOR = [0.01] * 768\n"
    end = "def create_source_provider(\n"
    replacement = '''REVIEW_LESSON_RANGES = ((111, 120), (141, 150), (171, 180))\n\n\ndef _is_review_lesson(lesson_number: int) -> bool:\n    return any(start <= lesson_number <= end for start, end in REVIEW_LESSON_RANGES)\n\n\ndef _reference_sort_key(reference: str) -> tuple[int, tuple[int, ...], str]:\n    numbers = tuple(int(value) for value in re.findall(r"\\d+", reference))\n    return (0 if numbers else 1, numbers, reference.casefold())\n\n\ndef _ordered_pinecone_paragraphs(\n    paragraphs: list[dict[str, object]],\n) -> list[dict[str, object]]:\n    return sorted(\n        paragraphs,\n        key=lambda item: _reference_sort_key(str(item.get("reference", ""))),\n    )\n\n\ndef _pinecone_lesson_hash(\n    lesson_number: int,\n    language: str,\n    title: str,\n    paragraphs: list[dict[str, object]],\n) -> str:\n    payload = {\n        "lesson_number": lesson_number,\n        "language": language,\n        "title": title,\n        "paragraphs": [\n            {\n                "reference": str(item.get("reference", "")),\n                "text": str(item.get("text", "")),\n            }\n            for item in paragraphs\n        ],\n    }\n    canonical = json.dumps(\n        payload,\n        sort_keys=True,\n        ensure_ascii=False,\n        separators=(",", ":"),\n    )\n    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()\n\n\nDUMMY_VECTOR = [0.01] * 768\n\n\ndef _pinecone_push_sentence(\n    sentences: list[SourceSentence],\n    counter: list[int],\n    text: str,\n    category: str,\n    lesson_num: int,\n) -> None:\n    text = text.strip()\n    if text:\n        counter[0] += 1\n        sentences.append(\n            SourceSentence(\n                sentence_id=f"L{lesson_num}_{counter[0]:03d}",\n                text=text,\n                category=category,\n            )\n        )\n\n\nclass PineconeSourceProvider:\n    def __init__(\n        self,\n        *,\n        api_key: str | None = None,\n        host: str = "https://acim-text-e2xpwpt.svc.aped-4627-b74a.pinecone.io",\n        source_language: str = "en",\n    ) -> None:\n        self._api_key = api_key or os.environ.get("PINECONE_API_KEY", "")\n        if not self._api_key:\n            raise ValueError("PINECONE_API_KEY required")\n        self._host = host\n        self._source_language = source_language\n        self._provider_hash = hashlib.sha256(\n            f"pinecone:{host}:{source_language}".encode()\n        ).hexdigest()\n\n    def get_source_hash(self) -> str:\n        """Return provider identity; individual lessons carry content hashes."""\n        return self._provider_hash\n\n    def fetch_lessons(\n        self,\n        start: int = 116,\n        end: int = 199,\n        language: str = "en",\n    ) -> list[LessonRecord]:\n        if language != self._source_language:\n            raise ValueError(\n                f"Source provider is bound to {self._source_language!r}; requested {language!r}"\n            )\n\n        import urllib.error\n        import urllib.request\n\n        lessons_map: dict[int, dict[str, object]] = {}\n\n        for num in range(start, end + 1):\n            payload = {\n                "namespace": "workbook",\n                "vector": DUMMY_VECTOR,\n                "topK": 100,\n                "filter": {"lesson": {"$eq": num}},\n                "includeMetadata": True,\n            }\n            req = urllib.request.Request(\n                f"{self._host}/query",\n                data=json.dumps(payload).encode("utf-8"),\n                headers={"Api-Key": self._api_key, "Content-Type": "application/json"},\n            )\n            try:\n                with urllib.request.urlopen(req, timeout=30) as resp:\n                    result = json.loads(resp.read().decode())\n            except urllib.error.HTTPError as exc:\n                if exc.code == 404:\n                    continue\n                raise\n\n            matches = result.get("matches", [])\n            if not matches:\n                continue\n\n            paragraphs_raw: list[dict[str, object]] = []\n            title = f"Lesson {num}"\n            for match in matches:\n                meta = match.get("metadata", {})\n                ref = meta.get("reference", "")\n                paragraph_text = meta.get("text", "")\n                if paragraph_text:\n                    paragraphs_raw.append(\n                        {"reference": ref, "text": paragraph_text, "metadata": meta}\n                    )\n                stored_title = meta.get("title", "")\n                if stored_title and len(str(stored_title)) > len(str(title)):\n                    title = str(stored_title)\n\n            paragraphs_raw = _ordered_pinecone_paragraphs(paragraphs_raw)\n            lessons_map[num] = {\n                "title": title,\n                "paragraphs": paragraphs_raw,\n            }\n\n        missing = [num for num in range(start, end + 1) if num not in lessons_map]\n        if missing:\n            preview = ", ".join(str(num) for num in missing[:10])\n            raise ValueError(\n                f"Pinecone source is missing {len(missing)} requested lesson(s): {preview}"\n            )\n\n        records: list[LessonRecord] = []\n        for lesson_num in sorted(lessons_map):\n            data = lessons_map[lesson_num]\n            title = str(data["title"])\n            paragraphs_raw = data["paragraphs"]\n            if not isinstance(paragraphs_raw, list):\n                raise ValueError(f"Invalid Pinecone paragraphs for lesson {lesson_num}")\n\n            paragraph_texts: list[str] = []\n            sentences: list[SourceSentence] = []\n            sentence_counter = [0]\n\n            if title:\n                _pinecone_push_sentence(\n                    sentences, sentence_counter, title, "title", lesson_num\n                )\n\n            for paragraph in paragraphs_raw:\n                if not isinstance(paragraph, dict):\n                    continue\n                paragraph_text = str(paragraph.get("text", ""))\n                if paragraph_text:\n                    paragraph_texts.append(paragraph_text)\n                    _pinecone_push_sentence(\n                        sentences,\n                        sentence_counter,\n                        paragraph_text,\n                        "teaching",\n                        lesson_num,\n                    )\n\n            if _is_review_lesson(lesson_num):\n                lesson_type = LessonType.REVIEW\n            elif any(\n                marker in title.lower() for marker in ("stillness", "quiet", "meditation")\n            ):\n                lesson_type = LessonType.EXPERIENTIAL\n            else:\n                lesson_type = LessonType.STANDARD\n\n            lesson_source_hash = _pinecone_lesson_hash(\n                lesson_num, language, title, paragraphs_raw\n            )\n            records.append(\n                LessonRecord(\n                    lesson_number=lesson_num,\n                    language=language,\n                    title=title,\n                    lesson_type=lesson_type,\n                    source=SourceMetadata(\n                        edition=f"pinecone-acim-text-{self._host}",\n                        url=f"{self._host}/query",\n                        source_hash=lesson_source_hash,\n                        rights_status="review_required",\n                    ),\n                    sentences=sentences,\n                    paragraphs=paragraph_texts,\n                )\n            )\n\n        return records\n\n\n'''
    text = replace_between(text, start, end, replacement, "pinecone provider")
    write(path, text)


def patch_validators() -> None:
    path = "src/acim_suno/validators.py"
    text = read(path)
    text = text.replace(
        'SECTION_LABEL = re.compile(r"^\\s*\\[{1,2}[^\\]]+\\]{1,2}\\s*$")',
        'SECTION_LABEL = re.compile(r"^\\s*(?:\\[[^\\[\\]]+\\]|\\[\\[[^\\[\\]]+\\]\\])\\s*$")',
        1,
    )
    text = text.replace(
        'r"|music\\s+(?:fades?|drops?|swells?)|fade\\s+(?:in|out))\\)\\s*$",',
        'r"|music\\s+(?:fades?|drops?|swells?)|fade\\s+(?:in|out)|ad-?lib|spoken|sung)\\)\\s*$",',
        1,
    )
    old_editorial = '''EDITORIAL_MARKER = re.compile(\n    r"\\s*W-pI\\.[0-9]+\\.[0-9]+\\.|\\s*\\(\\d+\\)|\\s\\d+\\s+(?=[A-Z])"\n)\n'''
    new_editorial = '''EDITORIAL_REFERENCE = re.compile(r"\\bW-pI\\.\\d+(?:\\.\\d+)+\\.?")\nLEADING_EDITORIAL_NUMBER = re.compile(r"(?m)^\\s*(?:\\(\\d+\\)|\\d+\\.?)\\s+(?=[A-Z])")\n'''
    text = replace_once(text, old_editorial, new_editorial, "editorial normalization")
    text = text.replace(
        '    value = EDITORIAL_MARKER.sub(" ", value)\n',
        '    value = EDITORIAL_REFERENCE.sub(" ", value)\n'
        '    value = LEADING_EDITORIAL_NUMBER.sub(" ", value)\n',
        1,
    )
    start = "def _match_positions(source: str, chunk: str) -> list[int]:\n"
    end = "def validate_verbatim_lyrics(lyrics: str, source_text: str) -> ValidationReport:\n"
    replacement = '''def _is_verbatim_line(norm_line: str, norm_source: str) -> bool:\n    if not norm_line:\n        return False\n    if norm_line in norm_source:\n        return True\n\n    words = norm_line.split()\n    for unit_length in range(1, (len(words) // 2) + 1):\n        if len(words) % unit_length:\n            continue\n        unit_words = words[:unit_length]\n        repeat_count = len(words) // unit_length\n        if repeat_count < 2 or unit_words * repeat_count != words:\n            continue\n        unit = " ".join(unit_words)\n        if unit in norm_source:\n            return True\n    return False\n\n\n'''
    text = replace_between(text, start, end, replacement, "strict verbatim matcher")
    old_loop = '''        checked_lines += 1\n        ad_lib = AD_LIB.fullmatch(line)\n        if ad_lib:\n            line = ad_lib.group(1).strip()\n        else:\n            line = TREATMENT_MARKER.sub("", line).strip()\n        if not _is_verbatim_line(normalize_source_text(line), normalized_source):\n'''
    new_loop = '''        ad_lib = AD_LIB.fullmatch(line)\n        if ad_lib:\n            line = ad_lib.group(1).strip()\n        else:\n            line = TREATMENT_MARKER.sub("", line).strip()\n        if not line:\n            continue\n        checked_lines += 1\n        if not _is_verbatim_line(normalize_source_text(line), normalized_source):\n'''
    text = replace_once(text, old_loop, new_loop, "verbatim line counting")
    write(path, text)


def patch_llm() -> None:
    path = "src/acim_suno/llm.py"
    text = read(path)
    old_analysis = '''    return llm.generate_structured(system_prompt, user_prompt, LessonAnalysisProfile)\n\n\ndef score_compatibility(\n'''
    new_analysis = '''    result = llm.generate_structured(system_prompt, user_prompt, LessonAnalysisProfile)\n    return result.model_copy(\n        update={\n            "lesson_number": lesson.lesson_number,\n            "language": lesson.language,\n            "lesson_type": lesson.lesson_type,\n            "analyzed_source_hash": lesson.source.source_hash,\n            "analysis_version": prompt_version,\n        }\n    )\n\n\ndef score_compatibility(\n'''
    text = replace_once(text, old_analysis, new_analysis, "analysis provenance")

    start = "def score_compatibility(\n"
    end = "def select_archetype(\n"
    replacement = '''def score_compatibility(\n    lesson: LessonRecord,\n    styles: list[StyleRecord],\n    llm: LLMProvider,\n    prompt_version: str = "0.1.0",\n    max_attempts: int = 3,\n    profile: LessonAnalysisProfile | None = None,\n) -> list[CompatibilityScore]:\n    from collections import Counter\n\n    system_prompt = _load_prompt_section("compatibility scorer")\n    expected_ids = {style.style_id for style in styles}\n    if len(expected_ids) != len(styles):\n        raise ValueError("Style registry contains duplicate style IDs")\n\n    profile_info = "No lesson-analysis profile supplied."\n    if profile is not None:\n        profile_info = (\n            f"Themes: {', '.join(profile.themes) or 'none'}\\n"\n            f"Emotional arc: {profile.emotional_start} -> "\n            f"{profile.emotional_destination}\\n"\n            f"Energy target: {profile.energy_target}\\n"\n            f"Lyric density: {profile.lyric_density}\\n"\n            f"Repetition affinity: {profile.repetition_affinity}\\n"\n            f"Spoken-word need: {profile.spoken_word_need}\\n"\n            f"Clarity requirement: {profile.clarity_requirement}\\n"\n            f"Preferred arc: {profile.preferred_arc}\\n"\n            f"Suitable traits: {profile.suitable_traits}\\n"\n            f"Unsuitable traits: {profile.unsuitable_traits}"\n        )\n\n    lesson_info = (\n        f"Lesson {lesson.lesson_number}:\\n"\n        f"Title: {lesson.title}\\n"\n        f"Type: {lesson.lesson_type.value}\\n"\n        f"Language: {lesson.language}\\n"\n        f"Lesson analysis:\\n{profile_info}\\n"\n        f"Source excerpt:\\n{lesson.source_text[:2500]}\\n"\n    )\n    styles_info = "\\n".join(\n        f"style_id={style.style_id}, name={style.name}, "\n        f"bucket={style.primary_bucket}, energy={style.energy}, "\n        f"density={style.lyric_density}, prompt={style.core_prompt[:100]}"\n        for style in styles\n    )\n    user_prompt = (\n        f"{lesson_info}\\nAvailable styles ({len(styles)} total):\\n{styles_info}\\n"\n        f"\\nReturn exactly {len(styles)} score records, one per style_id listed above. "\n        "Do not add unknown IDs or duplicate IDs."\n    )\n\n    last_error: str | None = None\n    for attempt in range(1, max_attempts + 1):\n        response = llm.generate_structured(\n            system_prompt, user_prompt, CompatibilityScoreBatch\n        )\n        scores = [\n            score.model_copy(\n                update={\n                    "lesson_number": lesson.lesson_number,\n                    "language": lesson.language,\n                }\n            )\n            for score in response.root\n        ]\n        counts = Counter(score.style_id for score in scores)\n        returned_ids = set(counts)\n        missing = sorted(expected_ids - returned_ids)\n        unexpected = sorted(returned_ids - expected_ids)\n        duplicates = sorted(style_id for style_id, count in counts.items() if count != 1)\n        valid = (\n            len(scores) == len(styles)\n            and returned_ids == expected_ids\n            and not duplicates\n        )\n        if valid:\n            return scores\n\n        details: list[str] = []\n        if len(scores) != len(styles):\n            details.append(f"count {len(scores)} != {len(styles)}")\n        if missing:\n            details.append(f"missing: {', '.join(missing[:5])}")\n        if unexpected:\n            details.append(f"unexpected: {', '.join(unexpected[:5])}")\n        if duplicates:\n            details.append(f"duplicates: {', '.join(duplicates[:5])}")\n        last_error = "; ".join(details) or "invalid score batch"\n        logger.warning(\n            "Compatibility score batch invalid (attempt %d/%d): %s",\n            attempt,\n            max_attempts,\n            last_error,\n        )\n        if attempt < max_attempts:\n            user_prompt += (\n                f"\\n\\nPrevious attempt was invalid: {last_error}. "\n                f"Return exactly one record for every one of the {len(styles)} expected IDs."\n            )\n\n    raise ValueError(\n        f"Compatibility scoring failed for lesson {lesson.lesson_number} after "\n        f"{max_attempts} attempts: {last_error}"\n    )\n\n\n'''
    text = replace_between(text, start, end, replacement, "profile-aware scorer")
    write(path, text)


def patch_scorer() -> None:
    path = "src/acim_suno/scorer.py"
    text = read(path)
    text = text.replace(
        "from .models import CompatibilityScore, LessonRecord, StyleRecord\n",
        "from .models import (\n"
        "    CompatibilityScore,\n"
        "    LessonAnalysisProfile,\n"
        "    LessonRecord,\n"
        "    StyleRecord,\n"
        ")\n",
        1,
    )
    text = text.replace(
        '''    model_name: str,\n) -> str:\n    raw = f"{lesson_number}:{lesson_hash}:{style_hash}:{prompt_version}:{model_name}"\n''',
        '''    model_name: str,\n    profile_hash: str = "none",\n) -> str:\n    raw = (\n        f"{lesson_number}:{lesson_hash}:{style_hash}:{prompt_version}:"\n        f"{model_name}:{profile_hash}"\n    )\n''',
        1,
    )
    text = text.replace(
        '''    force_recompute: bool = False,\n) -> list[CompatibilityScore]:\n''',
        '''    force_recompute: bool = False,\n    profiles: list[LessonAnalysisProfile] | None = None,\n) -> list[CompatibilityScore]:\n''',
        1,
    )
    text = text.replace(
        '''    scores: list[CompatibilityScore] = []\n\n    for lesson in lessons:\n''',
        '''    scores: list[CompatibilityScore] = []\n    profile_by_lesson = {\n        (profile.lesson_number, profile.language): profile for profile in (profiles or [])\n    }\n\n    for lesson in lessons:\n''',
        1,
    )
    old_cache = '''        lesson_hash = lesson.source.source_hash\n        cache_key = build_score_cache_key(\n            lesson.lesson_number, lesson_hash, style_hash, prompt_version, llm.model_name\n        )\n'''
    new_cache = '''        lesson_hash = lesson.source.source_hash\n        profile = profile_by_lesson.get((lesson.lesson_number, lesson.language))\n        profile_hash = "none"\n        if profile is not None:\n            profile_hash = hashlib.sha256(\n                json.dumps(profile.model_dump(mode="json"), sort_keys=True).encode()\n            ).hexdigest()\n        cache_key = build_score_cache_key(\n            lesson.lesson_number,\n            lesson_hash,\n            style_hash,\n            prompt_version,\n            llm.model_name,\n            profile_hash,\n        )\n'''
    text = replace_once(text, old_cache, new_cache, "profile cache key")
    text = text.replace(
        "        lesson_scores = score_compatibility(lesson, styles, llm, prompt_version)\n",
        "        lesson_scores = score_compatibility(\n"
        "            lesson, styles, llm, prompt_version, profile=profile\n"
        "        )\n",
        1,
    )
    write(path, text)


def patch_planner() -> None:
    path = "src/acim_suno/planner.py"
    text = read(path)
    text = text.replace(
        "    LessonRecord,\n",
        "    LessonRecord,\n    LessonType,\n",
        1,
    )
    text = text.replace(
        '''    if profile.ranked_archetypes:\n        return profile.ranked_archetypes[0]\n''',
        '''    if lesson.lesson_type is LessonType.REVIEW:\n        return SongArchetype.PAIRED_REVIEW\n    if profile.ranked_archetypes:\n        return profile.ranked_archetypes[0]\n''',
        1,
    )
    write(path, text)


def patch_cli() -> None:
    path = "src/acim_suno/cli.py"
    text = read(path)
    old = '''    styles = load_models(args.styles, StyleRecord)\n    llm = create_llm_provider(args.provider, args.model)\n    scores = compute_compatibility_scores(\n        lessons,\n        styles,\n        llm,\n        prompt_version=args.prompt_version,\n        cache_dir=args.cache_dir,\n        force_recompute=args.force,\n    )\n'''
    new = '''    styles = load_models(args.styles, StyleRecord)\n    profiles = (\n        load_models(args.profiles, LessonAnalysisProfile) if args.profiles else None\n    )\n    llm = create_llm_provider(args.provider, args.model)\n    scores = compute_compatibility_scores(\n        lessons,\n        styles,\n        llm,\n        prompt_version=args.prompt_version,\n        cache_dir=args.cache_dir,\n        force_recompute=args.force,\n        profiles=profiles,\n    )\n'''
    text = replace_once(text, old, new, "standalone scoring profiles")
    text = text.replace(
        '    score.add_argument("--styles", required=True)\n',
        '    score.add_argument("--styles", required=True)\n'
        '    score.add_argument("--profiles", help="Optional lesson-analysis profiles JSON")\n',
        1,
    )
    text = text.replace(
        '''        scores = compute_compatibility_scores(\n            lessons, styles, llm, cache_dir=str(output_dir / "scores")\n        )\n''',
        '''        scores = compute_compatibility_scores(\n            lessons,\n            styles,\n            llm,\n            cache_dir=str(output_dir / "scores"),\n            profiles=profiles,\n        )\n''',
        1,
    )
    old_plan = '''            profile_matches = [p for p in profiles if p.lesson_number == lesson.lesson_number]\n            profile = profile_matches[0] if profile_matches else None\n            archetype = (\n                profile.ranked_archetypes[0]\n                if (profile and profile.ranked_archetypes)\n                else SongArchetype.TITLE_TEACHING_PRAYER\n            )\n            plan = create_lyric_plan(lesson, archetype, llm)\n'''
    new_plan = '''            profile_matches = [\n                profile\n                for profile in profiles\n                if profile.lesson_number == lesson.lesson_number\n                and profile.language == lesson.language\n            ]\n            profile = profile_matches[0] if profile_matches else None\n            archetype = (\n                choose_archetype(lesson, profile, llm)\n                if profile is not None\n                else SongArchetype.PAIRED_REVIEW\n                if lesson.lesson_type.value == "review"\n                else SongArchetype.TITLE_TEACHING_PRAYER\n            )\n            plan = create_lyric_plan(lesson, archetype, llm)\n'''
    text = replace_once(text, old_plan, new_plan, "run batch archetype selection")
    write(path, text)


def patch_pyproject() -> None:
    path = "pyproject.toml"
    text = read(path)
    text = text.replace('gemini = ["google-genai>=1.0"]', 'gemini = ["google-genai>=1.51.0"]', 1)
    write(path, text)


def patch_prompts() -> None:
    path = "prompts/PIPELINE_PROMPTS.md"
    text = read(path)
    needle = "Return exactly one score record per supplied style ID — no fewer, no more. The output count must equal the number of style IDs given. If any style is skipped, the run fails.\n"
    addition = needle + "Use the supplied lesson-analysis profile and source excerpt as the primary evidence. Do not score from the title alone or from model memory. Never invent, duplicate, or substitute style IDs.\n"
    text = replace_once(text, needle, addition, "compatibility prompt grounding")
    write(path, text)


def patch_tests() -> None:
    path = "tests/test_pipeline.py"
    text = read(path)
    text = text.replace(
        "from acim_suno.llm import MockLLMProvider, generate_lyrics, score_compatibility, select_archetype\n",
        "from acim_suno.llm import MockLLMProvider, generate_lyrics, score_compatibility, select_archetype\n",
        1,
    )
    text = text.replace(
        "from acim_suno.optimizer import optimize_assignments\n",
        "from acim_suno.optimizer import optimize_assignments\n"
        "from acim_suno.planner import choose_archetype\n",
        1,
    )
    text = text.replace(
        "from acim_suno.sources import ACIMJsonSourceProvider\n",
        "from acim_suno.sources import (\n"
        "    ACIMJsonSourceProvider,\n"
        "    _is_review_lesson,\n"
        "    _ordered_pinecone_paragraphs,\n"
        "    _pinecone_lesson_hash,\n"
        ")\n",
        1,
    )
    addition = '''\n\ndef test_review_lesson_ranges_match_workbook_reviews() -> None:\n    assert _is_review_lesson(116)\n    assert _is_review_lesson(120)\n    assert not _is_review_lesson(121)\n    assert not _is_review_lesson(140)\n    assert _is_review_lesson(141)\n    assert _is_review_lesson(150)\n    assert not _is_review_lesson(151)\n    assert _is_review_lesson(171)\n    assert _is_review_lesson(180)\n    assert not _is_review_lesson(181)\n\n\ndef test_pinecone_paragraphs_are_sorted_by_reference_and_hash_content() -> None:\n    paragraphs = [\n        {"reference": "W-pI.116.3", "text": "Third"},\n        {"reference": "W-pI.116.1", "text": "First"},\n        {"reference": "W-pI.116.2", "text": "Second"},\n    ]\n    ordered = _ordered_pinecone_paragraphs(paragraphs)\n    assert [item["text"] for item in ordered] == ["First", "Second", "Third"]\n    first_hash = _pinecone_lesson_hash(116, "en", "Title", ordered)\n    changed = [dict(item) for item in ordered]\n    changed[1]["text"] = "Changed"\n    second_hash = _pinecone_lesson_hash(116, "en", "Title", changed)\n    assert first_hash != second_hash\n\n\ndef test_verbatim_validator_rejects_reordered_source_words_but_allows_repetition() -> None:\n    assert not validate_verbatim_lyrics("world hello", "hello world").passed\n    assert validate_verbatim_lyrics(\n        "I am safe. I am safe.", "I am safe."\n    ).passed\n\n\ndef test_review_lessons_force_paired_review_archetype() -> None:\n    item = lesson(116).model_copy(update={"lesson_type": "review"})\n    profile = LessonAnalysisProfile(\n        lesson_number=116,\n        lesson_type="review",\n        ranked_archetypes=[SongArchetype.TITLE_TEACHING_PRAYER],\n    )\n    assert choose_archetype(item, profile, MockLLMProvider()) is SongArchetype.PAIRED_REVIEW\n\n\nclass CapturingScoreProvider(MockLLMProvider):\n    def __init__(self) -> None:\n        super().__init__()\n        self.last_prompt = ""\n\n    def generate_structured(self, system_prompt, user_prompt, response_model, temperature=0.0, seed=None):\n        self.last_prompt = user_prompt\n        return super().generate_structured(\n            system_prompt, user_prompt, response_model, temperature, seed\n        )\n\n\ndef test_compatibility_scoring_uses_lesson_profile() -> None:\n    provider = CapturingScoreProvider()\n    item = lesson(121)\n    profile = LessonAnalysisProfile(\n        lesson_number=121,\n        lesson_type="standard",\n        themes=["forgiveness", "release"],\n        emotional_start="fear",\n        emotional_destination="peace",\n        energy_target=0.7,\n    )\n    style = StyleRecord(style_id="A", name="A", core_prompt="Acoustic")\n    score_compatibility(item, [style], provider, profile=profile, max_attempts=1)\n    assert "forgiveness" in provider.last_prompt\n    assert "fear -> peace" in provider.last_prompt\n    assert "Source excerpt" in provider.last_prompt\n\n\nclass DuplicateScoreProvider(MockLLMProvider):\n    def generate_structured(self, system_prompt, user_prompt, response_model, temperature=0.0, seed=None):\n        if response_model is CompatibilityScoreBatch:\n            return CompatibilityScoreBatch(\n                [\n                    CompatibilityScore(lesson_number=121, style_id="A", total=8),\n                    CompatibilityScore(lesson_number=121, style_id="A", total=7),\n                    CompatibilityScore(lesson_number=121, style_id="B", total=6),\n                ]\n            )\n        return super().generate_structured(\n            system_prompt, user_prompt, response_model, temperature, seed\n        )\n\n\ndef test_compatibility_scoring_rejects_duplicate_style_records() -> None:\n    item = lesson(121)\n    styles = [\n        StyleRecord(style_id="A", name="A", core_prompt="A"),\n        StyleRecord(style_id="B", name="B", core_prompt="B"),\n    ]\n    with pytest.raises(ValueError, match="Compatibility scoring failed"):\n        score_compatibility(item, styles, DuplicateScoreProvider(), max_attempts=1)\n'''
    if "test_review_lesson_ranges_match_workbook_reviews" not in text:
        text += addition
    write(path, text)


def main() -> None:
    patch_sources()
    patch_validators()
    patch_llm()
    patch_scorer()
    patch_planner()
    patch_cli()
    patch_pyproject()
    patch_prompts()
    patch_tests()


if __name__ == "__main__":
    main()
