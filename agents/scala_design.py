"""Agent 6: Scala Design. Package structure, case classes, services, COBOL->Scala mapping. No code."""
from pathlib import Path
import json

from .base import BaseAgent, AgentContext, AgentResult
from llm import generate, get_model_for_agent, get_temperature
from documents.writer import write_docx
from documents.reader import read_docx_text


SCALA_DESIGN_PROMPT = """You are a Scala architect.
Design a clean Scala structure WITHOUT writing code.

Include:
- Package structure
- Case classes (names and main fields)
- Services (names and responsibilities)
- Mapping table: COBOL concept -> Scala concept

You MUST NOT: write Scala code or skip logic.

Use section titles on their own line:
- Package Structure
- Case Classes
- Services
- COBOL to Scala Mapping

End with: ---END---"""


class ScalaDesignAgent(BaseAgent):
    agent_id = "agent_6"

    def run(self, context: AgentContext) -> AgentResult:
        pseudo_doc = context.artifact_paths.get("05_Pseudocode_Language_Neutral.docx")
        pseudo_text = read_docx_text(pseudo_doc) if pseudo_doc else ""
        prompt = SCALA_DESIGN_PROMPT + "\n\n--- Pseudocode ---\n" + pseudo_text
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
            sections = [{"title": "Scala Design Specification", "body": response[:8000]}]

        out_dir = Path(context.output_dir) / "scala_design"
        out_dir.mkdir(parents=True, exist_ok=True)
        docx_path = out_dir / "06_Scala_Design_Specification.docx"
        write_docx(sections, docx_path, title="Scala Design Specification")

        design = {"packages": [], "case_classes": [], "services": [], "mapping": []}
        json_path = out_dir / "scala_design.json"
        with open(json_path, "w") as f:
            json.dump(design, f, indent=2)

        return AgentResult(
            artifacts={
                "06_Scala_Design_Specification.docx": str(docx_path),
                "scala_design.json": str(json_path),
            }
        )
