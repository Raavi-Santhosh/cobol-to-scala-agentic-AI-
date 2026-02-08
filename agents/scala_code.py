"""Agent 7: Target-language Code Generation (Scala or Python). Generates EVERY file from the design."""
import json
import re
from pathlib import Path

from .base import BaseAgent, AgentContext, AgentResult
from llm import generate, get_model_for_agent, get_temperature, get_target_language
from documents.reader import read_docx_text


SCALA_CODE_PROMPT = """You are a Scala developer. Generate COMPLETE Scala code for EVERY file listed below. Do not skip any file.

RULES:
1. You MUST emit exactly one ---FILE: path --- ... ---END FILE--- block for EACH file in the "Files to generate" list. If there are N files, you must output N blocks. No exceptions.
2. Use the EXACT package paths and class/object names from the design. Match case classes and services exactly.
3. For each file, implement the "Purpose" and every item in "Logic to implement" from the Per-File Implementation section. Full implementations only; no "// TODO" or placeholders.
4. Write only valid Scala. No COBOL.

Format for each file (repeat for every file in the list):
---FILE: path/from/list/File.scala---
// Scala code implementing the purpose and logic for this file
---END FILE---

Files to generate (you MUST output one ---FILE--- block per line, in this order):"""


PYTHON_CODE_PROMPT = """You are a Python developer. Generate COMPLETE Python code for EVERY module listed below. Do not skip any.

RULES:
1. You MUST emit exactly one ---FILE: path --- ... ---END FILE--- block for EACH module in the "Modules to generate" list. If there are N modules, you must output N blocks. No exceptions.
2. Use the EXACT module paths and class/function names from the design. Match dataclasses and services exactly.
3. For each module, implement the "Purpose" and every item in "Logic to implement" from the Per-File Implementation section. Full implementations only; no placeholders.
4. Write only valid Python 3 with type hints. No COBOL.

Format for each module (repeat for every module in the list):
---FILE: path/from/list/module.py---
# Python code implementing the purpose and logic for this module
---END FILE---

Modules to generate (you MUST output one ---FILE--- block per line, in this order):"""


def _extract_files(response: str) -> list[tuple[str, str]]:
    pattern = re.compile(r"---FILE:\s*([^\n-]+)---\s*(.*?)---END FILE---", re.DOTALL)
    matches = pattern.findall(response)
    return [(p.strip(), code.strip()) for p, code in matches]


def _load_design_json(context: AgentContext) -> dict | None:
    path = context.artifact_paths.get("scala_design.json")
    if path and Path(path).exists():
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    fallback = Path(context.output_dir) / "06_scala_design" / "scala_design.json"
    if fallback.exists():
        try:
            with open(fallback) as f:
                return json.load(f)
        except Exception:
            pass
    return None


def _file_checklist(design: dict | None, target: str) -> tuple[str, str]:
    """Build (1) numbered file list for prompt, (2) per-file mandate text (purpose + logic) for code gen."""
    ext = ".py" if target == "python" else ".scala"
    if not design:
        return "(Parse the design above; list every .scala or .py file and generate each one.)", ""

    packages = design.get("packages", [])
    file_resps = design.get("file_responsibilities", [])
    paths = []
    if file_resps:
        paths = [fr.get("path", "").strip() for fr in file_resps if fr.get("path")]
    if not paths and packages:
        paths = [p.get("path", "").strip() for p in packages if p.get("path")]
    if not paths:
        case_classes = design.get("case_classes", [])
        services = design.get("services", [])
        pkg_sep = "/"
        for c in case_classes:
            pkg = (c.get("package") or c.get("module", "")).replace(".", pkg_sep)
            name = c.get("name", "")
            if name:
                paths.append(f"{pkg}/{name}{ext}".replace("//", "/").strip("/"))
        for s in services:
            pkg = (s.get("package") or s.get("module", "")).replace(".", pkg_sep)
            name = s.get("name", "")
            if name:
                paths.append(f"{pkg}/{name}{ext}".replace("//", "/").strip("/"))

    if not paths:
        return "(See Package Structure in design.)", ""

    checklist = "\n".join(f"  {i+1}. {p}" for i, p in enumerate(paths))
    checklist = f"You MUST generate exactly {len(paths)} files.\n" + checklist

    mandate_lines = []
    for i, path in enumerate(paths):
        fr = next((f for f in file_resps if (f.get("path") or "").strip() == path), None)
        if fr:
            mandate_lines.append(f"File {i+1}: {path}")
            mandate_lines.append(f"  Purpose: {fr.get('purpose', '')}")
            for logic in fr.get("logic", []):
                mandate_lines.append(f"  Logic: - {logic}")
        else:
            pkg = next((p for p in packages if (p.get("path") or "").strip() == path), None)
            mandate_lines.append(f"File {i+1}: {path}")
            mandate_lines.append(f"  Purpose: {pkg.get('description', 'Implement as per design') if pkg else 'Implement as per design'}")
        mandate_lines.append("")
    per_file_mandate = "\n".join(mandate_lines) if mandate_lines else ""

    return checklist, per_file_mandate


