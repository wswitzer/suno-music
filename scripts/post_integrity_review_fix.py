from pathlib import Path

sources_path = Path("src/acim_suno/sources.py")
sources = sources_path.read_text(encoding="utf-8")
sources = sources.replace(
    'raise ValueError(f"Invalid Pinecone paragraphs for lesson {lesson_num}")',
    'raise TypeError(f"Invalid Pinecone paragraphs for lesson {lesson_num}")',
    1,
)
sources_path.write_text(sources, encoding="utf-8")

planner_path = Path("src/acim_suno/planner.py")
planner = planner_path.read_text(encoding="utf-8")
planner = planner.replace(
    "if lesson.lesson_type is LessonType.REVIEW:",
    "if lesson.lesson_type == LessonType.REVIEW:",
    1,
)
planner_path.write_text(planner, encoding="utf-8")
