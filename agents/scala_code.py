"""Agent 7: Target-language Code Generation (Scala or Python). Generates EVERY file from the design."""
import json
import re
from pathlib import Path

from .base import BaseAgent, AgentContext, AgentResult
from llm import generate, get_model_for_agent, get_temperature, get_target_language
from documents.reader import read_docx_text


SCALA_CODE_PROMPT = """You are a Scala developer. Generate COMPLETE Scala code for EVERY file in the design below.

RULES:
1. You MUST emit a separate ---FILE: ... --- block for EACH file listed in the Package Structure / design. Do not skip any file.
2. Use the EXACT package paths and class/object names from the design. Match case classes and services exactly.
3. Implement every case class with the fields specified; implement every service with the methods specified.
4. Write only valid Scala. No COBOL, no placeholders like "// TODO". Full implementations.
5. For each file use this format exactly:

---FILE: package/path/FileName.scala---
// Scala code
---END FILE---

List of files you MUST generate (from the design):"""


PYTHON_CODE_PROMPT = """You are a Python developer. Generate COMPLETE Python code for EVERY module in the design below.

RULES:
1. You MUST emit a separate ---FILE: ... --- block for EACH module listed in the Package/Module Structure. Do not skip any.
2. Use the EXACT module paths and class/function names from the design. Match dataclasses and services exactly.
3. Implement every dataclass with the fields specified; implement every service with the methods specified.
4. Write only valid Python 3 with type hints. No COBOL, no placeholders. Full implementations.
5. For each file use this format exactly:

---FILE: path/to/module.py---
# Python code
---END FILE---

List of modules you MUST generate (from the design):"""


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


def _file_checklist(design: dict | None, target: str) -> str:
    """Build explicit list of files the LLM must generate."""
    if not design:
        return "(Parse the design document above and list every .scala or .py file; then generate each one.)"
    ext = ".py" if target == "python" else ".scala"
    packages = design.get("packages", [])
    if packages:
        lines = [f"  - {p.get('path', '')}" for p in packages if p.get("path")]
        return "\n".join(lines) if lines else "(See Package Structure in design.)"
    case_classes = design.get("case_classes", [])
    services = design.get("services", [])
    paths = []
    pkg_sep = "/" if target == "scala" else "/"
    for c in case_classes:
        pkg = (c.get("package") or c.get("module", "")).replace(".", pkg_sep)
        name = c.get("name", "")
        if name:
            paths.append(f"  - {pkg}/{name}{ext}".replace("//", "/").strip("/"))
    for s in services:
        pkg = (s.get("package") or s.get("module", "")).replace(".", pkg_sep)
        name = s.get("name", "")
        if name:
            paths.append(f"  - {pkg}/{name}{ext}".replace("//", "/").strip("/"))
    if paths:
        return "\n".join(paths)
    return "(See design document for every file to generate.)"


class ScalaCodeAgent(BaseAgent):
    agent_id = "agent_7"

    def run(self, context: AgentContext) -> AgentResult:
        target = get_target_language()
        pseudo_doc = context.artifact_paths.get("05_Pseudocode_Language_Neutral.docx")
        design_doc = context.artifact_paths.get("06_Scala_Design_Specification.docx")
        pseudo_text = read_docx_text(pseudo_doc) if pseudo_doc else ""
        design_text = read_docx_text(design_doc) if design_doc else ""
        design_json = _load_design_json(context)
        file_checklist = _file_checklist(design_json, target)

        if target == "python":
            prompt = (
                PYTHON_CODE_PROMPT
                + "\n"
                + file_checklist
                + "\n\n--- Pseudocode ---\n"
                + pseudo_text[:20000]
                + "\n\n--- Python Design (implement EVERY module above) ---\n"
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
                + "\n\n--- Pseudocode ---\n"
                + pseudo_text[:20000]
                + "\n\n--- Scala Design (implement EVERY file above) ---\n"
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