class ScalaCodeAgent(BaseAgent):
    agent_id = "agent_7"

    def run(self, context: AgentContext) -> AgentResult:
        target = get_target_language()
        pseudo_doc = context.artifact_paths.get("05_Pseudocode_Language_Neutral.docx")
        design_doc = context.artifact_paths.get("06_Scala_Design_Specification.docx")
        pseudo_text = read_docx_text(pseudo_doc) if pseudo_doc else ""
        design_text = read_docx_text(design_doc) if design_doc else ""
        design_json = _load_design_json(context)
        file_checklist, per_file_mandate = _file_checklist(design_json, target)

        if target == "python":
            prompt = (
                PYTHON_CODE_PROMPT
                + "\n"
                + file_checklist
                + "\n\n--- Per-file implementation (what to implement in each file) ---\n"
                + (per_file_mandate or "(See design document.)")
                + "\n\n--- Pseudocode ---\n"
                + pseudo_text[:20000]
                + "\n\n--- Python Design (implement EVERY module above; use Per-File Implementation for each) ---\n"
                + design_text[:25000]
            )
            if design_json:
                prompt += "\n\n--- Design JSON (exact structure) ---\n" + json.dumps(design_json, indent=2)[:8000]
            ext = ".py"
            out_dir = Path(context.output_dir) / "07_python_code"
            code_dir = out_dir / "src"
        else:
            prompt = (
                SCALA_CODE_PROMPT
                + "\n"
                + file_checklist
                + "\n\n--- Per-file implementation (what to implement in each file) ---\n"
                + (per_file_mandate or "(See design document.)")
                + "\n\n--- Pseudocode ---\n"
                + pseudo_text[:20000]
                + "\n\n--- Scala Design (implement EVERY file above; use Per-File Implementation for each) ---\n"
                + design_text[:25000]
            )
            if design_json:
                prompt += "\n\n--- Design JSON (exact structure) ---\n" + json.dumps(design_json, indent=2)[:8000]
            ext = ".scala"
            out_dir = Path(context.output_dir) / "07_scala_code"
            code_dir = out_dir / "src" / "main" / "scala"
        out_dir.mkdir(parents=True, exist_ok=True)
        code_dir.mkdir(parents=True, exist_ok=True)

        model = get_model_for_agent(self.agent_id)
        response = generate(prompt, model=model, temperature=get_temperature(self.agent_id))
        matches = _extract_files(response)

        if not matches:
            single = re.sub(r"^---FILE:.*?---\s*", "", response)
            single = re.sub(r"\s*---END FILE---.*", "", single, flags=re.DOTALL)
            if single.strip():
                fpath = code_dir / ("main.py" if target == "python" else "Main.scala")
                fpath.write_text(single.strip(), encoding="utf-8")
                return AgentResult(artifacts={"target_source_dir": str(out_dir)})
            if target == "python":
                code_dir.joinpath("main.py").write_text(
                    "# Generated placeholder\n\ndef main() -> None:\n    pass\n", encoding="utf-8"
                )
            else:
                code_dir.joinpath("Main.scala").write_text(
                    "// Generated placeholder\nobject Main { def main(args: Array[String]): Unit = () }",
                    encoding="utf-8",
                )
            return AgentResult(artifacts={"target_source_dir": str(out_dir)})

        for rel_path, code in matches:
            if not rel_path.endswith(ext):
                rel_path = rel_path.rstrip("/") + ext
            rel_path = rel_path.replace("\\", "/").lstrip("/")
            full = code_dir / rel_path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(code, encoding="utf-8")

        return AgentResult(artifacts={"target_source_dir": str(out_dir)})
