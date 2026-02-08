"""Agent 2: Dependency Graph. Call hierarchy, shared components, data flow, migration order.
Populates dependency_graph.json from discovery.json + COPY scan. DOCX is generated FROM the same
JSON data so it always matches and is complete (no reliance on LLM for structure)."""
import json
import re
from pathlib import Path
from collections import defaultdict

from .base import BaseAgent, AgentContext, AgentResult
from documents.writer import write_docx
from documents.reader import read_cobol_directory


def _docx_call_hierarchy(call_hierarchy: list[dict]) -> str:
    """Build Call Hierarchy section from call_hierarchy JSON. Clear narrative + data matching JSON."""
    intro = (
        "This section lists every program and its call relationships, derived from CALL statements in the source. "
        "The content below is the same as dependency_graph.json \"call_hierarchy\"; downstream agents can rely on either.\n\n"
    )
    if not call_hierarchy:
        return intro + "No call relationships found."
    by_caller = defaultdict(list)
    for e in call_hierarchy:
        by_caller[e["caller"]].append((e["callee"], e.get("caller_file", ""), e.get("callee_file", "")))
    called_by = defaultdict(list)
    for e in call_hierarchy:
        called_by[e["callee"]].append(e["caller"])
    lines = ["Callers (who calls whom):", ""]
    for caller in sorted(by_caller.keys()):
        callees = by_caller[caller]
        caller_file = callees[0][1] if callees else ""
        callee_names = sorted(set(c[0] for c in callees))
        lines.append(f"  {caller} ({caller_file}) calls: {', '.join(callee_names)}")
    lines.append("")
    lines.append("Called-by (reverse lookup):")
    for callee in sorted(called_by.keys()):
        callers = sorted(called_by[callee])
        lines.append(f"  {callee} is called by: {', '.join(callers)}")
    return intro + "\n".join(lines)


def _docx_shared_components(shared_copybooks: list[dict]) -> str:
    """Build Shared Components section from shared_copybooks JSON. Narrative matches JSON."""
    intro = (
        "Copybooks (COPY statements) define shared data structures. Below, shared copybooks are listed first, "
        "then the full list. This content matches dependency_graph.json \"shared_copybooks\".\n\n"
    )
    if not shared_copybooks:
        return intro + "No copybooks found."
    shared_only = [s for s in shared_copybooks if s.get("shared")]
    lines = ["Shared copybooks (used by more than one program):", ""]
    for s in shared_only:
        lines.append(f"  {s['copybook']}: used by {', '.join(s['used_by'])}")
    lines.append("")
    lines.append("All copybooks and programs that use them:")
    for s in shared_copybooks:
        marker = " (SHARED)" if s.get("shared") else ""
        lines.append(f"  {s['copybook']}{marker}: {', '.join(s['used_by'])}")
    return intro + "\n".join(lines)


def _docx_migration_order(migration_order: list[dict]) -> str:
    """Build Migration Order section from migration_order JSON. Narrative matches JSON."""
    intro = (
        "Programs are listed in recommended migration order (callees before callers). "
        "This list is the same as dependency_graph.json \"migration_order\".\n\n"
    )
    if not migration_order:
        return intro + "No migration order computed."
    lines = [f"  {m['order']}. {m['program']} — {m.get('justification', '')}" for m in migration_order]
    return intro + "\n".join(lines)


def _docx_data_flow_summary(call_hierarchy: list[dict], shared_copybooks: list[dict]) -> str:
    """Narrative derived from JSON so DOCX and JSON stay in sync."""
    shared_count = sum(1 for s in shared_copybooks if s.get("shared"))
    call_count = len(call_hierarchy)
    return (
        "Data flow in this codebase is determined by the call hierarchy and shared copybooks. "
        "Parameters are passed via CALL USING; shared copybooks define common record layouts and fields.\n\n"
        f"This document reflects {call_count} caller-to-callee relationships and {shared_count} copybooks shared across multiple programs. "
        "The Call Hierarchy and Shared Components sections above are the single source of truth and match dependency_graph.json. "
        "The Migration Order section below lists programs so that each program is migrated only after the programs it calls."
    )


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
            "data_flow_summary": "Data flows follow call hierarchy and shared copybooks; see DOCX for narrative.",
        }

        # Build DOCX from same JSON data so DOCX and JSON always match and are complete
        sections = [
            {"title": "Call Hierarchy", "body": _docx_call_hierarchy(call_hierarchy)},
            {"title": "Shared Components", "body": _docx_shared_components(shared_copybooks)},
            {"title": "Data Flow Summary", "body": _docx_data_flow_summary(call_hierarchy, shared_copybooks)},
            {"title": "Migration Order Recommendation", "body": _docx_migration_order(migration_order)},
        ]

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
