import sys, asyncio, hashlib, logging, time
from langgraph.graph import StateGraph, END
from graph_state import ResearchState
from agents import ResearchCoordinator, ContentAnalyzer, SynthesisAgent, CitationManager
from search import SearchEngine
from rag import RAGStore

log = logging.getLogger("workflow")
MAX_SOURCES = 10
def _p(msg):
    try:
        print(msg, file=sys.stderr, flush=True)
    except OSError:
        pass
    log.info(msg)

_search      = SearchEngine()
_coordinator = ResearchCoordinator()
_analyzer    = ContentAnalyzer()
_synthesizer = SynthesisAgent()
_citations   = CitationManager()
_rag_sessions = {}

def _get_rag(query):
    key = hashlib.md5(query.encode()).hexdigest()
    if key not in _rag_sessions:
        _rag_sessions[key] = RAGStore(session_id=key)
    return _rag_sessions[key]

async def node_coordinator(state: ResearchState):
    return await _coordinator.create_plan(state)

async def node_searcher(state: ResearchState):
    _p("\n" + "="*50)
    _p("[STEP 2/4] Searcher")
    _p("="*50)
    keywords = state.get("keywords", [])
    search_query = " ".join(keywords[:4]) if keywords else state["query"]
    _p(f"  Query: '{search_query}'")
    t0 = time.time()
    papers = await _search.search_all(search_query)
    if not papers:
        _p("  Retrying with original query...")
        papers = await _search.search_all(state["query"])
    papers = papers[:MAX_SOURCES]
    _p(f"  Total: {len(papers)} papers in {time.time()-t0:.1f}s")
    _p("  Indexing into RAG...")
    rag = _get_rag(state["query"])
    docs = [{"content": p.get("abstract") or p.get("summary",""),
             "title": p.get("title",""), "url": p.get("url",""),
             "source": p.get("source","unknown"), "authors": p.get("authors",[]),
             "published": p.get("published","")} for p in papers]
    rag.add(docs)
    _p(f"  RAG: indexed {len(docs)} docs")
    _p("[STEP 2/4] DONE\n")
    return {"papers": papers}

async def node_analyze_and_retrieve(state: ResearchState):
    _p("\n" + "="*50)
    _p("[STEP 3/4] Analyze + RAG Retrieve")
    _p("="*50)
    rag = _get_rag(state["query"])

    async def _analyse():
        return await _analyzer.analyse_all(state)

    async def _retrieve():
        _p("  [RAG] Retrieving chunks...")
        t0 = time.time()
        chunks = rag.retrieve(state["query"], k=5)
        texts = [c["text"] for c in chunks if c.get("text")]
        _p(f"  [RAG] {len(texts)} chunks in {time.time()-t0:.1f}s")
        return "\n---\n".join(texts) if texts else ""

    t0 = time.time()
    analysis_result, context = await asyncio.gather(_analyse(), _retrieve())
    _p(f"[STEP 3/4] DONE in {time.time()-t0:.1f}s\n")
    return {"analyses": analysis_result["analyses"], "retrieved_context": context}

async def node_synthesizer(state: ResearchState):
    if not state.get("papers"):
        _p("  WARNING: No papers found")
        return {"final_report": "## No Sources Found\n\nPlease try a more specific topic."}
    report = await _synthesizer.generate_report(state)
    refs   = _citations.format(state["papers"])
    full   = f"{report['final_report']}\n\n---\n\n## References\n\n{refs}"
    _p("\n" + "#"*50)
    _p("# PIPELINE COMPLETE!")
    _p("#"*50 + "\n")
    return {"final_report": full}

_wf = StateGraph(ResearchState)
_wf.add_node("coordinator",          node_coordinator)
_wf.add_node("searcher",             node_searcher)
_wf.add_node("analyze_and_retrieve", node_analyze_and_retrieve)
_wf.add_node("synthesizer",          node_synthesizer)
_wf.set_entry_point("coordinator")
_wf.add_edge("coordinator",          "searcher")
_wf.add_edge("searcher",             "analyze_and_retrieve")
_wf.add_edge("analyze_and_retrieve", "synthesizer")
_wf.add_edge("synthesizer",          END)
research_graph = _wf.compile()
