"""Agent 2: Dependency Graph. Call hierarchy, shared components, data flow, migration order.
Populates dependency_graph.json from discovery.json + COPY scan. DOCX is detailed for downstream agents."""
import json
import re
from pathlib import Path
from collections import defaultdict

from .base import BaseAgent, AgentContext, AgentResult
from llm import generate, get_model_for_agent, get_temperature
from documents.writer import write_docx
from documents.reader import read_docx_text, read_cobol_directory


DEPENDENCY_PROMPT = """You are a system architect. Document at a MINUTE level of detail so downstream agents understand exactly who calls whom and how data flows.

Do NOT explain business rules or algorithms. Focus ONLY on structure and data flow.

Given the overview and source below, produce a highly detailed document:

1. Call Hierarchy
   - List EVERY program. For each program state: (a) which programs it CALLs (by PROGRAM-ID), (b) which programs call it.
   - Use explicit lines like "MAINPGM calls: CALCSUBR" and "CALCSUBR is called by: MAINPGM".

2. Shared Components
   - List EVERY copybook. For each copybook list EVERY program that uses it (COPY statement). If a copybook is used by more than one program, say "SHARED" and list all programs.

3. Data Flow Summary
   - Describe step-by-step how data moves: which program passes what to which (e.g. via CALL USING, copybook fields). Name programs and data areas. Be specific enough that a downstream agent can trace each flow.

4. Migration Order Recommendation
   - List programs in the order they should be migrated (one per line or numbered). For each program give a one-line justification (e.g. "Leaf program, no callers" or "Depends only on ERRPROC which is already migrated").

Format with exactly these section titles on their own line:
- Call Hierarchy
- Shared Components
- Data Flow Summary
- Migration Order Recommendation

After the last section add: ---END---"""


def _load_discovery(context: AgentContext) -> dict:
    """Load discovery.json from artifact path or discovery subdir."""
    path = context.artifact_paths.get("discovery.json")
    if path and Path(path).exists():
        with open(path) as f:
            return json.load(f)
    fallback = Path(context.output_dir) / "01_discovery" / "discovery.json"
    if not fallback.exists():
        fallback = Path(context.output_dir) / "discovery" / "discovery.json"
    if fallback.exists():
        with open(fallback) as f:
            return json.load(f)
    return {}


def _build_call_hierarchy(discovery: dict) -> list[dict]:
    """From call_linkages build list of {caller, callee, caller_file, callee_file}."""
    programs_by_name = {p["name"]: p["file"] for p in discovery.get("programs", [])}
    out = []
    for link in discovery.get("call_linkages", []):
        caller = link.get("caller", "")
        caller_file = link.get("file", "")
        for callee in link.get("calls", []):
            callee_file = programs_by_name.get(callee, "")
            out.append({
                "caller": caller,
                "callee": callee,
                "caller_file": caller_file,
                "callee_file": callee_file,
            })
    return out


def _build_shared_copybooks(cobol_files: dict[str, str], program_names: set[str]) -> list[dict]:
    """For each .cbl file get PROGRAM-ID and COPY names; then list copybooks used by >1 program."""
    path_to_program = {}
    program_copybooks = defaultdict(set)
    for path, content in cobol_files.items():
        if not path.upper().endswith(".CBL"):
            continue
        m = re.search(r"PROGRAM-ID\.\s*(\S+)\.", content, re.IGNORECASE)
        prog = m.group(1) if m else Path(path).stem
        path_to_program[path] = prog
        program_names.add(prog)
        for copy in re.findall(r"COPY\s+(\S+)\.", content, re.IGNORECASE):
            program_copybooks[prog].add(copy)
    copybook_to_programs = defaultdict(list)
    for prog, copies in program_copybooks.items():
        for cpy in copies:
            copybook_to_programs[cpy].append(prog)
    shared = []
    for copybook, progs in sorted(copybook_to_programs.items()):
        progs = sorted(set(progs))
        shared.append({"copybook": copybook, "used_by": progs, "shared": len(progs) > 1})
    return shared


def _build_migration_order(discovery: dict) -> list[dict]:
    """Topological order: programs that are only callees (leaves) first, then callers."""
    call_linkages = discovery.get("call_linkages", [])
    all_programs = {p["name"] for p in discovery.get("programs", [])}
    callers = set()
    callees = set()
    for link in call_linkages:
        callers.add(link["caller"])
        for c in link.get("calls", []):
            callees.add(c)
    # Leaves = programs that are never callers (or have no calls)
    remaining = set(all_programs)
    order = []
    step = 0
    while remaining:
        # Next batch: programs that either don't call anyone, or whose callees are already in order
        ordered_names = {x["program"] for x in order}
        next_batch = []
        for p in remaining:
            link = next((l for l in call_linkages if l["caller"] == p), None)
            called = set(link["calls"]) if link else set()
            if not called or called <= ordered_names:
                next_batch.append(p)
        if not next_batch:
            next_batch = list(remaining)
        for p in sorted(next_batch):
            step += 1
            order.append({
                "order": step,
                "program": p,
                "justification": "Leaf or dependencies already migrated" if step <= len(next_batch) else "After dependencies",
            })
            remaining.discard(p)
    return order


class DependencyGraphAgent(BaseAgent):
    agent_id = "agent_2"

    def run(self, context: AgentContext) -> AgentResult:
        discovery = _load_discovery(context)
        overview_path = context.artifact_paths.get("01_COBOL_Codebase_Overview.docx")
        overview_text = read_docx_text(overview_path) if overview_path else ""
        cobol_files = read_cobol_directory(context.cobol_dir)
        program_names = {p["name"] for p in discovery.get("programs", [])}

        # Build JSON from discovery + COPY scan (always populated)
        call_hierarchy = _build_call_hierarchy(discovery)
        shared_copybooks = _build_shared_copybooks(cobol_files, program_names)
        migration_order = _build_migration_order(discovery)
        dependency = {
            "call_hierarchy": call_hierarchy,
            "shared_copybooks": shared_copybooks,
            "migration_order": migration_order,
            "data_flow_summary": "See DOCX for narrative; structure derived from call hierarchy and shared copybooks.",
        }

        combined = "\n\n".join(
            f"--- {p} ---\n{c[:4000]}" for p, c in cobol_files.items()
        )
        prompt = (
            DEPENDENCY_PROMPT
            + "\n\n--- Overview ---\n"
            + overview_text
            + "\n\n--- Call linkage data (use this for accuracy) ---\n"
            + json.dumps({"call_hierarchy": call_hierarchy, "shared_copybooks": [s for s in shared_copybooks if s["shared"]], "migration_order": migration_order}, indent=2)[:8000]
            + "\n\n--- Source ---\n"
            + combined[:25000]
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
            sections = [{"title": "Dependency and Call Graph", "body": response[:12000]}]

        out_dir = Path(context.output_dir) / "02_dependency"
        out_dir.mkdir(parents=True, exist_ok=True)
        docx_path = out_dir / "02_Dependency_and_Call_Graph.docx"
        write_docx(sections, docx_path, title="Dependency and Call Graph")

        json_path = out_dir / "dependency_graph.json"
        with open(json_path, "w") as f:
            json.dump(dependency, f, indent=2)

        return AgentResult(
            artifacts={
                "02_Dependency_and_Call_Graph.docx": str(docx_path),
                "dependency_graph.json": str(json_path),
            }
        )
