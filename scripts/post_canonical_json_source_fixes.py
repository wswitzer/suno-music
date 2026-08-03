from pathlib import Path

path = Path("tests/test_pipeline.py")
text = path.read_text(encoding="utf-8")

marker = r"\n\ndef _write_canonical_workbook"
idx = text.find(marker)
if idx < 0:
    raise RuntimeError("canonical test suffix marker not found")

prefix = text[:idx]
suffix = text[idx:]
suffix = suffix.replace(r"\n", "\n")

# Keep public regression fixtures wholly synthetic; do not commit source text.
replacements = {
    "Forgiveness offers everything I want.": "Synthetic lesson idea.",
    "What could you want forgiveness cannot give?": "First canonical sentence.",
    "Do you want peace?": "Second canonical sentence.",
    "Forgiveness offers it.": "Third canonical sentence.",
    "Remember this today.": "Synthetic practice instruction.",
    "I thank my Father for His gifts to me.": "Synthetic lesson 123.",
    "Would you have peace?": "Changed canonical sentence.",
}
for old, new in replacements.items():
    suffix = suffix.replace(old, new)

# The migration payload intentionally encoded Python string newlines. Converting
# the outer payload's escaped newlines leaves these two strings as line
# continuations, so restore explicit \n escapes inside the Python test strings.
suffix = suffix.replace(
    'separate_lines = "[Outro]\\\nFirst exact phrase.\\\nSecond exact phrase."',
    'separate_lines = "[Outro]\\nFirst exact phrase.\\nSecond exact phrase."',
)
suffix = suffix.replace(
    'fused_line = "[Outro]\\\nFirst exact phrase. Second exact phrase."',
    'fused_line = "[Outro]\\nFirst exact phrase. Second exact phrase."',
)

# Ensure the regex in the synthetic numbering assertion checks digits, not a
# literal backslash sequence after conversion from the migration payload.
suffix = suffix.replace('r"^\\\\d+\\\\s"', 'r"^\\d+\\s"')

# Replace the generic-mock repair assertion with a provider that explicitly
# verifies the repair path requests the Pydantic wrapper and returns an exact
# source phrase. This isolates the structured-output contract from mock lyric
# generation behavior.
repair_marker = "def test_repair_uses_structured_lyrics_wrapper() -> None:"
repair_idx = suffix.find(repair_marker)
if repair_idx < 0:
    raise RuntimeError("repair wrapper test marker not found")
repair_test = '''class RepairWrapperProvider(MockLLMProvider):
    def __init__(self) -> None:
        super().__init__()
        self.response_model_seen = None

    def generate_structured(
        self, system_prompt, user_prompt, response_model, temperature=0.0, seed=None
    ):
        if response_model is GeneratedLyricsResponse:
            self.response_model_seen = response_model
            generated_lyric = __import__(
                "acim_suno.models", fromlist=["GeneratedLyric"]
            ).GeneratedLyric(section_label="Chorus", text="Demo 116")
            return GeneratedLyricsResponse([generated_lyric])
        return super().generate_structured(
            system_prompt, user_prompt, response_model, temperature, seed
        )


def test_repair_uses_structured_lyrics_wrapper() -> None:
    item = lesson(116)
    style = StyleRecord(style_id="STYLE_1", name="Demo", core_prompt="Warm acoustic folk.")
    plan = LyricPlan(
        lesson_number=116,
        language="en",
        archetype=SongArchetype.TITLE_TEACHING_PRAYER,
        sections=[PlanSection(label="Chorus", function="title", source_sentence_ids=["title"])],
    )
    adaptation = StyleAdaptation(
        style_id="STYLE_1",
        lesson_number=116,
        core_prompt=style.core_prompt,
        adaptation="Gentle delivery.",
        final_prompt=f"{style.core_prompt} Gentle delivery.",
    )
    generated_lyric = __import__(
        "acim_suno.models", fromlist=["GeneratedLyric"]
    ).GeneratedLyric(section_label="Chorus", text="Invented line")
    artifact = __import__(
        "acim_suno.generator", fromlist=["create_song_artifact"]
    ).create_song_artifact(item, plan, adaptation, [generated_lyric])
    report = validate_verbatim_lyrics(artifact.full_lyrics_text, item.source_text)
    request = create_repair_request(artifact, report, max_retries=1)
    provider = RepairWrapperProvider()
    repaired, _, repaired_report = repair_song(request, item, provider)
    assert provider.response_model_seen is GeneratedLyricsResponse
    assert repaired is not None
    assert repaired_report.passed
'''
suffix = suffix[:repair_idx] + repair_test

text = prefix + suffix
if "import json\n" not in text:
    text = text.replace(
        "from __future__ import annotations\n\n",
        "from __future__ import annotations\n\nimport json\n",
        1,
    )

path.write_text(text, encoding="utf-8")
