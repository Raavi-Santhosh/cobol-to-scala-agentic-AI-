"""Agent 5: Pseudocode. Language-neutral, minute-level step-by-step logic. DOCX and JSON aligned."""
import json
import re
from pathlib import Path

from .base import BaseAgent, AgentContext, AgentResult
from llm import generate, get_model_for_agent, get_temperature
from documents.writer import write_docx
from documents.reader import read_docx_text


PSEUDOCODE_PROMPT = """You are a language-neutral algorithm designer. Produce ELABORATE PSEUDOCODE so a downstream design agent gets a complete picture of the COBOL system without reading other documents.

You MUST weave in BOTH business logic AND technical detail:

1. Main Flow
   - List EVERY step (initialization, reads, decisions, writes, commits, etc.). Number each step; use sub-steps (2a, 2b) for branches.
   - For each step that implements a business rule, cite the rule (e.g. "per BR-01" or "business rule: audit trail for insert/update").
   - For each step that involves I/O, name the program and operation (e.g. "DB2HNDL: INSERT into PORTFOLIO"; "FILEHNDL: READ INPUT-FILE until end").
   - For error handling or restart logic, state explicitly (e.g. "on SQLCODE < 0: rollback and exit"; "commit only after all operations succeed").

2. Control Flow
   - List EVERY decision: condition and action. Use "IF ... THEN ..." or "WHEN ... THEN ...".
   - Include loop exit conditions, retry logic (e.g. "deadlock -911: retry up to 3 times"), and any checkpoint/restart conditions.

3. Data Transformations
   - For each transformation: what is read or computed, how it changes, what is written. Name key fields and which program or service performs it.
   - Where a transformation aligns to a business rule or technical pattern, say so briefly.

Your output must be detailed enough that a design agent can derive packages, case classes, and services (Scala or Python) from this pseudocode alone, while also having business and technical docs for traceability. Do NOT use COBOL or Scala/Python syntax. Be exhaustive.

Use exactly these section titles on their own line (with a leading hyphen and space):
- Main Flow
- Control Flow
- Data Transformations

End with: ---END---

Then output a JSON block that downstream agents will parse. Use exactly this format (no other text around it):
```json
{"main_flow": [{"step": 1, "description": "..."}, {"step": 2, "description": "..."}], "control_flow": [{"condition": "...", "action": "..."}], "data_transformations": [{"description": "...", "inputs": "...", "outputs": "..."}]}
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


def _parse_sections_into_pseudo(response: str) -> dict:
    """Fallback: parse Main Flow, Control Flow, Data Transformations from response text."""
    main_flow = []
    control_flow = []
    data_transformations = []
    section = None
    for line in response.split("\n"):
        stripped = line.strip()
        # Section headers: "- Main Flow" or "**Main Flow**" or "Main Flow"
        if re.match(r"^[-*]+\s*Main Flow", stripped, re.I) or stripped.lower() == "main flow":
            section = "main_flow"
            continue
        if re.match(r"^[-*]+\s*Control Flow", stripped, re.I) or stripped.lower() == "control flow":
            section = "control_flow"
            continue
        if re.match(r"^[-*]+\s*Data Transformations", stripped, re.I) or stripped.lower() == "data transformations":
            section = "data_transformations"
            continue
        if stripped == "---END---":
            break
        if not stripped:
            continue
        # Numbered step: 1. ... or 2a. ...
        step_m = re.match(r"^(\d+[a-z]?)[.)]\s*(.+)", stripped)
        if section == "main_flow" and step_m:
            main_flow.append({"step": step_m.group(1), "description": step_m.group(2).strip()})
        elif section == "main_flow" and stripped.startswith("*"):
            main_flow.append({"step": str(len(main_flow) + 1), "description": stripped.lstrip("* ").strip()})
        elif section == "control_flow" and stripped:
            if " THEN " in stripped or " then " in stripped:
                parts = re.split(r"\s+THEN\s+", stripped, 1, flags=re.I)
                control_flow.append({"condition": parts[0].strip(), "action": parts[1].strip() if len(parts) > 1 else ""})
            else:
                control_flow.append({"condition": stripped, "action": ""})
        elif section == "data_transformations" and stripped:
            data_transformations.append({"description": stripped, "inputs": "", "outputs": ""})
    return {
        "main_flow": main_flow or [{"step": 1, "description": "See DOCX Main Flow section."}],
        "control_flow": control_flow,
        "data_transformations": data_transformations,
    }


def _docx_structured_summary_from_json(pseudo: dict) -> str:
    """Build narrative section that exactly reflects pseudocode.json."""
    intro = (
        "The following is the structured summary that matches pseudocode.json. "
        "Downstream agents can use this section or the JSON for the same information.\n\n"
    )
    lines = []
    if pseudo.get("main_flow"):
        lines.append("Main flow (from JSON):")
        for m in pseudo["main_flow"]:
            step = m.get("step", "")
            desc = m.get("description", "")
            lines.append(f"  {step}. {desc}")
        lines.append("")
    if pseudo.get("control_flow"):
        lines.append("Control flow (from JSON):")
        for c in pseudo["control_flow"]:
            cond = c.get("condition", "")
            action = c.get("action", "")
            if action:
                lines.append(f"  IF {cond} THEN {action}")
            else:
                lines.append(f"  {cond}")
        lines.append("")
    if pseudo.get("data_transformations"):
        lines.append("Data transformations (from JSON):")
        for d in pseudo["data_transformations"]:
            desc = d.get("description", "")
            inputs = d.get("inputs", "")
            outputs = d.get("outputs", "")
            if inputs or outputs:
                lines.append(f"  {desc} (inputs: {inputs}; outputs: {outputs})")
            else:
                lines.append(f"  {desc}")
    if not lines:
        return intro + "No structured pseudocode extracted; see narrative sections above."
    return intro + "\n".join(lines)


def _normalize_section_title(line: str) -> str | None:
    """Recognize section headers: '- Main Flow', '**Main Flow**', etc."""
    s = line.strip()
    if not s or s == "---END---":
        return None
    for title in ("Main Flow", "Control Flow", "Data Transformations"):
        if re.match(r"^[-*]+\s*" + re.escape(title) + r"\s*$", s, re.I) or s.lower() == title.lower():
            return title
    return None


class PseudocodeAgent(BaseAgent):
    agent_id = "agent_5"

    def run(self, context: AgentContext) -> AgentResult:
        business_doc = context.artifact_paths.get("03_Business_Logic_Specification.docx")
        technical_doc = context.artifact_paths.get("04_Technical_Design_COBOL.docx")
        business_text = read_docx_text(business_doc) if business_doc else ""
        technical_text = read_docx_text(technical_doc) if technical_doc else ""
        prompt = (
            PSEUDOCODE_PROMPT
            + "\n\n--- Business Logic (use rules and domain terms; cite BR-ids where steps implement them) ---\n"
            + business_text[:30000]
            + "\n\n--- Technical Design (use I/O, loops, error handling, restart logic per program) ---\n"
            + technical_text[:30000]
        )
        model = get_model_for_agent(self.agent_id)
        response = generate(prompt, model=model, temperature=get_temperature(self.agent_id))

        # Parse sections: accept "- Title" or "**Title**"
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
                # Alternative: line like "- Something" that isn't a section
                if current_title or current_body:
                    sections.append({"title": current_title or "Section", "body": "\n".join(current_body)})
                current_title = line.strip().lstrip("- ")
                current_body = []
            else:
                current_body.append(line)
        if current_title or current_body:
            sections.append({"title": current_title or "Section", "body": "\n".join(current_body)})
        if not sections:
            sections = [{"title": "Pseudocode (Language-Neutral)", "body": response[:12000]}]

        # Parse JSON so we can populate pseudocode.json and add aligned DOCX section
        parsed = _parse_json_block(response)
        if parsed and isinstance(parsed, dict):
            pseudo = {
                "main_flow": parsed.get("main_flow", []),
                "control_flow": parsed.get("control_flow", []),
                "data_transformations": parsed.get("data_transformations", []),
            }
            if not pseudo["main_flow"]:
                pseudo["main_flow"] = [{"step": 1, "description": "See DOCX Main Flow section."}]
        else:
            pseudo = _parse_sections_into_pseudo(response)

        # Append structured summary so DOCX and JSON stay aligned
        sections.append({
            "title": "Structured Summary (aligned with pseudocode.json)",
            "body": _docx_structured_summary_from_json(pseudo),
        })

        out_dir = Path(context.output_dir) / "05_pseudocode"
        out_dir.mkdir(parents=True, exist_ok=True)
        docx_path = out_dir / "05_Pseudocode_Language_Neutral.docx"
        write_docx(sections, docx_path, title="Pseudocode (Language-Neutral)")

        json_path = out_dir / "pseudocode.json"
        with open(json_path, "w") as f:
            json.dump(pseudo, f, indent=2)

        return AgentResult(
            artifacts={
                "05_Pseudocode_Language_Neutral.docx": str(docx_path),
                "pseudocode.json": str(json_path),
            }
        )
