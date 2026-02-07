"""Agent 8: Validation. Verify business logic parity: rule-by-rule comparison, deviations, risk flags."""
from pathlib import Path

from .base import BaseAgent, AgentContext, AgentResult
from llm import generate, get_model_for_agent, get_temperature
from documents.writer import write_docx
from documents.reader import read_docx_text


VALIDATION_PROMPT = """You are a QA auditor.
Verify business logic parity between the Business Logic Specification and the Scala source.

Produce:
- Rule-by-rule comparison (each business rule -> where/how it appears in Scala)
- Deviations (any mismatch or missing behavior)
- Risk flags (areas that need manual review)

Use section titles on their own line:
- Rule-by-Rule Comparison
- Deviations
- Risk Flags

End with: ---END---"""


def _read_scala_source(scala_dir: str | Path) -> str:
    root = Path(scala_dir)
    if not root.exists():
        return "(No Scala source found)"
    parts = []
    for f in root.rglob("*.scala"):
        parts.append(f"--- {f.relative_to(root)} ---\n{f.read_text(encoding='utf-8', errors='replace')}")
    return "\n\n".join(parts)[:30000]


class ValidationAgent(BaseAgent):
    agent_id = "agent_8"

    def run(self, context: AgentContext) -> AgentResult:
        business_doc = context.artifact_paths.get("03_Business_Logic_Specification.docx")
        scala_dir = context.artifact_paths.get("scala_source_dir")
        business_text = read_docx_text(business_doc) if business_doc else ""
        scala_text = _read_scala_source(scala_dir) if scala_dir else "(Scala source not found)"
        prompt = (
            VALIDATION_PROMPT
            + "\n\n--- Business Logic ---\n"
            + business_text
            + "\n\n--- Scala Source ---\n"
            + scala_text
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
            sections = [{"title": "Parity and Validation Report", "body": response[:8000]}]

        out_dir = Path(context.output_dir) / "validation"
        out_dir.mkdir(parents=True, exist_ok=True)
        docx_path = out_dir / "08_Parity_and_Validation_Report.docx"
        write_docx(sections, docx_path, title="Parity and Validation Report")

        return AgentResult(artifacts={"08_Parity_and_Validation_Report.docx": str(docx_path)})
