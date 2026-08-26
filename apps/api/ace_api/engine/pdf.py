from __future__ import annotations

from dataclasses import dataclass

import fitz


@dataclass
class Page:
    number: int  # 1-based
    text: str


def extract_pages(path: str) -> list[Page]:
    doc = fitz.open(path)
    pages = [Page(number=i + 1, text=page.get_text()) for i, page in enumerate(doc)]
    doc.close()
    return pages


def full_text(path: str) -> str:
    return "\n".join(p.text for p in extract_pages(path))
