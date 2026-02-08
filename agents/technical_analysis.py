"""Agent 4: Technical Analysis. HOW does the system achieve the business logic?
Output is minute-level so downstream agents understand clearly. JSON populated from LLM response."""
import json
import re
from pathlib import Path

from .base import BaseAgent, AgentContext, AgentResult
from llm import generate, get_model_for_agent, get_temperature
from documents.writer import write_docx
from documents.reader import read_docx_text, read_cobol_directory


TECHNICAL_PROMPT = """You are a legacy system engineer. Document at a MINUTE level of detail so downstream agents understand exactly how the system works technically.

Goal: Answer HOW does the system achieve the business logic? Be exhaustive and precise. Do NOT change business meaning or simplify logic.

Include:

1. File and I/O Patterns
   - For EACH program or file: name the file/program, operation (read/write/update), record or data structure, and any key details (e.g. sequential, keyed). List every relevant FD, SELECT, OPEN, READ, WRITE.

2. Looping Behavior
   - For EACH loop: which program, what type (PERFORM UNTIL, VARYING, etc.), exit condition, and what the loop does in one line.

3. Cursor and Position Logic
   - Any record position, cursor, or pointer logic: which program, where it is set/used, and how it advances or resets.

4. Error Handling
   - For EACH program or module: how errors are detected, what happens (abend, return code, message), and any error copybook or paragraph.

5. Restart and Checkpoint Logic
   - Any checkpoint, restart, or recovery logic: where and how.

Use section titles on their own line:
- File and I/O Patterns
- Looping Behavior
- Cursor and Position Logic
- Error Handling
- Restart and Checkpoint Logic

End with: ---END---

Then, on a new line, output a JSON block that downstream agents will parse. Use exactly this format (no other text around it):
```json
{"file_patterns": [{"program": "...", "file_or_resource": "...", "operation": "...", "description": "..."}], "loops": [{"program": "...", "type": "...", "exit_condition": "...", "description": "..."}], "cursor_logic": [{"program": "...", "description": "..."}], "error_handling": [{"program": "...", "mechanism": "...", "description": "..."}], "restart_checkpoint": [{"program": "...", "description": "..."}]}
```"""


def _parse_json_block(text: str) -> dict | None:
    """Extract JSON from ```json ... ``` block after ---END---."""
    try:
        if "---END---" in text:
            text = text.split("---END---", 1)[1]
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if m:
            return json.loads(m.group(1).strip())
        return None
    except (json.JSONDecodeError, IndexError):
        return None


def _docx_structured_summary_from_json(tech: dict) -> str:
    """Build narrative section that exactly reflects technical_analysis.json so DOCX and JSON stay aligned."""
    intro = (
        "The following is the structured summary that matches technical_analysis.json. "
        "Downstream agents can use this section or the JSON for the same information.\n\n"
    )
    lines = []
    if tech.get("file_patterns"):
        lines.append("File and I/O patterns (from JSON):")
        for f in tech["file_patterns"]:
            prog = f.get("program", "")
            fname = f.get("file_or_resource", "")
            op = f.get("operation", "")
            desc = f.get("description", "")
            lines.append(f"  Program: {prog}; File: {fname}; Operation: {op}. {desc}")
        lines.append("")
    if tech.get("loops"):
        lines.append("Looping behavior (from JSON):")
        for l in tech["loops"]:
            prog = l.get("program", "")
            typ = l.get("type", "")
            exit_ = l.get("exit_condition", "")
            desc = l.get("description", "")
            lines.append(f"  Program: {prog}; Type: {typ}; Exit: {exit_}. {desc}")
        lines.append("")
    if tech.get("cursor_logic"):
        lines.append("Cursor/position logic (from JSON):")
        for c in tech["cursor_logic"]:
            prog = c.get("program", "")
            desc = c.get("description", "")
            lines.append(f"  {prog}: {desc}")
        lines.append("")
    if tech.get("error_handling"):
        lines.append("Error handling (from JSON):")
        for e in tech["error_handling"]:
            prog = e.get("program", "")
            mech = e.get("mechanism", "")
            desc = e.get("description", "")
            lines.append(f"  {prog}; Mechanism: {mech}. {desc}")
        lines.append("")
    if tech.get("restart_checkpoint"):
        lines.append("Restart/checkpoint logic (from JSON):")
        for r in tech["restart_checkpoint"]:
            prog = r.get("program", "")
            desc = r.get("description", "")
            lines.append(f"  {prog}: {desc}")
    if not lines:
        return intro + "No structured technical data extracted; see narrative sections above."
    return intro + "\n".join(lines)


