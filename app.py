"""
app.py — Streamlit frontend for the Multi-Agent Research Assistant.

Export feature: uses Exporter.to_pdf() and Exporter.to_markdown() to generate
in-memory bytes that are served via st.download_button — no CLI scripts needed.
"""

import asyncio
import io
import logging
import sys
import tempfile
from pathlib import Path

import streamlit as st

import logger_setup  # noqa: F401
from exporter import Exporter
from html import escape

API_URL  = "http://localhost:8000/research"
USE_BACKEND_API = False
log      = logging.getLogger("streamlit_app")
_exp     = Exporter()

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

st.set_page_config(
    page_title="Research Assistant",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .paper-card {
    background:#f8f9fa; border:1px solid #e9ecef;
    border-radius:10px; padding:14px 16px; margin-bottom:12px;
  }
  .paper-rank {
    background:#1f3c88; color:white; border-radius:50%;
    width:28px; height:28px; display:inline-flex;
    align-items:center; justify-content:center;
    font-weight:700; font-size:13px; margin-right:8px;
  }
  .paper-title { font-weight:600; font-size:15px; color:#1a1a2e; line-height:1.4; }
  .takeaway-label {
    font-size:10px; font-weight:700; color:#6c757d;
    letter-spacing:.08em; text-transform:uppercase;
    margin-top:8px; margin-bottom:2px;
  }
  
  .takeaway-text { font-size:13px; color:#444; line-height:1.5; }
  .meta-row { font-size:12px; color:#868e96; margin-top:8px; }
  .badge {
    display:inline-flex; align-items:center; gap:6px;
    padding:2px 9px 2px 4px; border-radius:999px;
    font-size:11px; font-weight:600; margin-left:4px;
  }
  .source-logo {
    width:20px; height:20px; border-radius:50%;
    display:inline-flex; align-items:center; justify-content:center;
    color:white; font-size:9px; font-weight:800;
  }
  .source-logo-s2  { background:#185abc; }
  .source-logo-web { background:#0b7a4b; }
  .source-logo-gh  { background:#24292f; }
  .badge-s2  { background:#e7f3ff; color:#0366d6; }
  .badge-web { background:#f0fff4; color:#2d7d32; }
  .badge-gh  { background:#fff3e0; color:#e65100; }
  .stat-grid {
    display:grid; grid-template-columns:repeat(4,minmax(0,1fr));
    gap:16px; margin:12px 0 20px;
  }
  .stat-card {
    border:1px solid #e5e7eb; border-radius:8px;
    padding:14px 16px; background:#ffffff;
  }
  .stat-label { color:#6b7280; font-size:13px; margin-bottom:6px; }
  .stat-value { color:#111827; font-size:30px; font-weight:700; }
  @media(max-width:900px){ .stat-grid{ grid-template-columns:repeat(2,minmax(0,1fr)); } }
  @media(max-width:520px){ .stat-grid{ grid-template-columns:1fr; } }
 div[data-testid="stDownloadButton"] button {
    width: 100% !important;
    padding-left: 8px !important;
    padding-right: 8px !important;
  }
  div[data-testid="stDownloadButton"] button p {
    white-space: nowrap !important;
    word-break: keep-all !important;
    font-size: 14px !important; /* Slightly optimizes font scale to fit the container */
  }
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────
def source_badge(source: str) -> str:
    mapping = {
        "semantic_scholar": ("Semantic Scholar", "badge-s2",  "source-logo-s2",  "S2"),
        "web":              ("Web",              "badge-web", "source-logo-web", "WEB"),
        "github":           ("GitHub",           "badge-gh",  "source-logo-gh",  "GH"),
    }
    label, cls, logo_cls, initials = mapping.get(
        source, (source.title(), "badge-s2", "source-logo-s2", "SRC")
    )
    return (
        f'<span class="badge {cls}">'
        f'<span class="source-logo {logo_cls}">{initials}</span>'
        f'{escape(label)}</span>'
    )


def render_paper_card(paper: dict):
    rank     = paper["rank"]
    title    = escape(str(paper.get("title", "")))
    takeaway = escape((paper.get("key_takeaway") or "").strip())
    authors  = paper.get("authors", [])
    year     = paper.get("published", "")
    cites    = paper.get("citations", 0)
    url      = paper.get("url", "")
    source   = paper.get("source", "")

    author_str = escape(", ".join(authors[:2]))
    if len(authors) > 2:
        author_str += f" +{len(authors)-2} more"

    meta_parts = []
    if year:       meta_parts.append(f"<b>{escape(str(year))}</b>")
    if cites:      meta_parts.append(f"<b>{cites:,}</b> citations")
    if author_str: meta_parts.append(author_str)
    meta_html = " | ".join(meta_parts) + source_badge(source)
    link_html = f'<a href="{escape(url)}" target="_blank" style="font-size:12px;">Open →</a>' if url else ""

    st.markdown(f"""
<div class="paper-card">
  <div>
    <span class="paper-rank">{rank}</span>
    <span class="paper-title">{title}</span>
    {link_html}
  </div>
  {"<div class='takeaway-label'>KEY TAKEAWAY</div><div class='takeaway-text'>" + takeaway + "</div>" if takeaway else ""}
  <div class="meta-row">{meta_html}</div>
</div>""", unsafe_allow_html=True)


def render_stat_grid(stats: list):
    cards = []
    for label, value in stats:
        cards.append(
            "<div class='stat-card'>"
            f"<div class='stat-label'>{escape(label)}</div>"
            f"<div class='stat-value'>{int(value):,}</div>"
            "</div>"
        )
    st.markdown(f"<div class='stat-grid'>{''.join(cards)}</div>", unsafe_allow_html=True)


# ── Export helpers ────────────────────────────────────────────────────────
def _build_full_report(data: dict) -> str:
    """Compose the complete report text including the sources list."""
    papers = data.get("papers", [])
    source_lines = "\n".join(
        f"- {p.get('title', 'Untitled')} ({p.get('source', 'unknown')})"
        for p in papers
    )
    return (
        f"# {data.get('query', 'Research Report')}\n\n"
        f"{data.get('report', 'No report generated.')}\n\n"
        "## Retrieved Sources\n\n"
        f"{source_lines or '- No sources retrieved.'}\n"
    )


def _export_pdf_bytes(report_text: str) -> bytes:
    """Render the report to PDF and return the raw bytes."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name
    _exp.to_pdf(report_text, output_path=tmp_path)
    pdf_bytes = Path(tmp_path).read_bytes()
    Path(tmp_path).unlink(missing_ok=True)
    return pdf_bytes


def render_export_buttons(data: dict):
    """
    Render Download as Markdown and Download as PDF buttons.
    Both buttons use st.download_button so the file is served directly in the
    browser — no CLI scripts or manual file paths required.
    """
    report_text = _build_full_report(data)
    safe_query  = data.get("query", "report").replace(" ", "_")[:60]

    st.divider()
    st.markdown("#### ⬇️ Export Report")
    col_md, col_pdf, _ = st.columns([1.8, 1.5, 3])

    with col_md:
        st.download_button(
            label="📄 Markdown",
            data=report_text.encode("utf-8"),
            file_name=f"{safe_query}.md",
            mime="text/markdown",
            use_container_width=True,
        )

    with col_pdf:
        # Build PDF lazily and cache in session_state to avoid re-rendering on
        # every Streamlit rerun triggered by the Markdown button click.
        cache_key = f"pdf_bytes_{safe_query}"
        if cache_key not in st.session_state:
            with st.spinner("Building PDF…"):
                try:
                    st.session_state[cache_key] = _export_pdf_bytes(report_text)
                except Exception as exc:
                    log.exception("PDF export failed")
                    st.error(f"PDF export failed: {exc}")
                    return

        st.download_button(
            label="📕 PDF",
            data=st.session_state[cache_key],
            file_name=f"{safe_query}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )


# ── Pipeline runner ───────────────────────────────────────────────────────
def run_research_locally(query: str) -> dict:
    from workflow import research_graph
    initial_state = {
        "query": query.strip(),
        "research_plan": "",
        "keywords": [],
        "papers": [],
        "analyses": [],
        "retrieved_context": "",
        "final_report": "",
    }
    state = asyncio.run(research_graph.ainvoke(initial_state))
    raw_papers = state.get("papers", [])
    s2_papers  = [p for p in raw_papers if p.get("source") == "semantic_scholar"]
    web_papers = [p for p in raw_papers if p.get("source") == "web"]
    gh_papers  = [p for p in raw_papers if p.get("source") == "github"]
    ranked = s2_papers + web_papers + gh_papers
    cards = [
        {
            "rank": i + 1,
            "title": p.get("title", ""),
            "key_takeaway": (p.get("key_takeaway") or p.get("summary", ""))[:300],
            "authors": p.get("authors", []),
            "published": p.get("published", ""),
            "citations": p.get("citations", 0),
            "url": p.get("url", ""),
            "source": p.get("source", ""),
        }
        for i, p in enumerate(ranked)
    ]
    return {
        "query": query,
        "plan": state.get("research_plan", ""),
        "keywords": state.get("keywords", []),
        "papers": cards,
        "report": state.get("final_report", ""),
        "papers_found": len(raw_papers),
    }


# ── Results renderer ──────────────────────────────────────────────────────
def render_results(data: dict):
    papers   = data.get("papers", [])
    s2_count = sum(1 for p in papers if p.get("source") == "semantic_scholar")
    kws      = data.get("keywords", [])
    report   = data.get("report", "")

    render_stat_grid([
        ("Total Sources",        data.get("papers_found", 0)),
        ("Academic Papers",      s2_count),
        ("Keywords Identified",  len(kws)),
        ("Report Sections",      max(report.count("\n## "), report.count("\n# "))),
    ])

    st.divider()

    if kws:
        st.markdown(" ".join(f"`{k}`" for k in kws))

    left, right = st.columns([3, 2], gap="large")

    with left:
        st.subheader("📄 Literature Review")
        plan = data.get("plan", "")
        if plan:
            with st.expander("Research Strategy", expanded=True):
                st.info(plan)
        st.markdown(report or "No report generated.")

        # ── Download buttons live here, inside the report panel ──────────
        render_export_buttons(data)

    with right:
        total_sources = data.get("papers_found", len(papers))
        st.subheader(f"📚 Sources ({total_sources})")

        s2_list  = [p for p in papers if p.get("source") == "semantic_scholar"]
        web_list = [p for p in papers if p.get("source") == "web"]
        gh_list  = [p for p in papers if p.get("source") == "github"]

        tabs = st.tabs([
            f"Academic ({len(s2_list)})",
            f"Web ({len(web_list)})",
            f"GitHub ({len(gh_list)})",
        ])

        with tabs[0]:
            if s2_list:
                for p in s2_list:
                    render_paper_card(p)
            else:
                st.info("No academic papers retrieved.")

        with tabs[1]:
            if web_list:
                for p in web_list:
                    render_paper_card(p)
            else:
                st.info("No web results retrieved.")

        with tabs[2]:
            if gh_list:
                for p in gh_list:
                    render_paper_card(p)
            else:
                st.info("No GitHub repositories retrieved.")


# ── Page header ───────────────────────────────────────────────────────────
st.title("🔬 Multi-Agent Research Assistant")
st.caption(
    "Searches **OpenAlex** (academic), the web, and GitHub — "
    "then synthesises a grounded literature review with ranked sources."
)

st.markdown("""
<div style="display:flex;gap:10px;align-items:center;margin:12px 0 20px;">
  <span class="badge badge-s2"><span class="source-logo source-logo-s2">S2</span>Academic</span>
  <span class="badge badge-web"><span class="source-logo source-logo-web">WEB</span>Web</span>
  <span class="badge badge-gh"><span class="source-logo source-logo-gh">GH</span>GitHub</span>
</div>
""", unsafe_allow_html=True)

# ── Search form ───────────────────────────────────────────────────────────
with st.form("search_form"):
    query = st.text_input(
        "Research topic",
        placeholder="e.g., Transformer Architectures in NLP",
        label_visibility="collapsed",
    )
    submitted = st.form_submit_button("Generate Report", type="primary")

st.caption("💡 Tip: be specific — *'LSTM for time series forecasting'* returns richer results than *'LSTM'*")

# ── Run pipeline ──────────────────────────────────────────────────────────
if submitted:
    if not query.strip():
        st.warning("Please enter a research topic.")
    else:
        with st.spinner("Orchestrating agents… usually 30–90 seconds"):
            try:
                data = run_research_locally(query)
                st.session_state["last_result"] = data
                st.session_state["last_query"]  = query
            except Exception as exc:
                log.exception("Local research run failed")
                st.error(f"Pipeline error: {exc}")
                data = None

        if data:
            render_results(data)

elif "last_result" in st.session_state:
    render_results(st.session_state["last_result"])
