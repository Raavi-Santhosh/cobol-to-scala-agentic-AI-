"""Agent 5: Pseudocode. Language-neutral step-by-step logic. No COBOL or Scala syntax."""
from pathlib import Path
import json

from .base import BaseAgent, AgentContext, AgentResult
from llm import generate, get_model_for_agent, get_temperature
from documents.writer import write_docx
from documents.reader import read_docx_text


PSEUDOCODE_PROMPT = """You are a language-neutral algorithm designer.
Create pure pseudocode that exactly represents the system.

Include:
- Step-by-step logic
- Control flow
- Data transformations

You MUST NOT: use COBOL syntax, use Scala syntax, or optimize logic.

Use section titles on their own line:
- Main Flow
- Control Flow
- Data Transformations

End with: ---END---"""


class PseudocodeAgent(BaseAgent):
    agent_id = "agent_5"

    def run(self, context: AgentContext) -> AgentResult:
        business_doc = context.artifact_paths.get("03_Business_Logic_Specification.docx")
        technical_doc = context.artifact_paths.get("04_Technical_Design_COBOL.docx")
        business_text = read_docx_text(business_doc) if business_doc else ""
        technical_text = read_docx_text(technical_doc) if technical_doc else ""
        prompt = (
            PSEUDOCODE_PROMPT
            + "\n\n--- Business Logic ---\n"
            + business_text
            + "\n\n--- Technical Design ---\n"
            + technical_text
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
            sections = [{"title": "Pseudocode (Language-Neutral)", "body": response[:8000]}]

        out_dir = Path(context.output_dir) / "pseudocode"
        out_dir.mkdir(parents=True, exist_ok=True)
        docx_path = out_dir / "05_Pseudocode_Language_Neutral.docx"
        write_docx(sections, docx_path, title="Pseudocode (Language-Neutral)")

        pseudo = {"main_flow": [], "control_flow": [], "data_transformations": []}
        json_path = out_dir / "pseudocode.json"
        with open(json_path, "w") as f:
            json.dump(pseudo, f, indent=2)

        return AgentResult(
            artifacts={
                "05_Pseudocode_Language_Neutral.docx": str(docx_path),
                "pseudocode.json": str(json_path),
            }
        )