def _parse_fallback_technical(response: str) -> dict:
    """If no JSON block, build minimal structure from section headings."""
    file_patterns = []
    loops = []
    error_handling = []
    section = None
    for line in response.split("\n"):
        if line.strip().startswith("- ") and not line.strip().startswith("-  "):
            title = line.strip().lstrip("- ").strip()
            if "File" in title or "I/O" in title:
                section = "file"
            elif "Loop" in title:
                section = "loop"
            elif "Error" in title:
                section = "error"
            else:
                section = None
            continue
        if section == "file" and line.strip() and not line.strip().startswith("-"):
            file_patterns.append({"program": "", "file_or_resource": "", "operation": "", "description": line.strip()})
        elif section == "loop" and line.strip() and not line.strip().startswith("-"):
            loops.append({"program": "", "type": "", "exit_condition": "", "description": line.strip()})
        elif section == "error" and line.strip() and not line.strip().startswith("-"):
            error_handling.append({"program": "", "mechanism": "", "description": line.strip()})
    return {
        "file_patterns": file_patterns,
        "loops": loops,
        "cursor_logic": [],
        "error_handling": error_handling,
        "restart_checkpoint": [],
    }


class TechnicalAnalysisAgent(BaseAgent):
    agent_id = "agent_4"

    def run(self, context: AgentContext) -> AgentResult:
        business_doc = context.artifact_paths.get("03_Business_Logic_Specification.docx")
        business_text = read_docx_text(business_doc) if business_doc else ""
        cobol_files = read_cobol_directory(context.cobol_dir)
        source = "\n\n".join(f"--- {p} ---\n{c}" for p, c in cobol_files.items())[:35000]
        prompt = (
            TECHNICAL_PROMPT
            + "\n\n--- Business Logic ---\n"
            + business_text
            + "\n\n--- COBOL Source ---\n"
            + source
        )
        model = get_model_for_agent(self.agent_id)
        response = generate(prompt, model=model, temperature=get_temperature(self.agent_id))

        sections = []
        current_title = ""
        current_body = []
        for line in response.split("\n"):
            if line.strip() == "---END---":
                break
            if line.startswith("- ") and not line.startswith("-  "):
                if current_title or current_body:
                    sections.append({"title": current_title or "Section", "body": "\n".join(current_body)})
                current_title = line.strip().lstrip("- ")
                current_body = []
            else:
                current_body.append(line)
        if current_title or current_body:
            sections.append({"title": current_title or "Section", "body": "\n".join(current_body)})
        if not sections:
            sections = [{"title": "Technical Design (COBOL)", "body": response[:12000]}]

        # Parse JSON so we can add a DOCX section that exactly matches it (balance narrative + JSON)
        parsed = _parse_json_block(response)
        if parsed and isinstance(parsed, dict):
            tech = {
                "file_patterns": parsed.get("file_patterns", []),
                "loops": parsed.get("loops", []),
                "cursor_logic": parsed.get("cursor_logic", []),
                "error_handling": parsed.get("error_handling", []),
                "restart_checkpoint": parsed.get("restart_checkpoint", []),
            }
        else:
            tech = _parse_fallback_technical(response)

        # Append structured summary so DOCX narrative and JSON stay aligned for downstream agents
        sections.append({
            "title": "Structured Summary (aligned with technical_analysis.json)",
            "body": _docx_structured_summary_from_json(tech),
        })

        out_dir = Path(context.output_dir) / "04_technical"
        out_dir.mkdir(parents=True, exist_ok=True)
        docx_path = out_dir / "04_Technical_Design_COBOL.docx"
        write_docx(sections, docx_path, title="Technical Design (COBOL)")

        json_path = out_dir / "technical_analysis.json"
        with open(json_path, "w") as f:
            json.dump(tech, f, indent=2)

        return AgentResult(
            artifacts={
                "04_Technical_Design_COBOL.docx": str(docx_path),
                "technical_analysis.json": str(json_path),
            }
        )
