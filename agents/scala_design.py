"""Agent 6: Target-language Design (Scala or Python). Minute-level structure and mapping. JSON populated from LLM."""
import json
import re
from pathlib import Path

from .base import BaseAgent, AgentContext, AgentResult
from llm import generate, get_model_for_agent, get_temperature, get_target_language
from documents.writer import write_docx
from documents.reader import read_docx_text


SCALA_DESIGN_PROMPT = """You are a Scala architect. You are given three inputs: (1) Business Logic — rules and domain; (2) Technical Design — I/O, loops, error handling per program; (3) Pseudocode — step-by-step flow. Use the PSEUDOCODE as the primary flow; use BUSINESS LOGIC to assign rules and domain concepts to your classes/services; use TECHNICAL DESIGN to align packages and services with programs, I/O, and error handling. Produce a MINUTE-LEVEL design so the code generator can implement every file exactly.

You MUST specify:

1. Package Structure
   - List EVERY file with its full package path (e.g. com.example.app.Main -> com/example/app/Main.scala). Use a tree or numbered list. No file may be omitted.

2. Case Classes
   - For EACH case class: full name, package path, and EVERY field with name and type (e.g. status: String, timestamp: LocalDateTime). Include any type parameters.

3. Services
   - For EACH service (object or class): full name, package path, and EVERY method signature or responsibility (e.g. def execute(op: DatabaseOperation): Try[Unit]). List all public methods.

4. COBOL to Scala Mapping
   - Table: COBOL concept | Scala concept (package.ClassName or package.ObjectName). One row per concept.

5. Per-File Implementation (Clear Cut-Outs)
   - For EACH file in the Package Structure, list:
     (a) File path (e.g. com/example/app/Main.scala)
     (b) Purpose: one sentence on what this file is responsible for
     (c) Logic to implement: bullet list of what this file MUST do (e.g. "Parse args and delegate to DatabaseService", "Implement execute(): open connection, run SQL, handle SQLCODE", "Hold status field; used by BR-01"). Be specific so the code generator knows exactly what to write in that file. No file may be omitted.

You MUST NOT: write Scala code or skip any class/file. Be exhaustive.

Use exactly these section titles on their own line:
- Package Structure
- Case Classes
- Services
- COBOL to Scala Mapping
- Per-File Implementation (Clear Cut-Outs)

End with: ---END---

Then output a JSON block that the code generator will use. Include file_responsibilities with path, purpose, and logic array for each file. Use exactly this format (no other text around it):
```json
{"packages": [{"path": "com/example/app/Main.scala", "description": "Main entry"}], "case_classes": [{"name": "RecordStatus", "package": "com.example.model", "fields": [{"name": "status", "type": "String"}]}], "services": [{"name": "DatabaseService", "package": "com.example.service", "methods": ["def execute(op: DatabaseOperation): Try[Unit]"]}], "mapping": [{"cobol_concept": "Record Status", "scala_concept": "com.example.model.RecordStatus"}], "file_responsibilities": [{"path": "com/example/app/Main.scala", "purpose": "Entry point; orchestrates flow", "logic": ["Parse command-line args", "Call DatabaseService.execute with operation", "Exit with return code"]}]}
```"""


PYTHON_DESIGN_PROMPT = """You are a Python architect. You are given three inputs: (1) Business Logic — rules and domain; (2) Technical Design — I/O, loops, error handling per program; (3) Pseudocode — step-by-step flow. Use the PSEUDOCODE as the primary flow; use BUSINESS LOGIC to assign rules and domain concepts to your modules/classes; use TECHNICAL DESIGN to align package structure with programs, I/O, and error handling. Produce a MINUTE-LEVEL design so the code generator can implement every module exactly.

You MUST specify:

1. Package and Module Structure
   - List EVERY module with its path (e.g. app/main.py, model/record_status.py). Use a tree or numbered list. No module may be omitted.

2. Data Classes / Dataclasses
   - For EACH dataclass: full name, module path, and EVERY field with name and type (e.g. status: str, timestamp: datetime). Include typing imports if needed.

3. Services and Modules
   - For EACH service module or class: full name, module path, and EVERY function or method signature (e.g. def execute(op: DatabaseOperation) -> None). List all public APIs.

4. COBOL to Python Mapping
   - Table: COBOL concept | Python concept (module.ClassName or module.function_name). One row per concept.

5. Per-File Implementation (Clear Cut-Outs)
   - For EACH module in the Package Structure, list:
     (a) Module path (e.g. app/main.py)
     (b) Purpose: one sentence on what this module is responsible for
     (c) Logic to implement: bullet list of what this module MUST do. Be specific so the code generator knows exactly what to write. No module may be omitted.

You MUST NOT: write Python code or skip any class/module. Be exhaustive.

Use exactly these section titles on their own line:
- Package and Module Structure
- Data Classes / Dataclasses
- Services and Modules
- COBOL to Python Mapping
- Per-File Implementation (Clear Cut-Outs)

End with: ---END---

Then output a JSON block that the code generator will use. Include file_responsibilities with path, purpose, and logic array. Use exactly this format (no other text around it):
```json
{"packages": [{"path": "app/main.py", "description": "Main entry"}], "case_classes": [{"name": "RecordStatus", "module": "model.record_status", "fields": [{"name": "status", "type": "str"}]}], "services": [{"name": "DatabaseService", "module": "service.database", "methods": ["def execute(op: DatabaseOperation) -> None"]}], "mapping": [{"cobol_concept": "Record Status", "scala_concept": "model.record_status.RecordStatus"}], "file_responsibilities": [{"path": "app/main.py", "purpose": "Entry point", "logic": ["Parse args", "Call DatabaseService.execute", "Exit with code"]}]}
```"""


