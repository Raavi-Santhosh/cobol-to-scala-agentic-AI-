"""Input/output contracts per agent. Orchestrator checks these before/after each run."""

AGENT_CONTRACTS = {
    "agent_1": {
        "required_inputs": ["cobol_source"],
        "outputs": [
            ("docx", "01_COBOL_Codebase_Overview.docx"),
            ("json", "discovery.json"),
        ],
    },
    "agent_2": {
        "required_inputs": ["cobol_source", "01_COBOL_Codebase_Overview.docx"],
        "outputs": [
            ("docx", "02_Dependency_and_Call_Graph.docx"),
            ("json", "dependency_graph.json"),
        ],
    },
    "agent_3": {
        "required_inputs": [
            "cobol_source",
            "01_COBOL_Codebase_Overview.docx",
            "02_Dependency_and_Call_Graph.docx",
            "dependency_graph.json",
        ],
        "outputs": [
            ("docx", "03_Business_Logic_Specification.docx"),
            ("json", "business_rules.json"),
        ],
    },
    "agent_4": {
        "required_inputs": ["cobol_source", "03_Business_Logic_Specification.docx"],
        "outputs": [
            ("docx", "04_Technical_Design_COBOL.docx"),
            ("json", "technical_analysis.json"),
        ],
    },
    "agent_5": {
        "required_inputs": [
            "03_Business_Logic_Specification.docx",
            "04_Technical_Design_COBOL.docx",
        ],
        "outputs": [
            ("docx", "05_Pseudocode_Language_Neutral.docx"),
            ("json", "pseudocode.json"),
        ],
    },
    "agent_6": {
        "required_inputs": [
            "03_Business_Logic_Specification.docx",
            "04_Technical_Design_COBOL.docx",
            "05_Pseudocode_Language_Neutral.docx",
        ],
        "outputs": [
            ("docx", "06_Scala_Design_Specification.docx"),
            ("json", "scala_design.json"),
        ],
    },
    "agent_7": {
        "required_inputs": [
            "05_Pseudocode_Language_Neutral.docx",
            "06_Scala_Design_Specification.docx",
        ],
        "outputs": [("dir", "target_source_dir")],
    },
    "agent_8": {
        "required_inputs": ["03_Business_Logic_Specification.docx", "target_source_dir"],
        "outputs": [
            ("docx", "08_Parity_and_Validation_Report.docx"),
        ],
    },
    "agent_9": {
        "required_inputs": [
            "01_COBOL_Codebase_Overview.docx",
            "02_Dependency_and_Call_Graph.docx",
            "03_Business_Logic_Specification.docx",
            "04_Technical_Design_COBOL.docx",
            "05_Pseudocode_Language_Neutral.docx",
            "06_Scala_Design_Specification.docx",
            "08_Parity_and_Validation_Report.docx",
        ],
        "outputs": [
            ("docx", "07_Scala_Business_and_Technical_Design.docx"),
        ],
    },
}


def get_contract(agent_id: str) -> dict:
    if agent_id not in AGENT_CONTRACTS:
        raise ValueError(f"Unknown agent: {agent_id}")
    return AGENT_CONTRACTS[agent_id].copy()


def required_inputs(agent_id: str) -> list:
    return get_contract(agent_id)["required_inputs"]


def output_artifacts(agent_id: str) -> list:
    return get_contract(agent_id)["outputs"]

