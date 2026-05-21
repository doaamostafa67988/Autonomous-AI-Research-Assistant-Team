import os, sys, json, asyncio, time, logging
from groq import Groq
from dotenv import load_dotenv
from graph_state import ResearchState

load_dotenv()
_client = Groq(api_key=os.getenv("GROQ_API_KEY"), timeout=45.0, max_retries=1)
_MODEL  = "llama-3.3-70b-versatile"
_ANALYSIS_LIMIT = 6
_ANALYSIS_CONCURRENCY = 2
log = logging.getLogger("agents")

def _p(msg: str):
    try:
        print(msg, file=sys.stderr, flush=True)
    except OSError:
        pass
    log.info(msg)

def _chat(messages, temperature=0.3, max_tokens=2048):
    resp = _client.chat.completions.create(
        model=_MODEL, messages=messages,
        temperature=temperature, max_tokens=max_tokens,
    )
    return resp.choices[0].message.content

def _clip(text, max_chars):
    text = " ".join(str(text or "").split())
    return text[:max_chars].rstrip()

async def _async_chat(messages, label="LLM", **kwargs):
    t0 = time.time()
    _p(f"  --> [{label}] Calling Groq...")
    loop = asyncio.get_running_loop()
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: _chat(messages, **kwargs)),
            timeout=60,
        )
        _p(f"  <-- [{label}] Done in {time.time()-t0:.1f}s ({len(result)} chars)")
        return result
    except asyncio.TimeoutError:
        _p(f"  !! [{label}] Timed out after {time.time()-t0:.1f}s")
        raise

class ResearchCoordinator:
    async def create_plan(self, state: ResearchState) -> dict:
        _p("\n" + "="*50)
        _p(f"[STEP 1/4] ResearchCoordinator — '{state['query']}'")
        _p("="*50)
        
  
        prompt = f"""You are a research planning expert. Analyse this topic and return a JSON object.

CRITICAL INSTRUCTIONS FOR KEYWORDS:
- Provide a maximum of 2-3 keywords total in the list.
- Each keyword MUST be extremely short (maximum 1-2 words). For example, use ["LSTM", "NLP"] instead of ["Long Short Term Memory Networks for NLP"].
- Keep them strictly focused on the core specific technology.

Topic: {state['query']}
Return ONLY valid JSON:
{{
  "research_plan": "2-3 sentence overview",
  "keywords": ["short_keyword1", "short_keyword2"],
  "subtopics": ["subtopic1", "subtopic2"]
}}"""
        try:
            raw = await _async_chat(
                [{"role": "user", "content": prompt}],
                label="Coordinator",
                temperature=0.1,
                max_tokens=900,
            )
        except Exception as exc:
            _p(f"   WARNING: Coordinator failed: {exc}")
            return {
                "research_plan": f"Search and summarize reliable sources about {state['query']}.",
                "keywords": [state["query"]],
            }
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        try:
            data = json.loads(raw)
        except Exception:
            _p("   WARNING: JSON parse failed")
            data = {"research_plan": raw, "keywords": [state["query"]], "subtopics": []}
            
        
        keywords = data.get("keywords", [state["query"]])
        if isinstance(keywords, list) and len(keywords) > 2:
            keywords = keywords[:2]
            
        _p(f"   Keywords: {keywords}")
        _p("[STEP 1/4] DONE\n")
        return {"research_plan": data.get("research_plan", ""), "keywords": keywords}