def _parse_json_block(text: str) -> dict | None:
    try:
        if "---END---" in text:
            text = text.split("---END---", 1)[1]
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if m:
            return json.loads(m.group(1).strip())
        return None
    except (json.JSONDecodeError, IndexError):
        return None


def _parse_design_sections_into_json(response: str) -> dict:
    """Fallback: extract package paths, case class names, service names from section text."""
    packages = []
    case_classes = []
    services = []
    mapping = []
    section = None
    for line in response.split("\n"):
        stripped = line.strip()
        if "---END---" in stripped:
            break
        if re.match(r"^[-*]+\s*Package Structure", stripped, re.I) or "Package and Module" in stripped:
            section = "packages"
            continue
        if re.match(r"^[-*]+\s*Case Classes", stripped, re.I) or "Data Classes" in stripped:
            section = "case_classes"
            continue
        if re.match(r"^[-*]+\s*Services", stripped, re.I):
            section = "services"
            continue
        if "COBOL to Scala" in stripped or "COBOL to Python" in stripped:
            section = "mapping"
            continue
        if not stripped or stripped.startswith("|") and "---" in stripped:
            continue
        if section == "packages":
            # Line like "1. com/example/app/Main.scala" or "├── Main.scala" or "com.example.app.Main"
            if ".scala" in stripped or ".py" in stripped:
                path = re.sub(r"^[\s├│└─]*", "", stripped).strip()
                path = re.sub(r"^\d+\.\s*", "", path)  # strip "1. ", "2. " numbered list prefix
                if path and path not in ("```", "```scala"):
                    packages.append({"path": path, "description": ""})
            elif stripped.startswith("com.") or stripped.startswith("app.") or "/" in stripped:
                path = stripped.replace(".", "/").rstrip("/")
                if not path.endswith(".scala") and not path.endswith(".py"):
                    path += ".scala" if ".scala" in response else ".py"
                packages.append({"path": path, "description": ""})
        elif section == "case_classes":
            # "RecordStatus(status: String)" or "RecordStatus"
            m = re.match(r"^([A-Za-z0-9_]+)\s*\(([^)]*)\)", stripped)
            if m:
                case_classes.append({"name": m.group(1), "package": "", "fields": [{"name": "x", "type": "String"}]})
            elif stripped and stripped[0].isupper() and "(" not in stripped and ":" in response:
                case_classes.append({"name": stripped.split("(")[0].strip(), "package": "", "fields": []})
        elif section == "services":
            if stripped and stripped[0].isupper() and "Service" in stripped:
                services.append({"name": stripped.split("+")[0].strip().split()[0], "package": "", "methods": []})
        elif section == "mapping" and "|" in stripped and stripped.count("|") >= 2:
            parts = [p.strip() for p in stripped.split("|")[1:-1]]
            if len(parts) >= 2 and parts[0] and parts[1]:
                mapping.append({"cobol_concept": parts[0], "scala_concept": parts[1]})
    file_responsibilities = [{"path": p.get("path", ""), "purpose": p.get("description", "See DOCX"), "logic": [p.get("description", "Implement as per DOCX")]} for p in packages] if packages else []
    return {
        "packages": packages or [{"path": "app/Main.scala", "description": "See DOCX"}],
        "case_classes": case_classes,
        "services": services,
        "mapping": mapping,
        "file_responsibilities": file_responsibilities,
    }


def _docx_structured_summary_from_json(design: dict) -> str:
    """Build DOCX section that matches scala_design.json."""
    intro = (
        "The following matches scala_design.json. The code generator uses this structure to produce every file.\n\n"
    )
    lines = []
    if design.get("file_responsibilities"):
        lines.append("Per-file implementation (clear cut-outs):")
        for fr in design["file_responsibilities"]:
            lines.append(f"  {fr.get('path', '')}")
            lines.append(f"    Purpose: {fr.get('purpose', '')}")
            for logic in fr.get("logic", [])[:10]:
                lines.append(f"    - {logic}")
        lines.append("")
    if design.get("packages"):
        lines.append("Packages / files:")
        for p in design["packages"]:
            lines.append(f"  {p.get('path', '')} — {p.get('description', '')}")
        lines.append("")
    if design.get("case_classes"):
        lines.append("Case classes:")
        for c in design["case_classes"]:
            fields = c.get("fields", [])
            fs = ", ".join(f"{f.get('name', '')}: {f.get('type', '')}" for f in fields)
            lines.append(f"  {c.get('name', '')}({fs}) in {c.get('package', '')}")
        lines.append("")
    if design.get("services"):
        lines.append("Services:")
        for s in design["services"]:
            methods = s.get("methods", [])
            lines.append(f"  {s.get('name', '')} in {s.get('package', '')}: {methods}")
        lines.append("")
    if design.get("mapping"):
        lines.append("COBOL to Scala/Python mapping:")
        for m in design["mapping"]:
            lines.append(f"  {m.get('cobol_concept', '')} -> {m.get('scala_concept', '')}")
    if not lines:
        return intro + "No structured design extracted; see narrative above."
    return intro + "\n".join(lines)


