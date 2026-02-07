"""Agent 2: Dependency Graph. Call hierarchy, shared components, data flow, migration order."""
from pathlib import Path
import json

from .base import BaseAgent, AgentContext, AgentResult
from llm import generate, get_model_for_agent, get_temperature
from documents.writer import write_docx
from documents.reader import read_docx_text, read_cobol_directory


DEPENDENCY_PROMPT = """You are a system architect mapping relationships.
Do NOT explain business rules or algorithms.

Given the COBOL codebase overview and the source below, produce:
1. Call hierarchy (which programs call which)
2. Shared components (copybooks used by multiple programs)
3. Data flow summary (how data passes between programs)
4. Migration order recommendation (which programs to migrate first, with brief justification)

Format your response with exactly these section titles on their own line:
- Call Hierarchy
- Shared Components
- Data Flow Summary
- Migration Order Recommendation

After the last section add: ---END---"""


class DependencyGraphAgent(BaseAgent):
    agent_id = "agent_2"

    def run(self, context: AgentContext) -> AgentResult:
        overview_path = context.artifact_paths.get("01_COBOL_Codebase_Overview.docx")
        overview_text = read_docx_text(overview_path) if overview_path else ""
        cobol_files = read_cobol_directory(context.cobol_dir)
        combined = "\n\n".join(
            f"--- {p} ---\n{c[:4000]}" for p, c in cobol_files.items()
        )
        prompt = DEPENDENCY_PROMPT + "\n\n--- Overview ---\n" + overview_text + "\n\n--- Source ---\n" + combined[:25000]
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
            sections = [{"title": "Dependency and Call Graph", "body": response[:8000]}]

        out_dir = Path(context.output_dir) / "dependency"
        out_dir.mkdir(parents=True, exist_ok=True)
        docx_path = out_dir / "02_Dependency_and_Call_Graph.docx"
        write_docx(sections, docx_path, title="Dependency and Call Graph")

        dependency = {
            "call_hierarchy": [],
            "shared_copybooks": [],
            "migration_order": [],
        }
        json_path = out_dir / "dependency_graph.json"
        with open(json_path, "w") as f:
            json.dump(dependency, f, indent=2)

        return AgentResult(
            artifacts={
                "02_Dependency_and_Call_Graph.docx": str(docx_path),
                "dependency_graph.json": str(json_path),
            }
        )
