"""
Agent 1: COBOL Discovery.

Design (from scratch):
- Parser is the single source of truth for: programs (name + path), copybooks, called programs, call linkages.
  These are extracted from every file with regex; no LLM for lists so nothing is "missed".
- Optional LLM step only for: Batch vs CICS, Input/Output Files, Database Tables (classification/narrative).
- DOCX and discovery.json are built from the same parser output so they always match. Call linkages
  come from the dependency graph (who CALLs whom) and are always populated when present in source.

Set DISCOVERY_PARSER_ONLY=1 to skip the optional LLM (Batch/CICS, I/O, DB default to Unknown/None).
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


# ---- Parser: single source of truth for structure ----

def _parse_programs_and_refs(files: dict[str, str]) -> tuple[list[dict], set[str], set[str], dict[str, set[str]]]:
    """
    One pass over all files. Returns:
    - programs: [{"name": str, "file": str}, ...]
    - copybooks: set of copybook names
    - called_programs: set of program names in CALL statements
    - refs: path -> set of paths referenced (COPY or CALL resolved to path)
    """
    paths = list(files.keys())
    programs = []
    copybooks = set()
    called_programs = set()
    refs = defaultdict(set)

    def stem(p):
        return Path(p).stem.upper()

    def resolve_copy(name):
        for p in paths:
            if p.upper().endswith(".CPY") and stem(p) == name.upper():
                return p
        return None

    def resolve_call(name):
        for p in paths:
            if p.upper().endswith(".CBL") and stem(p) == name.upper():
                return p
        return None

    for path, content in files.items():
        if path.upper().endswith(".CBL"):
            m = re.search(r"PROGRAM-ID\.\s*(\S+)\.", content, re.IGNORECASE)
            if m:
                programs.append({"name": m.group(1), "file": path})

        for m in re.finditer(r"COPY\s+(\S+)\.", content, re.IGNORECASE):
            name = m.group(1)
            copybooks.add(name)
            r = resolve_copy(name)
            if r:
                refs[path].add(r)

        for m in re.finditer(r"CALL\s+['\"]?(\w+)['\"]?", content, re.IGNORECASE):
            name = m.group(1)
            called_programs.add(name)
            r = resolve_call(name)
            if r:
                refs[path].add(r)

    return programs, copybooks, called_programs, dict(refs)


def _build_call_linkages(programs: list[dict], refs: dict[str, set[str]]) -> list[dict]:
    """From refs (path -> set of referenced paths), build call_linkages: caller program calls which programs."""
    path_to_name = {p["file"]: p["name"] for p in programs}
    linkages = []
    for p in programs:
        path = p["file"]
        called_paths = refs.get(path, set())
        called_names = sorted(
            path_to_name.get(cp, Path(cp).stem) for cp in called_paths
            if cp.upper().endswith(".CBL")
        )
        if called_names:
            linkages.append({"caller": p["name"], "file": path, "calls": called_names})
    return linkages


def _section_programs(programs: list[dict]) -> str:
    return "\n".join(f"- {p['name']} ({p['file']})" for p in programs) if programs else "None."


def _section_copybooks(copybooks: set) -> str:
    return "\n".join(f"- {c}" for c in sorted(copybooks)) if copybooks else "None."


def _section_called(called_programs: set) -> str:
    return "\n".join(f"- {c}" for c in sorted(called_programs)) if called_programs else "None."


def _section_call_linkages(linkages: list[dict]) -> str:
    if not linkages:
        return "None."
    return "\n".join(f"- {x['caller']} ({x['file']}) calls: {', '.join(x['calls'])}" for x in linkages)


# ---- Optional LLM: Batch/CICS, I/O, DB only ----

def _invoke_llm_for_classification(full_inventory: str, model: str, temp: float) -> dict:
    """Ask LLM only for Batch vs CICS, I/O files, DB tables. Returns dict with those three keys."""
    prompt = """You are a COBOL analyst. Below is the complete inventory of a codebase (every file with PROGRAM-ID, COPY, CALL).

Answer ONLY these three items in this exact format (one line each):

BATCH_OR_CICS: Batch | CICS | Unknown
IO_FILES: brief answer or "None explicitly mentioned"
DB_TABLES: brief answer or "None referenced"

