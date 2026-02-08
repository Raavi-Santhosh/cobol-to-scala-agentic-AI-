"""Agent 3: Business Logic Extraction. WHAT does the system do for the business?
Output is minute-level so downstream agents understand clearly. JSON populated from LLM response."""
import json
import re
from pathlib import Path

from .base import BaseAgent, AgentContext, AgentResult
from llm import generate, get_model_for_agent, get_temperature
from documents.writer import write_docx
from documents.reader import read_docx_text, read_cobol_directory


BUSINESS_LOGIC_PROMPT = """You are a senior business analyst. Document at a MINUTE level of detail so downstream agents can understand every rule and decision exactly.

You do NOT care about: file names, variable names, performance, COBOL syntax.

Your ONLY goal: Answer WHAT does the system do for the business? Be exhaustive and precise.

Produce:

1. Business Rules
   - List EVERY business rule. Give each a unique ID (BR-01, BR-02, ...) and a full, unambiguous description.
   - Example: "BR-01: If employee type is CONTRACT then no tax is applied to the payment."

2. Decision Logic
   - List EVERY decision: condition and outcome. Use explicit "IF <condition> THEN <outcome>" or "WHEN X THEN Y".
   - Example: "If record status is 'Y' then extra value is added to the calculated amount."

3. Domain Explanations
   - Define every domain term used (e.g. WS-RECORD, amount, status, multiplier). Explain what each means in business terms.

4. Edge Cases
   - List every edge case or exception with a concrete example. Example: "When status is not Y, extra value is ignored."

You MUST NOT: mention files, loops, COBOL, or Scala. Use business language only.

Format with these section titles on their own line:
- Business Rules
- Decision Logic
- Domain Explanations
- Edge Cases

End with: ---END---

Then, on a new line, output a JSON block that downstream agents will parse. Use exactly this format (no other text around it):
```json
{"rules": [{"id": "BR-01", "description": "..."}], "decision_logic": [{"condition": "...", "outcome": "..."}], "domain_terms": [{"term": "...", "meaning": "..."}], "edge_cases": [{"description": "...", "example": "..."}]}
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


def _parse_fallback_rules(response: str) -> dict:
    """If no JSON block, try to extract rules from section text."""
    rules = []
    decision_logic = []
    edge_cases = []
    domain_terms = []
    section = None
    for line in response.split("\n"):
        if line.strip().startswith("- ") and not line.strip().startswith("-  "):
            title = line.strip().lstrip("- ").strip()
            if title == "Business Rules":
                section = "rules"
            elif title == "Decision Logic":
                section = "decision_logic"
            elif title == "Domain Explanations":
                section = "domain"
            elif title == "Edge Cases":
                section = "edge"
            else:
                section = None
            continue
        if section == "rules" and line.strip():
            desc = re.sub(r"^(?:BR-\d+[.:]\s*|\d+\.\s*)", "", line.strip()).strip() or line.strip()
            if desc:
                rules.append({"id": f"BR-{len(rules)+1:02d}", "description": desc})
        elif section == "decision_logic" and line.strip() and not line.strip().startswith("-"):
            decision_logic.append({"condition": line.strip(), "outcome": ""})
        elif section == "edge" and line.strip() and not line.strip().startswith("-"):
            edge_cases.append({"description": line.strip(), "example": ""})
    return {
        "rules": rules,
        "decision_logic": decision_logic,
        "domain_terms": domain_terms,
        "edge_cases": edge_cases,
    }


class BusinessLogicAgent(BaseAgent):
    agent_id = "agent_3"

    def run(self, context: AgentContext) -> AgentResult:
        overview_path = context.artifact_paths.get("01_COBOL_Codebase_Overview.docx")
        dep_docx = context.artifact_paths.get("02_Dependency_and_Call_Graph.docx")
        dep_json_path = context.artifact_paths.get("dependency_graph.json")
        overview_text = read_docx_text(overview_path) if overview_path else ""
        dep_text = read_docx_text(dep_docx) if dep_docx else ""
        dep_json = ""
        if dep_json_path and Path(dep_json_path).exists():
            dep_json = Path(dep_json_path).read_text()
        cobol_files = read_cobol_directory(context.cobol_dir)
        source_preview = "\n".join(f"{p}:\n{c[:2000]}" for p, c in list(cobol_files.items())[:15])
        prompt = (
            BUSINESS_LOGIC_PROMPT
            + "\n\n--- Overview ---\n"
            + overview_text
            + "\n\n--- Dependency ---\n"
            + dep_text
            + "\n\n--- Dependency JSON ---\n"
            + dep_json[:6000]
            + "\n\n--- Source (excerpts) ---\n"
            + source_preview[:20000]
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
            sections = [{"title": "Business Logic Specification", "body": response[:12000]}]

        out_dir = Path(context.output_dir) / "03_business"
        out_dir.mkdir(parents=True, exist_ok=True)
        docx_path = out_dir / "03_Business_Logic_Specification.docx"
        write_docx(sections, docx_path, title="Business Logic Specification")

        parsed = _parse_json_block(response)
        if parsed and isinstance(parsed, dict):
            rules = {
                "rules": parsed.get("rules", []),
                "decision_logic": parsed.get("decision_logic", []),
                "domain_terms": parsed.get("domain_terms", []),
                "edge_cases": parsed.get("edge_cases", []),
            }
        else:
            rules = _parse_fallback_rules(response)
            if not rules.get("domain_terms"):
                rules["domain_terms"] = []

        json_path = out_dir / "business_rules.json"
        with open(json_path, "w") as f:
            json.dump(rules, f, indent=2)

        return AgentResult(
            artifacts={
                "03_Business_Logic_Specification.docx": str(docx_path),
                "business_rules.json": str(json_path),
            }
        )
