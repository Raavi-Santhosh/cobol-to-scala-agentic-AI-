"""Agent 9: Documentation. Final Scala-side business and technical design from all prior DOCX."""
from pathlib import Path

from .base import BaseAgent, AgentContext, AgentResult
from llm import generate, get_model_for_agent, get_temperature
from documents.writer import write_docx
from documents.reader import read_docx_text


DOCUMENTATION_PROMPT = """You are a technical writer.
Produce the final Scala-side documentation that combines business and technical design.

Use the content from all the provided prior documents to create one cohesive document:
- Business context and rules (from business logic spec)
- Technical design and structure (from technical and Scala design docs)
- Validation summary (from parity report)
- Any other relevant sections for a developer maintaining the Scala system

Do NOT invent content that is not in the sources.

Use clear section titles. End with: ---END---"""


class DocumentationAgent(BaseAgent):
    agent_id = "agent_9"

    def run(self, context: AgentContext) -> AgentResult:
        doc_keys = [
            "01_COBOL_Codebase_Overview.docx",
            "02_Dependency_and_Call_Graph.docx",
            "03_Business_Logic_Specification.docx",
            "04_Technical_Design_COBOL.docx",
            "05_Pseudocode_Language_Neutral.docx",
            "06_Scala_Design_Specification.docx",
            "08_Parity_and_Validation_Report.docx",
        ]
        parts = []
        for key in doc_keys:
            path = context.artifact_paths.get(key)
            if path and Path(path).exists():
                parts.append(f"--- {key} ---\n" + read_docx_text(path))
        combined = "\n\n".join(parts)[:60000]
        prompt = DOCUMENTATION_PROMPT + "\n\n" + combined
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
            sections = [{"title": "Scala Business and Technical Design", "body": response[:8000]}]

        out_dir = Path(context.output_dir) / "documentation"
        out_dir.mkdir(parents=True, exist_ok=True)
        docx_path = out_dir / "07_Scala_Business_and_Technical_Design.docx"
        write_docx(sections, docx_path, title="Scala Business and Technical Design")

        return AgentResult(artifacts={"07_Scala_Business_and_Technical_Design.docx": str(docx_path)})
