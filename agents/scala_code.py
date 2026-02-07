"""Agent 7: Scala Code Generation. Write Scala only from pseudocode and design. No COBOL access."""
from pathlib import Path
import re

from .base import BaseAgent, AgentContext, AgentResult
from llm import generate, get_model_for_agent, get_temperature
from documents.reader import read_docx_text


SCALA_CODE_PROMPT = """You are a Scala developer.
Write Scala code ONLY, strictly following the design and pseudocode below.
You MUST NOT: access COBOL, change logic, or add creativity.

Output only valid Scala source code. For multiple files, use this format exactly:

---FILE: path/to/File.scala---
// Scala code here
---END FILE---

Repeat for each file. No other commentary."""


class ScalaCodeAgent(BaseAgent):
    agent_id = "agent_7"

    def run(self, context: AgentContext) -> AgentResult:
        pseudo_doc = context.artifact_paths.get("05_Pseudocode_Language_Neutral.docx")
        design_doc = context.artifact_paths.get("06_Scala_Design_Specification.docx")
        pseudo_text = read_docx_text(pseudo_doc) if pseudo_doc else ""
        design_text = read_docx_text(design_doc) if design_doc else ""
        prompt = (
            SCALA_CODE_PROMPT
            + "\n\n--- Pseudocode ---\n"
            + pseudo_text
            + "\n\n--- Scala Design ---\n"
            + design_text
        )
        model = get_model_for_agent(self.agent_id)
        response = generate(prompt, model=model, temperature=get_temperature(self.agent_id))

        out_dir = Path(context.output_dir) / "scala_code"
        out_dir.mkdir(parents=True, exist_ok=True)
        scala_dir = out_dir / "src" / "main" / "scala"
        scala_dir.mkdir(parents=True, exist_ok=True)

        pattern = re.compile(r"---FILE:\s*([^\n-]+)---\s*(.*?)---END FILE---", re.DOTALL)
        matches = pattern.findall(response)
        if not matches:
            single = re.sub(r"^---FILE:.*?---\s*", "", response)
            single = re.sub(r"\s*---END FILE---.*", "", single, flags=re.DOTALL)
            if single.strip():
                fpath = scala_dir / "Main.scala"
                fpath.write_text(single.strip(), encoding="utf-8")
                return AgentResult(
                    artifacts={"scala_source_dir": str(out_dir)}
                )
            fpath = scala_dir / "Main.scala"
            fpath.write_text("// Generated placeholder\nobject Main { def main(args: Array[String]): Unit = () }", encoding="utf-8")
            return AgentResult(artifacts={"scala_source_dir": str(out_dir)})

        for rel_path, code in matches:
            rel_path = rel_path.strip()
            if not rel_path.endswith(".scala"):
                rel_path = rel_path.rstrip("/") + ".scala"
            full = scala_dir / rel_path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(code.strip(), encoding="utf-8")

        return AgentResult(artifacts={"scala_source_dir": str(out_dir)})
