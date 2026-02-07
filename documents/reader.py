"""Read DOCX and COBOL source for agent inputs."""
from pathlib import Path
from docx import Document


def read_docx_text(path: str | Path) -> str:
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def read_cobol_directory(cobol_dir: str | Path) -> dict[str, str]:
    """Return {relative_path: content} for .cbl and .cpy under cobol_dir."""
    root = Path(cobol_dir)
    out = {}
    for ext in ("*.cbl", "*.cpy"):
        for f in root.rglob(ext):
            try:
                rel = f.relative_to(root)
                out[str(rel)] = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass
    return out
