# Discovery Agent: Full-Knowledge Plan

## Goal
The LLM must have **full knowledge** of every file in the codebase before performing discovery. No truncation, no partial view.

## Problem with current approach
- Sending raw source in one request is capped (~90k chars). Large codebases get truncated, so the LLM does not see all files.
- Chunking gave the LLM only a partial view per request, so outputs were incomplete or empty.

## Plan: Two-phase, inventory-first

### Phase 1 – Build complete inventory (no size limit)
- **Input:** All COBOL files under the codebase directory (every `.cbl`, `.cpy`).
- **Action:** Run a lightweight parser over **every** file (no truncation). For each file extract:
  - File path (as in codebase)
  - PROGRAM-ID (if present)
  - COPY names used in this file
  - CALL names used in this file
  - Optional: hints for I/O (SELECT, FD) and DB (EXEC SQL) for the LLM to interpret
- **Output:** A single **structured text block** (the “full inventory”). Format is compact: e.g. one block per file with fixed fields so the LLM can see the whole codebase in one place. Size is O(files × ~10 lines) so it fits in context even for hundreds of files.

**Result:** A string that describes every file. No file is omitted. The LLM will receive this entire string.

### Phase 2 – LLM discovery on full inventory
- **Input:** The complete inventory string from Phase 1.
- **Action:** One LLM request. Prompt states:
  - “Below is the **complete** inventory of the codebase. Every file is listed with path, program ID, copybooks, and calls.”
  - “Using only this inventory, produce the discovery sections: Programs (with path), Batch vs CICS, Copybooks Used, I/O, DB, Called Programs, Call Linkages. Use exact paths and names from the inventory.”
- **Output:** Same as today: parsed sections → DOCX + discovery.json (programs, copybooks, called_programs, call_linkages, batch_or_cics).

**Result:** The LLM has full knowledge (of the inventory) and performs discovery in one shot. DOCX and JSON stay in sync and reflect the whole codebase.

### Modes
| Mode | Phase 1 | Phase 2 | When |
|------|---------|---------|------|
| **LLM (default)** | Build full inventory (all files) | Send full inventory to LLM → DOCX + JSON | Normal run |
| **Parser-only** | Same parser data | No LLM; build DOCX + JSON from parser only | `DISCOVERY_PARSER_ONLY=1` |

### Benefits
1. **Full knowledge:** Every file is represented in the inventory; nothing is dropped.
2. **Single LLM call:** One request, one response; no chunking of discovery.
3. **Fits context:** Inventory is much smaller than full source, so large codebases still fit.
4. **Deterministic coverage:** Parser guarantees all files are included; LLM adds classification and narrative (Batch/CICS, I/O, DB, formatting).

### Implementation outline
1. Add `_build_full_inventory(cobol_files: dict) -> str` that returns the compact text for every file (path, PROGRAM-ID, COPY list, CALL list, optional I/O/DB hints).
2. Add `DISCOVERY_PROMPT_FULL_KNOWLEDGE` that explains the inventory and asks for the seven sections with exact paths/names.
3. In `DiscoveryAgent.run()` (LLM path): call `_build_full_inventory(cobol_files)` → `prompt = DISCOVERY_PROMPT_FULL_KNOWLEDGE + "\n\n" + inventory` → `response = generate(prompt, ...)` → parse → DOCX + JSON (unchanged).
4. Parser-only path unchanged; optional: reuse the same inventory format for consistency.
