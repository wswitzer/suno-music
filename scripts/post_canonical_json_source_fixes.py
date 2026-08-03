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

# Ensure the regex in the synthetic numbering assertion checks digits, not a
# literal backslash sequence after conversion from the migration payload.
suffix = suffix.replace('r"^\\\\d+\\\\s"', 'r"^\\d+\\s"')

text = prefix + suffix
if "import json\n" not in text:
    text = text.replace("from __future__ import annotations\n\n", "from __future__ import annotations\n\nimport json\n", 1)

path.write_text(text, encoding="utf-8")
