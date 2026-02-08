"""Agent 1: COBOL Discovery. Inventory only: programs, paths, copybooks, call linkages, I/O, DB.

Full-knowledge flow: Phase 1 builds a complete inventory of every file (path, PROGRAM-ID, COPY, CALL);
Phase 2 sends that entire inventory to the LLM in one request so it has full knowledge and produces
the discovery DOCX + JSON. No truncation: every file is in the inventory.

Set DISCOVERY_PARSER_ONLY=1 to skip LLM and build overview from parser only (no timeouts).
"""
from pathlib import Path
import json
import logging
import os
import re
from collections import defaultdict

from .base import BaseAgent, AgentContext, AgentResult
from llm import generate, get_model_for_agent, get_temperature
from documents.writer import write_docx
from documents.reader import read_cobol_directory

logger = logging.getLogger(__name__)

# Section titles the LLM must use (order preserved)
DISCOVERY_SECTION_NAMES = [
    "Programs",
    "Batch vs CICS",
    "Copybooks Used",
    "Input/Output Files",
    "Database Tables",
    "Called Programs",
    "Call Linkages",
]

# Phase 2: LLM receives the COMPLETE inventory (all files) and performs discovery.
DISCOVERY_PROMPT_FULL_KNOWLEDGE = """You are a junior COBOL analyst. Your ONLY job is to inventory the system.
Do NOT explain business meaning, guess intent, rewrite logic, or mention Scala.

Below is the COMPLETE inventory of the codebase. Every file is listed with:
- FILE: path
- PROGRAM-ID: (if it is a program)
- COPY: copybook names used in this file
- CALL: program names called from this file
- I/O/DB hints if present (SELECT, FD, EXEC SQL)

You have full knowledge of the entire codebase from this inventory. Using ONLY this inventory, produce the discovery document.

For EVERY section below list concrete data. Use the EXACT file paths and names from the inventory.

1) Programs
   List every program. Each line: PROGRAM-ID (exact file path from inventory).
   Example: - MAINPGM (src/main/MAINPGM.cbl)

2) Batch vs CICS
   One line: Batch, CICS, or Unknown. Infer from file paths (e.g. batch/, online/) or content hints.

3) Copybooks Used
   List every COPY name that appears in the inventory. One per line: - COPYBOOKNAME

4) Input/Output Files
   From I/O hints in the inventory, or "None explicitly mentioned."

5) Database Tables
   From DB hints in the inventory, or "None referenced."

6) Called Programs
   List every program name that appears in any CALL line in the inventory. One per line: - PROGNAME

7) Call Linkages
   For each program that has CALL in the inventory, list: PROGRAM-ID (file path) calls: COMMA-SEPARATED list of called names.
   Example: - MAINPGM (src/main/MAINPGM.cbl) calls: CALCSUBR

Use exactly these section titles on their own line:
- Programs
- Batch vs CICS
- Copybooks Used
- Input/Output Files
- Database Tables
- Called Programs
- Call Linkages

After the last section, add a line: ---END---"""


def _path_stem(p: str) -> str:
    return Path(p).stem.upper()


def _build_full_inventory(cobol_files: dict[str, str]) -> str:
    """Phase 1: Build complete inventory of every file (path, PROGRAM-ID, COPY, CALL, I/O/DB hints).
    No truncation: every file is included. LLM will receive this entire string for full knowledge.
    """
    lines = ["=== COMPLETE CODEBASE INVENTORY (every file) ===\n"]
    for path in sorted(cobol_files.keys()):
        content = cobol_files[path]
        block = [f"FILE: {path}"]
        m = re.search(r"PROGRAM-ID\.\s*(\S+)\.", content, re.IGNORECASE)
        if m:
            block.append(f"  PROGRAM-ID: {m.group(1)}")
        copies = list(dict.fromkeys(re.findall(r"COPY\s+(\S+)\.", content, re.IGNORECASE)))
        if copies:
            block.append("  COPY: " + ", ".join(copies))
        calls = list(dict.fromkeys(re.findall(r"CALL\s+['\"]?(\w+)['\"]?", content, re.IGNORECASE)))
        if calls:
            block.append("  CALL: " + ", ".join(calls))
        if re.search(r"SELECT\s|FD\s|FILE\s+CONTROL", content, re.IGNORECASE):
            block.append("  I/O: (file/SELECT/FD references present)")
        if re.search(r"EXEC\s+SQL|DB2|EXEC\s+CICS", content, re.IGNORECASE):
            block.append("  DB/CICS: (EXEC SQL or CICS references present)")
        lines.append("\n".join(block))
        lines.append("")
    return "\n".join(lines)


