from typing import TypedDict, List, Dict, Any


class ResearchState(TypedDict):
    query: str
    research_plan: str
    keywords: List[str]
    papers: List[Dict[str, Any]]
    analyses: List[str]
    retrieved_context: str
    final_report: str