def _normalize_section_title(line: str) -> str | None:
    s = line.strip()
    if not s or s == "---END---":
        return None
    for title in ("Package Structure", "Case Classes", "Services", "COBOL to Scala Mapping", "Per-File Implementation (Clear Cut-Outs)",
                  "Package and Module Structure", "Data Classes / Dataclasses", "Services and Modules", "COBOL to Python Mapping"):
        if re.match(r"^[-*]+\s*" + re.escape(title) + r"\s*$", s, re.I) or s.lower() == title.lower():
            return title
    return None


class ScalaDesignAgent(BaseAgent):
    agent_id = "agent_6"

    def run(self, context: AgentContext) -> AgentResult:
        target = get_target_language()
        business_doc = context.artifact_paths.get("03_Business_Logic_Specification.docx")
        technical_doc = context.artifact_paths.get("04_Technical_Design_COBOL.docx")
        pseudo_doc = context.artifact_paths.get("05_Pseudocode_Language_Neutral.docx")
        business_text = read_docx_text(business_doc) if business_doc else ""
        technical_text = read_docx_text(technical_doc) if technical_doc else ""
        pseudo_text = read_docx_text(pseudo_doc) if pseudo_doc else ""
        # All three inputs; cap total context to avoid very long runs (agent_6 can be slow with huge prompts)
        max_per_doc = 18000  # ~18k chars each keeps prompt manageable for faster inference
        context_block = (
            "\n\n--- Business Logic (rules, domain terms, edge cases — map to your classes/services) ---\n"
            + business_text[:max_per_doc]
            + "\n\n--- Technical Design (I/O per program, loops, error handling — align packages/services) ---\n"
            + technical_text[:max_per_doc]
            + "\n\n--- Pseudocode (primary flow — implement this step-by-step in your design) ---\n"
            + pseudo_text[:max_per_doc]
        )
        if target == "python":
            prompt = PYTHON_DESIGN_PROMPT + context_block
            doc_title = "Python Design Specification"
        else:
            prompt = SCALA_DESIGN_PROMPT + context_block
            doc_title = "Scala Design Specification"
        model = get_model_for_agent(self.agent_id)
        response = generate(prompt, model=model, temperature=get_temperature(self.agent_id))

        sections = []
        current_title = ""
        current_body = []
        for line in response.split("\n"):
            if line.strip() == "---END---":
                break
            norm = _normalize_section_title(line)
            if norm:
                if current_title or current_body:
                    sections.append({"title": current_title or "Section", "body": "\n".join(current_body)})
                current_title = norm
                current_body = []
            elif line.startswith("- ") and not line.startswith("-  "):
                if current_title or current_body:
                    sections.append({"title": current_title or "Section", "body": "\n".join(current_body)})
                current_title = line.strip().lstrip("- ")
                current_body = []
            else:
                current_body.append(line)
        if current_title or current_body:
            sections.append({"title": current_title or "Section", "body": "\n".join(current_body)})
        if not sections:
            sections = [{"title": doc_title, "body": response[:12000]}]

        parsed = _parse_json_block(response)
        if parsed and isinstance(parsed, dict):
            design = {
                "packages": parsed.get("packages", []),
                "case_classes": parsed.get("case_classes", []),
                "services": parsed.get("services", []),
                "mapping": parsed.get("mapping", []),
                "file_responsibilities": parsed.get("file_responsibilities", []),
            }
            if not design["packages"]:
                design["packages"] = [{"path": "app/Main.scala", "description": "See DOCX"}]
            if not design["file_responsibilities"] and design["packages"]:
                design["file_responsibilities"] = [
                    {"path": p.get("path", ""), "purpose": p.get("description", "See DOCX"), "logic": [p.get("description", "Implement as per design")]}
                    for p in design["packages"]
                ]
        else:
            design = _parse_design_sections_into_json(response)
            design.setdefault("file_responsibilities", [])

        sections.append({
            "title": "Structured Summary (aligned with scala_design.json)",
            "body": _docx_structured_summary_from_json(design),
        })

        out_dir = Path(context.output_dir) / "06_scala_design"
        out_dir.mkdir(parents=True, exist_ok=True)
        docx_path = out_dir / "06_Scala_Design_Specification.docx"
        write_docx(sections, docx_path, title=doc_title)

        json_path = out_dir / "scala_design.json"
        with open(json_path, "w") as f:
            json.dump(design, f, indent=2)

        return AgentResult(
            artifacts={
                "06_Scala_Design_Specification.docx": str(docx_path),
                "scala_design.json": str(json_path),
            }
        )
