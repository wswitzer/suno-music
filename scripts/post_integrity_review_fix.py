from pathlib import Path

path = Path("src/acim_suno/sources.py")
text = path.read_text(encoding="utf-8")
text = text.replace(
    'raise ValueError(f"Invalid Pinecone paragraphs for lesson {lesson_num}")',
    'raise TypeError(f"Invalid Pinecone paragraphs for lesson {lesson_num}")',
    1,
)
path.write_text(text, encoding="utf-8")
