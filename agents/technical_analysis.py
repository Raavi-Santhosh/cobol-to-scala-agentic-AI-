"""Agent 4: Technical Analysis. HOW does the system achieve the business logic? No changing meaning."""
from pathlib import Path
import json

from .base import BaseAgent, AgentContext, AgentResult
from llm import generate, get_model_for_agent, get_temperature
from documents.writer import write_docx
from documents.reader import read_docx_text, read_cobol_directory


TECHNICAL_PROMPT = """You are a legacy system engineer.
Goal: Answer HOW does the system technically achieve the business logic?

Include:
- File reading patterns
- Looping behavior
- Cursor logic
- Error handling
- Restart/checkpoint logic

You MUST NOT: change business meaning or simplify logic.

Use section titles on their own line:
- File and I/O Patterns
- Looping Behavior
- Cursor and Position Logic
- Error Handling
- Restart and Checkpoint Logic

End with: ---END---"""


class TechnicalAnalysisAgent(BaseAgent):
    agent_id = "agent_4"

    def run(self, context: AgentContext) -> AgentResult:
        business_doc = context.artifact_paths.get("03_Business_Logic_Specification.docx")
        business_text = read_docx_text(business_doc) if business_doc else ""
        cobol_files = read_cobol_directory(context.cobol_dir)
        source = "\n\n".join(f"--- {p} ---\n{c}" for p, c in cobol_files.items())[:35000]
        prompt = TECHNICAL_PROMPT + "\n\n--- Business Logic ---\n" + business_text + "\n\n--- COBOL Source ---\n" + source
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
            sections = [{"title": "Technical Design (COBOL)", "body": response[:8000]}]

        out_dir = Path(context.output_dir) / "technical"
        out_dir.mkdir(parents=True, exist_ok=True)
        docx_path = out_dir / "04_Technical_Design_COBOL.docx"
        write_docx(sections, docx_path, title="Technical Design (COBOL)")

        tech = {"file_patterns": [], "loops": [], "error_handling": []}
        json_path = out_dir / "technical_analysis.json"
        with open(json_path, "w") as f:
            json.dump(tech, f, indent=2)

        return AgentResult(
            artifacts={
                "04_Technical_Design_COBOL.docx": str(docx_path),
                "technical_analysis.json": str(json_path),
            }
        )
