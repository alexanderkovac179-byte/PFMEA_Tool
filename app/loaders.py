from pathlib import Path
from pypdf import PdfReader
from docx import Document

def load_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")

def load_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = []

    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text)

    return "\n".join(pages)

def load_docx(path: Path) -> str:
    doc = Document(str(path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)

def load_documents(folder: str) -> list[dict]:
    docs = []

    for path in Path(folder).rglob("*"):
        if not path.is_file():
            continue

        suffix = path.suffix.lower()

        try:
            if suffix in [".txt", ".md"]:
                text = load_txt(path)
            elif suffix == ".pdf":
                text = load_pdf(path)
            elif suffix == ".docx":
                text = load_docx(path)
            else:
                continue

            if text.strip():
                docs.append({
                    "source": str(path),
                    "text": text
                })

        except Exception as e:
            print(f"Chyba pri načítaní {path}: {e}")

    return docs