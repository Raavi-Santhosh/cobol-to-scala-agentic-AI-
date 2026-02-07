"""Agent 3: Business Logic Extraction. WHAT does the system do for the business? No files, COBOL, Scala."""
from pathlib import Path
import json

from .base import BaseAgent, AgentContext, AgentResult
from llm import generate, get_model_for_agent, get_temperature
from documents.writer import write_docx
from documents.reader import read_docx_text, read_cobol_directory


BUSINESS_LOGIC_PROMPT = """You are a senior business analyst.
You do NOT care about: files, variables, performance, COBOL syntax.

Your ONLY goal: Answer WHAT does the system do for the business?

Produce:
- Business rules (numbered)
- Decision logic (e.g. If X then Y)
- Domain explanations
- Edge-case rules

Example style: "If employee type is CONTRACT then no tax is applied."

You MUST NOT: mention files, loops, COBOL, or Scala.

Format with these section titles on their own line:
- Business Rules
- Decision Logic
- Domain Explanations
- Edge Cases

End with: ---END---"""


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
            + dep_json
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
            sections = [{"title": "Business Logic Specification", "body": response[:8000]}]

        out_dir = Path(context.output_dir) / "business"
        out_dir.mkdir(parents=True, exist_ok=True)
        docx_path = out_dir / "03_Business_Logic_Specification.docx"
        write_docx(sections, docx_path, title="Business Logic Specification")

        rules = {"rules": [], "decision_logic": [], "edge_cases": []}
        json_path = out_dir / "business_rules.json"
        with open(json_path, "w") as f:
            json.dump(rules, f, indent=2)

        return AgentResult(
            artifacts={
                "03_Business_Logic_Specification.docx": str(docx_path),
                "business_rules.json": str(json_path),
            }
        )
