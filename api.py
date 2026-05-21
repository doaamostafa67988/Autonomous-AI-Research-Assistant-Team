import logger_setup
"""
api.py — FastAPI entry point. Import logger_setup FIRST.
"""
  # noqa: F401  — must be first

import asyncio
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from workflow import research_graph

log = logging.getLogger("api")
PIPELINE_TIMEOUT_SECONDS = 150

app = FastAPI(
    title="Multi-Agent Research Assistant",
    description=(
        "Orchestrates AI agents to search Semantic Scholar, the web, and GitHub, "
        "then synthesises a grounded literature review with citations."
    ),
    version="1.0.0",
)


class ResearchRequest(BaseModel):
    query: str = Field(..., min_length=3, description="The research topic or question.")


class PaperCard(BaseModel):
    rank:         int
    title:        str
    key_takeaway: str
    authors:      list[str]
    published:    str
    citations:    int
    url:          str
    source:       str


class ResearchResponse(BaseModel):
    query:        str
    plan:         str
    keywords:     list[str]
    papers:       list[PaperCard]
    report:       str
    papers_found: int


@app.post("/research", response_model=ResearchResponse)
async def run_research(request: ResearchRequest):
    query = request.query.strip()
    log.info("")
    log.info("#" * 60)
    log.info(f"# NEW REQUEST: {query}")
    log.info("#" * 60)

    initial_state = {
        "query":             query,
        "research_plan":     "",
        "keywords":          [],
        "papers":            [],
        "analyses":          [],
        "retrieved_context": "",
        "final_report":      "",
    }

    try:
        state = await asyncio.wait_for(
            research_graph.ainvoke(initial_state),
            timeout=PIPELINE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        log.error("Pipeline timed out after %s seconds", PIPELINE_TIMEOUT_SECONDS)
        raise HTTPException(
            status_code=504,
            detail="Research pipeline timed out. Try a narrower topic.",
        )
    except Exception as exc:
        log.error(f"Pipeline error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

    raw_papers = state.get("papers", [])
    s2_papers  = [p for p in raw_papers if p.get("source") == "semantic_scholar"]
    other      = [p for p in raw_papers if p.get("source") != "semantic_scholar"]
    ranked     = s2_papers + other

    cards = [
        PaperCard(
            rank         = i + 1,
            title        = p.get("title", ""),
            key_takeaway = p.get("key_takeaway", p.get("summary", ""))[:300],
            authors      = p.get("authors", []),
            published    = p.get("published", ""),
            citations    = p.get("citations", 0),
            url          = p.get("url", ""),
            source       = p.get("source", ""),
        )
        for i, p in enumerate(ranked)
    ]

    log.info(f"# REQUEST DONE — {len(raw_papers)} papers, report generated")
    log.info("#" * 60)

    return ResearchResponse(
        query        = query,
        plan         = state.get("research_plan", ""),
        keywords     = state.get("keywords", []),
        papers       = cards,
        report       = state.get("final_report", ""),
        papers_found = len(raw_papers),
    )


@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}