def _resolve_copy_to_path(copy_name: str, all_paths: list[str]) -> str | None:
    """Resolve COPY name (e.g. WORKAREA) to a .cpy path in all_paths."""
    name_upper = copy_name.upper()
    for path in all_paths:
        if path.upper().endswith(".CPY") and _path_stem(path) == name_upper:
            return path
    return None


def _resolve_call_to_path(call_name: str, all_paths: list[str]) -> str | None:
    """Resolve CALL name (e.g. CALCSUBR) to a .cbl path in all_paths."""
    name_upper = call_name.upper()
    for path in all_paths:
        if path.upper().endswith(".CBL") and _path_stem(path) == name_upper:
            return path
    return None


def _build_dependency_graph(files: dict[str, str]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Returns (path -> set of paths it references), (path -> set of paths that reference it)."""
    paths = list(files.keys())
    refs: dict[str, set[str]] = defaultdict(set)
    reverse: dict[str, set[str]] = defaultdict(set)
    for path, content in files.items():
        for m in re.finditer(r"COPY\s+(\S+)\.", content, re.IGNORECASE):
            resolved = _resolve_copy_to_path(m.group(1), paths)
            if resolved and resolved in files:
                refs[path].add(resolved)
                reverse[resolved].add(path)
        for m in re.finditer(r"CALL\s+['\"]?(\w+)['\"]?", content, re.IGNORECASE):
            resolved = _resolve_call_to_path(m.group(1), paths)
            if resolved and resolved in files:
                refs[path].add(resolved)
                reverse[resolved].add(path)
    return dict(refs), dict(reverse)


def _dependency_aware_chunks(
    files: dict[str, str],
    max_chunk_chars: int,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Build chunks so related code stays together. Returns (list of chunk file-dicts, path->chunk_index)."""
    refs, reverse = _build_dependency_graph(files)
    paths = list(files.keys())
    cpy_paths = {p for p in paths if p.upper().endswith(".CPY")}
    cbl_paths = {p for p in paths if p.upper().endswith(".CBL")}

    def path_size(p: str) -> int:
        return len(p) + len(files[p]) + 50

    def cluster_size(ps: set[str]) -> int:
        return sum(path_size(p) for p in ps)

    # Roots: programs not called by any other (entry points). If every program is called, use all .cbl as roots.
    called_by_others = {p for p in cbl_paths if reverse.get(p)}
    roots = cbl_paths - called_by_others if (cbl_paths - called_by_others) else cbl_paths
    # Build one cluster per root: root + its refs (copybooks + called programs). Prefer keeping caller+callee together.
    clusters: list[set[str]] = []
    used = set()
    for root in sorted(roots):
        cluster = {root}
        cluster.update(refs.get(root, set()))
        for p in list(cluster):
            if p in refs:
                cluster.update(refs[p])
        cluster = {p for p in cluster if p in files}
        if not cluster or cluster <= used:
            continue
        clusters.append(cluster)
        used |= cluster
    # Any path not in a cluster (e.g. copybooks only) goes into a single "orphan" cluster
    for p in paths:
        if p not in used:
            clusters.append({p})
            used.add(p)

    # Order within a cluster: copybooks first, then programs (callees before callers).
    def order_paths(ps: set[str]) -> list[str]:
        return sorted(
            ps,
            key=lambda p: (
                0 if p in cpy_paths else 1,
                -len(reverse.get(p, set())),
                p,
            ),
        )

    # Pack clusters into chunks. If a cluster fits, add it whole; else split by dependency order (no file split).
    chunks: list[dict[str, str]] = []
    path_to_chunk: dict[str, int] = {}
    current: dict[str, str] = {}
    current_size = 0
    for cluster in clusters:
        ordered = order_paths(cluster)
        if cluster_size(cluster) <= max_chunk_chars:
            if current_size + cluster_size(cluster) > max_chunk_chars and current:
                chunks.append(current)
                for p in current:
                    path_to_chunk[p] = len(chunks) - 1
                current = {}
                current_size = 0
            for p in ordered:
                current[p] = files[p]
                current_size += path_size(p)
        else:
            # Cluster too big: flush current, then add this cluster file-by-file in dependency order (new chunks as needed).
            if current:
                chunks.append(current)
                for p in current:
                    path_to_chunk[p] = len(chunks) - 1
                current = {}
                current_size = 0
            for p in ordered:
                if current_size + path_size(p) > max_chunk_chars and current:
                    chunks.append(current)
                    for q in current:
                        path_to_chunk[q] = len(chunks) - 1
                    current = {}
                    current_size = 0
                current[p] = files[p]
                current_size += path_size(p)
    if current:
        chunks.append(current)
        for p in current:
            path_to_chunk[p] = len(chunks) - 1
    return chunks, path_to_chunk


def _cross_chunk_context(
    chunk_index: int,
    chunk_paths: set[str],
    path_to_chunk: dict[str, int],
    reverse: dict[str, set[str]],
    refs: dict[str, set[str]],
) -> str:
    """Describe how this chunk relates to others (callers in other chunks, callees in other chunks)."""
    lines = []
    # Programs in other chunks that call programs in this chunk
    callers_of_this = set()
    for p in chunk_paths:
        for caller in reverse.get(p, set()):
            if path_to_chunk.get(caller) is not None and path_to_chunk[caller] != chunk_index:
                callers_of_this.add(caller)
    if callers_of_this:
        lines.append("Programs in other chunks that call programs in this chunk: " + ", ".join(sorted(callers_of_this)))
    # Programs in this chunk that are called by programs in other chunks (redundant but clear)
    # Programs in this chunk that call programs in other chunks
    callees_elsewhere = set()
    for p in chunk_paths:
        for callee in refs.get(p, set()):
            if path_to_chunk.get(callee) is not None and path_to_chunk[callee] != chunk_index:
                callees_elsewhere.add(callee)
    if callees_elsewhere:
        lines.append("Programs/copybooks in this chunk call or use (in other chunks): " + ", ".join(sorted(callees_elsewhere)))
    if not lines:
        return ""
    return "Context (cross-chunk relationships): " + " | ".join(lines) + "\n\n"


def _parse_cobol_structure(files: dict[str, str]) -> dict:
    """Lightweight parse: program ids, copy names, call names. Uses full content only."""
    programs = []
    copybooks = set()
    calls = set()
    for path, content in files.items():
        if path.endswith(".cbl"):
            m = re.search(r"PROGRAM-ID\.\s*(\S+)\.", content, re.IGNORECASE)
            if m:
                programs.append({"name": m.group(1), "file": path})
        for m in re.finditer(r"COPY\s+(\S+)\.", content, re.IGNORECASE):
            copybooks.add(m.group(1))
        for m in re.finditer(r"CALL\s+['\"]?(\w+)['\"]?", content, re.IGNORECASE):
            calls.add(m.group(1))
    return {
        "programs": programs,
        "copybooks": sorted(copybooks),
        "called_programs": sorted(calls),
    }


def _format_chunk_content(chunk_files: dict[str, str], context_prefix: str = "") -> str:
    """Format a chunk's files as a single string for the prompt. Full content per file. Optional context_prefix for cross-chunk meaning."""
    body = "\n\n".join(
        f"--- FILE: {path} ---\n{content}"
        for path, content in chunk_files.items()
    )
    if context_prefix:
        return context_prefix + body
    return body


def _parse_response_into_sections(response: str) -> dict[str, str]:
    """Parse LLM response into section title -> body. Uses DISCOVERY_SECTION_NAMES."""
    sections: dict[str, str] = {}
    current_title: str | None = None
    current_body: list[str] = []
    for line in response.split("\n"):
        if line.strip() == "---END---":
            break
        if line.startswith("- ") and not line.startswith("-  "):
            if current_title is not None:
                body = "\n".join(current_body).strip()
                if body and current_title in DISCOVERY_SECTION_NAMES:
                    sections[current_title] = body
            raw_title = line.strip().lstrip("- ")
            current_title = raw_title if raw_title in DISCOVERY_SECTION_NAMES else None
            current_body = []
        else:
            current_body.append(line)
    if current_title is not None:
        body = "\n".join(current_body).strip()
        if body and current_title in DISCOVERY_SECTION_NAMES:
            sections[current_title] = body
    return sections


def _structure_to_section_bodies(structure: dict) -> dict[str, str]:
    """Build section bodies from structure (programs, copybooks, called_programs). Used only in parser-only mode."""
    programs_body = "\n".join(
        f"- {p['name']} ({p['file']})" for p in structure["programs"]
    ) if structure["programs"] else "None identified."
    copybooks_body = "\n".join(f"- {c}" for c in structure["copybooks"]) or "None."
    calls_body = "\n".join(f"- {c}" for c in structure["called_programs"]) or "None."
    return {
        "Programs": programs_body,
        "Copybooks Used": copybooks_body,
        "Called Programs": calls_body,
    }


def _parse_llm_merged_to_structure(merged: dict[str, str]) -> dict:
    """Extract structured data from LLM merged sections so discovery.json matches the DOCX (same LLM source)."""
    programs: list[dict] = []
    copybooks: list[str] = []
    called: list[str] = []
    call_linkages: list[dict] = []
    # Programs: e.g. "- PROGNAME (path/to/file.cbl)"
    for line in (merged.get("Programs") or "").split("\n"):
        line = line.strip()
        if not line or line.lower().startswith("none"):
            continue
        line = line.lstrip("- ").strip()
        m = re.match(r"^(\w+)\s*\((.+)\)\s*$", line)
        if m:
            programs.append({"name": m.group(1), "file": m.group(2).strip()})
        elif re.match(r"^\w+\s+", line):
            parts = line.split(None, 1)
            programs.append({"name": parts[0], "file": parts[1].lstrip("- ()").strip() if len(parts) > 1 else ""})
        elif line:
            programs.append({"name": line, "file": ""})
    # Copybooks Used
    for line in (merged.get("Copybooks Used") or "").split("\n"):
        line = line.strip().lstrip("- ").strip()
        if line and not line.lower().startswith("none"):
            copybooks.append(line.split()[0] if line.split() else line)
    copybooks = sorted(dict.fromkeys(copybooks))
    # Called Programs
    for line in (merged.get("Called Programs") or "").split("\n"):
        line = line.strip().lstrip("- ").strip()
        if line and not line.lower().startswith("none"):
            called.append(line.split()[0] if line.split() else line)
    called = sorted(dict.fromkeys(called))
    # Call Linkages: e.g. "- MAINPGM (path.cbl) calls: CALCSUBR" or "PROG (path) calls: A, B"
    for line in (merged.get("Call Linkages") or "").split("\n"):
        line = line.strip().lstrip("- ").strip()
        if not line or "calls:" not in line.lower():
            continue
        before, _, after = line.partition("calls:")
        m = re.match(r"^(\w+)\s*\((.+)\)\s*$", before.strip())
        if m:
            caller_name, caller_file = m.group(1), m.group(2).strip()
            callees = [s.strip() for s in after.split(",") if s.strip()]
            call_linkages.append({"caller": caller_name, "file": caller_file, "calls": callees})
    batch = (merged.get("Batch vs CICS") or "").strip() or "Unknown"
    return {
        "programs": programs,
        "copybooks": copybooks,
        "called_programs": called,
        "call_linkages": call_linkages,
        "batch_or_cics": batch,
    }


def _build_call_linkages_from_refs(
    refs: dict[str, set[str]], programs: list[dict]
) -> list[dict]:
    """Build call_linkages from dependency graph and program list (file -> program name)."""
    path_to_name = {p["file"]: p["name"] for p in programs}
    linkages = []
    for p in programs:
        path = p["file"]
        called_paths = refs.get(path, set())
        called_names = sorted(
            path_to_name.get(cp, Path(cp).stem) for cp in called_paths if cp.endswith(".cbl") or cp.upper().endswith(".CBL")
        )
        if called_names:
            linkages.append({"caller": p["name"], "file": path, "calls": called_names})
    return linkages


def _build_overview_from_parser(
    structure: dict, file_count: int, call_linkages: list[dict] | None = None
) -> list[dict]:
    """Build DOCX sections from parser output only (no LLM). Use when DISCOVERY_PARSER_ONLY=1."""
    bodies = _structure_to_section_bodies(structure)
    linkages_body = ""
    if call_linkages:
        lines = [f"- {x['caller']} ({x['file']}) calls: {', '.join(x['calls'])}" for x in call_linkages]
        linkages_body = "\n".join(lines)
    else:
        linkages_body = "None (parser-only)."
    return [
        {"title": "Programs", "body": bodies["Programs"]},
        {"title": "Batch vs CICS", "body": "Unknown (parser-only mode)."},
        {"title": "Copybooks Used", "body": bodies["Copybooks Used"]},
        {"title": "Input/Output Files", "body": "None explicitly mentioned (parser-only)."},
        {"title": "Database Tables", "body": "None referenced (parser-only)."},
        {"title": "Called Programs", "body": bodies["Called Programs"]},
        {"title": "Call Linkages", "body": linkages_body},
    ]


def _merge_section_bodies(chunk_sections: list[dict[str, str]]) -> dict[str, str]:
    """Merge section bodies from multiple chunks. Deduplicates list-like lines where possible."""
    merged: dict[str, str] = {}
    for name in DISCOVERY_SECTION_NAMES:
        if name == "Batch vs CICS":
            # Take first non-Unknown value across chunks
            value = ""
            for chunk_sec in chunk_sections:
                body = chunk_sec.get(name, "").strip()
                if body and body.lower() != "unknown":
                    value = body
                    break
            if not value:
                value = next(
                    (chunk_sec.get(name, "").strip() for chunk_sec in chunk_sections if chunk_sec.get(name, "").strip()),
                    "Unknown",
                )
            merged[name] = value
            continue
        parts = []
        seen_lines: set[str] = set()
        for chunk_sec in chunk_sections:
            body = chunk_sec.get(name, "").strip()
            if not body:
                continue
            for line in body.split("\n"):
                line_stripped = line.strip()
                if not line_stripped:
                    parts.append("")
                    continue
                key = line_stripped.lower()
                if key in seen_lines:
                    continue
                seen_lines.add(key)
                parts.append(line)
            if parts and parts[-1] != "":
                parts.append("")
        merged[name] = "\n".join(parts).strip() if parts else ""
    return merged


class DiscoveryAgent(BaseAgent):
    agent_id = "agent_1"

    def run(self, context: AgentContext) -> AgentResult:
        cobol_files = read_cobol_directory(context.cobol_dir)
        if not cobol_files:
            logger.warning("No COBOL files found under %s", context.cobol_dir)

        parser_only = os.environ.get("DISCOVERY_PARSER_ONLY", "").strip().lower() in ("1", "true", "yes")
        if parser_only:
            logger.info("Discovery: parser-only mode (DISCOVERY_PARSER_ONLY=1), skipping LLM")
            structure = _parse_cobol_structure(cobol_files)
            refs, _ = _build_dependency_graph(cobol_files)
            call_linkages = _build_call_linkages_from_refs(refs, structure["programs"])
            sections_for_docx = _build_overview_from_parser(
                structure, len(cobol_files), call_linkages=call_linkages
            )
            out_dir = Path(context.output_dir) / "discovery"
            out_dir.mkdir(parents=True, exist_ok=True)
            docx_path = out_dir / "01_COBOL_Codebase_Overview.docx"
            write_docx(sections_for_docx, docx_path, title="COBOL Codebase Overview")
            discovery = {
                "programs": structure["programs"],
                "copybooks": structure["copybooks"],
                "called_programs": structure["called_programs"],
                "call_linkages": call_linkages,
                "batch_or_cics": "Unknown",
                "file_count": len(cobol_files),
                "chunk_count": 0,
                "parser_only": True,
            }
            json_path = out_dir / "discovery.json"
            with open(json_path, "w") as f:
                json.dump(discovery, f, indent=2)
            return AgentResult(
                artifacts={
                    "01_COBOL_Codebase_Overview.docx": str(docx_path),
                    "discovery.json": str(json_path),
                }
            )

        # Phase 1: Full inventory of every file (no truncation)
        full_inventory = _build_full_inventory(cobol_files)
        logger.info(
            "Discovery: full-knowledge inventory built, %d files, %d chars (all files included)",
            len(cobol_files),
            len(full_inventory),
        )

        # Phase 2: Single LLM request with complete inventory
        model = get_model_for_agent(self.agent_id)
        temp = get_temperature(self.agent_id)
        prompt = DISCOVERY_PROMPT_FULL_KNOWLEDGE + "\n\n" + full_inventory
        response = generate(prompt, model=model, temperature=temp)
        merged = _parse_response_into_sections(response)

        # DOCX and JSON both from LLM only
        sections_for_docx = [
            {"title": name, "body": merged.get(name, "") or "Not provided by model."}
            for name in DISCOVERY_SECTION_NAMES
        ]
        llm_structure = _parse_llm_merged_to_structure(merged)

        out_dir = Path(context.output_dir) / "discovery"
        out_dir.mkdir(parents=True, exist_ok=True)
        docx_path = out_dir / "01_COBOL_Codebase_Overview.docx"
        write_docx(sections_for_docx, docx_path, title="COBOL Codebase Overview")

        discovery = {
            "programs": llm_structure["programs"],
            "copybooks": llm_structure["copybooks"],
            "called_programs": llm_structure["called_programs"],
            "call_linkages": llm_structure["call_linkages"],
            "batch_or_cics": llm_structure["batch_or_cics"],
            "file_count": len(cobol_files),
            "chunk_count": 0,
        }
        json_path = out_dir / "discovery.json"
        with open(json_path, "w") as f:
            json.dump(discovery, f, indent=2)

        return AgentResult(
            artifacts={
                "01_COBOL_Codebase_Overview.docx": str(docx_path),
                "discovery.json": str(json_path),
            }
        )
