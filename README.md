# 🔬 Multi-Agent Research Assistant

> An autonomous AI system that searches academic papers, the web, and GitHub — then synthesises a structured literature review in under 90 seconds.

[![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python)](https://python.org)
[![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-orange)](https://github.com/langchain-ai/langgraph)
[![Streamlit](https://img.shields.io/badge/UI-Streamlit-red?logo=streamlit)](https://streamlit.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)


---
## 📺 Demo

*The demo video below shows a complete run from query to exported PDF.*

https://github.com/user-attachments/assets/7131a4f3-9a2e-4129-b7d6-29a55924a585

---

## 🏗️ Architecture

![Multi-Agent Research Assistant Architecture Diagram](https://github.com/user-attachments/assets/03f69207-8a28-4654-a00b-0b2022874722)

*Five-agent LangGraph pipeline: Coordinator → Search → Analyze+RAG (parallel) → Synthesise → Citations*

---

## 🚀 Live App

**[→ Open on Streamlit Cloud](https://autonomous-ai-research-assistant-team.streamlit.app/)**

---

## ✨ Features

| Feature | Detail |
|---|---|
| **Multi-source search** | OpenAlex (academic), Serper (web), GitHub — in parallel |
| **RAG grounding** | ChromaDB indexes all sources; synthesis is grounded in retrieved chunks |
| **Structured report** | 7-section literature review: Executive Summary → Conclusion |
| **Ranked source cards** | TLDR, authors, year, citation count per paper |
| **In-app export** | `st.download_button` serves Markdown and PDF directly — no CLI needed |
| **Session isolation** | Each query gets its own ChromaDB collection |
| **Research history** | PostgreSQL stores past queries and reports *(planned — see roadmap)* |

---

## 🏗️ Architecture

```
User → Streamlit (app.py)
          │
          ▼
       LangGraph (workflow.py)
          │
  ┌── Research Coordinator ──────────────┐
  │  Parses query · builds keyword plan  │
  └───────────────┬──────────────────────┘
                  │
  ┌── Web Search Agent ─────────────────────────────┐
  │  OpenAlex · Serper · GitHub  →  ChromaDB index  │
  └───────────────┬─────────────────────────────────┘
                  │   asyncio.gather
        ┌─────────┴──────────┐
        ▼                    ▼
  Content Analyzer      RAG Retrieval
  (per-source LLM)     (ChromaDB top-k)
        └─────────┬──────────┘
                  ▼
  ┌── Synthesis Agent ──────────────────────────────┐
  │  7-section literature review (RAG-grounded)     │
  └───────────────┬─────────────────────────────────┘
                  ▼
  ┌── Citation Manager ─────────────────────────────┐
  │  Formats references · full metadata             │
  └───────────────┬─────────────────────────────────┘
                  ▼
       st.download_button  →  PDF or Markdown
```

### Agent roles

| Agent | File | Responsibility |
|---|---|---|
| Research Coordinator | `agents.py` | Parses query, produces research plan and keyword list |
| Web Search Agent | `search.py` | Queries OpenAlex, Serper, and GitHub concurrently |
| Content Analyzer | `agents.py` | Extracts contribution, method, results, and limitations per source |
| Synthesis Agent | `agents.py` | Writes the 7-section literature review grounded in RAG context |
| Citation Manager | `agents.py` | Formats references with authors, year, source type, citation count, URL |

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Agent orchestration | [LangGraph](https://github.com/langchain-ai/langgraph) |
| LLM | Groq — `llama-3.3-70b-versatile` |
| Academic search | [OpenAlex API](https://docs.openalex.org/) *(no key required)* |
| Web search | [Serper API](https://serper.dev/) *(optional)* |
| Code search | [GitHub API](https://docs.github.com/en/rest) *(optional)* |
| Vector store | [ChromaDB](https://www.trychroma.com/) |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` |
| Backend | FastAPI + Uvicorn |
| Frontend | Streamlit |
| PDF export | ReportLab *(via `Exporter` class)* |
| Research history *(planned)* | PostgreSQL |

---

## ⬇️ Export / Download

Reports are exported **directly in the browser** via Streamlit's `st.download_button` — no scripts, no manual file paths.

Once a report is generated, two buttons appear below the Literature Review panel:

| Button | Format | How it works |
|---|---|---|
| 📄 Markdown | `.md` | `Exporter.to_markdown()` encodes the report as UTF-8 bytes |
| 📕 PDF | `.pdf` | `Exporter.to_pdf()` renders via ReportLab into a temp file, reads bytes, cleans up |

The PDF is cached in `st.session_state` so re-clicking the Markdown button does not re-render the PDF.

```python
# The implementation lives in app.py → render_export_buttons()
st.download_button(
    label="📕 PDF",
    data=pdf_bytes,          # bytes from Exporter.to_pdf()
    file_name="report.pdf",
    mime="application/pdf",
)
```

> **Why not a CLI script?**  
> A script writing to disk requires users to know the output path and manually open the file. `st.download_button` serves the file through the browser in one click — no filesystem access needed, and it works on Streamlit Cloud where the server filesystem is ephemeral.

---

## 🚦 Getting Started

### 1. Clone

```bash
git clone https://github.com/your-username/research-assistant.git
cd research-assistant
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env`:

```env
GROQ_API_KEY=your_groq_key          # required
SERPER_API_KEY=your_serper_key      # optional — enables web search
GITHUB_TOKEN=your_github_token      # optional — enables GitHub search
```

> **Groq** is free at [console.groq.com](https://console.groq.com).  
> **Serper** free tier: 2,500 searches/month at [serper.dev](https://serper.dev).  
> **OpenAlex** requires no API key.

### 4. Run

```bash
# Terminal 1 — backend (optional; app runs locally without it by default)
uvicorn api:app --reload --port 8000

# Terminal 2 — frontend
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501).

---

## 📁 Project Structure

```
research-assistant/
├── agents.py          # Coordinator, Analyzer, Synthesizer, CitationManager
├── workflow.py        # LangGraph StateGraph — node wiring and execution order
├── search.py          # Unified search: OpenAlex, Serper, GitHub
├── rag.py             # ChromaDB RAG store with per-session collection isolation
├── graph_state.py     # Shared TypedDict state for the LangGraph pipeline
├── api.py             # FastAPI — POST /research, GET /health
├── app.py             # Streamlit UI + st.download_button export
├── exporter.py        # Exporter class: to_markdown(), to_pdf() via ReportLab
├── requirements.txt
├── .env.example
├── docs/
│   ├── architecture.svg   # Pipeline diagram
│   └── demo.mp4           # Screen recording
└── .gitignore
```

---

## 🌐 API Reference

### `POST /research`

```json
// Request
{ "query": "Transformer Architectures in NLP" }

// Response
{
  "query":        "Transformer Architectures in NLP",
  "plan":         "Research plan text...",
  "keywords":     ["transformers", "attention", "BERT", "NLP"],
  "papers_found": 12,
  "papers": [
    {
      "rank": 1,
      "title": "Attention Is All You Need",
      "key_takeaway": "Introduces the Transformer architecture...",
      "authors": ["Ashish Vaswani", "Noam Shazeer"],
      "published": "2017",
      "citations": 98432,
      "url": "https://...",
      "source": "semantic_scholar"
    }
  ],
  "report": "# Transformer Architectures in NLP\n\n## Executive Summary\n..."
}
```

### `GET /health`

```json
{ "status": "ok", "version": "1.0.0" }
```

---

## 🗺️ Roadmap

- [x] Multi-source parallel search (OpenAlex, Serper, GitHub)
- [x] RAG-grounded synthesis with ChromaDB
- [x] In-app PDF and Markdown export via `st.download_button`
- [x] Session-isolated vector collections
- [ ] PostgreSQL research history — save and reload past reports
- [ ] User authentication for history persistence on Streamlit Cloud
- [ ] arXiv API integration for preprint search
- [ ] Export to DOCX with proper heading styles

---

## 📄 License

MIT
