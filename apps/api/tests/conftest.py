import os
import pathlib

os.environ.setdefault("ACE_LLM_FAKE", "true")
os.environ.setdefault("ACE_EMBEDDER", "hash")

RESOURCES = pathlib.Path(__file__).resolve().parents[3] / "resources"

SYLLABUS_PDF = str(RESOURCES / "Appendix-1-Canadian-Investment-Regulatory-Exam-CIRE-Syllabus-EN.pdf")
PRACTICE_PDF = str(RESOURCES / "Appendix-2-CIRE-Practice-Exam-EN.pdf")
GUIDANCE_PDF = str(RESOURCES / "Appendix-3-CIRE-Guidance-for-Studying-EN.pdf")