Inventory:
"""
    prompt += full_inventory[:40000]  # cap so prompt is not huge
    try:
        response = generate(prompt, model=model, temperature=temp)
        out = {"batch_or_cics": "Unknown", "io_files": "None explicitly mentioned.", "db_tables": "None referenced."}
        for line in response.split("\n"):
            line = line.strip()
            if line.upper().startswith("BATCH_OR_CICS:"):
                out["batch_or_cics"] = line.split(":", 1)[1].strip() or "Unknown"
            elif line.upper().startswith("IO_FILES:"):
                out["io_files"] = line.split(":", 1)[1].strip() or "None explicitly mentioned."
            elif line.upper().startswith("DB_TABLES:"):
                out["db_tables"] = line.split(":", 1)[1].strip() or "None referenced."
        return out
    except Exception as e:
        logger.warning("Discovery LLM classification failed: %s", e)
        return {"batch_or_cics": "Unknown", "io_files": "None explicitly mentioned.", "db_tables": "None referenced."}


def _build_inventory_text(files: dict[str, str]) -> str:
    """Compact inventory for optional LLM: one block per file."""
    lines = []
    for path in sorted(files.keys()):
        content = files[path]
        block = [f"FILE: {path}"]
        m = re.search(r"PROGRAM-ID\.\s*(\S+)\.", content, re.IGNORECASE)
        if m:
            block.append(f"  PROGRAM-ID: {m.group(1)}")
        copies = re.findall(r"COPY\s+(\S+)\.", content, re.IGNORECASE)
        if copies:
            block.append("  COPY: " + ", ".join(copies))
        calls = re.findall(r"CALL\s+['\"]?(\w+)['\"]?", content, re.IGNORECASE)
        if calls:
            block.append("  CALL: " + ", ".join(calls))
        lines.append("\n".join(block))
        lines.append("")
    return "\n".join(lines)


# ---- Agent ----

class DiscoveryAgent(BaseAgent):
    agent_id = "agent_1"

    def run(self, context: AgentContext) -> AgentResult:
        cobol_files = read_cobol_directory(context.cobol_dir)
        if not cobol_files:
            logger.warning("No COBOL files found under %s", context.cobol_dir)
            cobol_files = {}

        # Parser: single source of truth (all files, no truncation)
        programs, copybooks, called_programs, refs = _parse_programs_and_refs(cobol_files)
        call_linkages = _build_call_linkages(programs, refs)

        # Optional LLM for Batch/CICS, I/O, DB only
        parser_only = os.environ.get("DISCOVERY_PARSER_ONLY", "").strip().lower() in ("1", "true", "yes")
        if parser_only:
            batch_or_cics = "Unknown"
            io_files = "None explicitly mentioned (parser-only)."
            db_tables = "None referenced (parser-only)."
            logger.info("Discovery: parser-only, skipping LLM")
        else:
            inventory = _build_inventory_text(cobol_files)
            model = get_model_for_agent(self.agent_id)
            temp = get_temperature(self.agent_id)
            llm_out = _invoke_llm_for_classification(inventory, model, temp)
            batch_or_cics = llm_out["batch_or_cics"]
            io_files = llm_out["io_files"]
            db_tables = llm_out["db_tables"]

        # DOCX sections (all from parser except the three classification lines)
        sections = [
            {"title": "Programs", "body": _section_programs(programs)},
            {"title": "Batch vs CICS", "body": batch_or_cics},
            {"title": "Copybooks Used", "body": _section_copybooks(copybooks)},
            {"title": "Input/Output Files", "body": io_files},
            {"title": "Database Tables", "body": db_tables},
            {"title": "Called Programs", "body": _section_called(called_programs)},
            {"title": "Call Linkages", "body": _section_call_linkages(call_linkages)},
        ]

        out_dir = Path(context.output_dir) / "01_discovery"
        out_dir.mkdir(parents=True, exist_ok=True)
        docx_path = out_dir / "01_COBOL_Codebase_Overview.docx"
        write_docx(sections, docx_path, title="COBOL Codebase Overview")

        discovery = {
            "programs": programs,
            "copybooks": sorted(copybooks),
            "called_programs": sorted(called_programs),
            "call_linkages": call_linkages,
            "batch_or_cics": batch_or_cics,
            "file_count": len(cobol_files),
            "parser_only": parser_only,
        }
        json_path = out_dir / "discovery.json"
        with open(json_path, "w") as f:
            json.dump(discovery, f, indent=2)

        logger.info(
            "Discovery: %d programs, %d copybooks, %d called, %d call linkages",
            len(programs), len(copybooks), len(called_programs), len(call_linkages),
        )
        return AgentResult(
            artifacts={
                "01_COBOL_Codebase_Overview.docx": str(docx_path),
                "discovery.json": str(json_path),
            }
        )