class ContentAnalyzer:
    async def _analyse_one(self, paper, index, total):
        title    = paper.get("title", "Unknown Title")
        content  = paper.get("summary") or paper.get("abstract", "")
        source   = paper.get("source", "unknown")
        takeaway = paper.get("key_takeaway", "")
        _p(f"    [{index}/{total}] ({source}): {title[:60]}...")
        prompt = f"""Analyse this source:
Source: {source} | Title: {title}
Takeaway: {_clip(takeaway, 500)}
Content: {_clip(content, 900)}
Headings: Main Contribution, Methodology, Key Results, Strengths, Limitations."""
        try:
            result = await _async_chat(
                [{"role": "user", "content": prompt}],
                label=f"Analyzer {index}/{total}",
                temperature=0.2,
                max_tokens=850,
            )
        except Exception as exc:
            _p(f"    [{index}/{total}] Analysis fallback: {exc}")
            result = (
                f"Main Contribution: {takeaway or content[:350] or 'No abstract was available.'}\n\n"
                "Methodology: Not stated in the retrieved snippet.\n\n"
                "Key Results: See the source for full details.\n\n"
                "Strengths: Included as a relevant search result.\n\n"
                "Limitations: Limited metadata was available for automated analysis."
            )
        return f"### {title}\n{result}"

    async def analyse_all(self, state: ResearchState) -> dict:
        papers = state.get("papers", [])[:_ANALYSIS_LIMIT]
        skipped = max(0, len(state.get("papers", [])) - len(papers))
        if skipped:
            _p(f"  Skipping {skipped} lower-ranked sources to keep response time bounded")
        _p(f"\n[STEP 3a/4] ContentAnalyzer — {len(papers)} papers")
        if not papers:
            return {"analyses": ["No sources retrieved."]}
        t0 = time.time()
        sem = asyncio.Semaphore(_ANALYSIS_CONCURRENCY)

        async def _bounded(paper, index):
            async with sem:
                return await self._analyse_one(paper, index, len(papers))

        tasks = [_bounded(p, i + 1) for i, p in enumerate(papers)]
        analyses = await asyncio.gather(*tasks)
        _p(f"[STEP 3a/4] DONE — {len(analyses)} analyses in {time.time()-t0:.1f}s\n")
        return {"analyses": list(analyses)}

class SynthesisAgent:
    async def generate_report(self, state: ResearchState) -> dict:
        _p("\n" + "="*50)
        _p("[STEP 4/4] SynthesisAgent — writing report...")
        _p("="*50)
        analyses = "\n\n---\n\n".join(_clip(a, 900) for a in state.get("analyses", []))
        context  = _clip(state.get("retrieved_context", "") or "No context.", 1800)
        query    = state["query"]
        plan     = state.get("research_plan", "")
        papers   = state.get("papers", [])
        _p(f"  {len(papers)} papers, {len(state.get('analyses',[]))} analyses")
        top_papers = "\n".join(
            f"- {p['title']} ({p.get('published','?')}) — {p.get('citations',0)} citations"
            for p in papers[:8]
        )
        prompt = f"""Write a concise literature review.
TOPIC: {query} | PLAN: {_clip(plan, 600)}
TOP SOURCES:\n{top_papers}
RAG CONTEXT:\n{context}
ANALYSES:\n{analyses}
Sections: Executive Summary, Introduction, Core Themes, Methodologies, Challenges, Future Directions, Conclusion.
Keep it around 500-700 words. No fabricated facts."""
        try:
            result = await _async_chat(
                [{"role": "user", "content": prompt}],
                label="Synthesizer",
                temperature=0.3,
                max_tokens=1600,
            )
        except Exception as exc:
            _p(f"  WARNING: Synthesizer failed, using fallback report: {exc}")
            highlights = "\n".join(f"- {p.get('title', 'Untitled')}" for p in papers[:6])
            result = (
                "## Executive Summary\n\n"
                f"The pipeline found {len(papers)} sources for **{query}**, but the language model "
                "timed out while writing the full narrative report.\n\n"
                "## Retrieved Sources\n\n"
                f"{highlights or '- No source titles available.'}\n\n"
                "## Next Step\n\n"
                "Run the query again with a narrower topic to generate a fuller synthesis."
            )
        _p("[STEP 4/4] DONE\n")
        return {"final_report": result}

class CitationManager:
    def format(self, papers):
        _p(f"  Citations: formatting {len(papers)} refs")
        if not papers:
            return "_No sources._"
        lines = []
        for i, p in enumerate(papers, 1):
            a = p.get("authors", [])
            authors = ", ".join(a[:3]) + (" et al." if len(a) > 3 else "") if a else "Unknown"
            ref = f"[{i}] **{authors}**. *{p.get('title','Untitled')}*."
            if p.get("published"): ref += f" {p['published']}."
            ref += f" [{p.get('source','').replace('_',' ').title()}]"
            if p.get("citations"):  ref += f" · {p['citations']:,} citations"
            if p.get("url"):        ref += f"\n    <{p['url']}>"
            lines.append(ref)
        return "\n\n".join(lines)
