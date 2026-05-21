"""
search.py — SearchEngine using OpenAlex (replaces Semantic Scholar which is blocked),
             Serper for web, and PyGithub for GitHub.
"""

import os, sys, time, asyncio, logging, httpx, requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
GITHUB_TOKEN   = os.getenv("GITHUB_TOKEN", "")

# OpenAlex — completely free, no API key, no registration, no blocks
_OA_BASE   = "https://api.openalex.org/works"
_OA_MAILTO = os.getenv("OPENALEX_EMAIL", "research@assistant.app")  # polite pool

log = logging.getLogger("search")

def _p(msg):
    try:
        print(msg, file=sys.stderr, flush=True)
    except OSError:
        pass
    log.info(msg)

def _clean_text(text, max_chars=900):
    text = " ".join(str(text or "").split())
    return text[:max_chars].rstrip()

def _normalise_openalex(work):
    """Normalise an OpenAlex work object to the app's paper dict format."""
    title = work.get("title", "Untitled") or "Untitled"

    # Abstract — OpenAlex stores it as an inverted index; reconstruct it
    abstract = ""
    inv = work.get("abstract_inverted_index")
    if inv:
        try:
            words = [""] * (max(pos for positions in inv.values() for pos in positions) + 1)
            for word, positions in inv.items():
                for pos in positions:
                    words[pos] = word
            abstract = " ".join(words)
        except Exception:
            abstract = ""

    # Authors
    authors_raw = work.get("authorships", [])
    authors = []
    for a in authors_raw[:4]:
        name = (a.get("author") or {}).get("display_name", "")
        if name:
            authors.append(name)
    if len(authors_raw) > 4:
        authors.append("et al.")

    # URL — prefer OA PDF, then landing page
    best_oa = work.get("best_oa_location") or {}
    url = best_oa.get("pdf_url") or best_oa.get("landing_page_url") or work.get("doi", "")
    if url and not url.startswith("http"):
        url = "https://doi.org/" + url

    year       = str(work.get("publication_year", ""))
    citations  = work.get("cited_by_count", 0)
    tldr_text  = (work.get("primary_topic") or {}).get("display_name", "")
    summary    = _clean_text(abstract or tldr_text, 900)
    takeaway   = _clean_text(tldr_text or abstract, 500)

    return {
        "title":       title,
        "summary":     summary,
        "key_takeaway": takeaway,
        "abstract":    _clean_text(abstract, 1200),
        "authors":     authors,
        "published":   year,
        "citations":   citations,
        "url":         url,
        "source":      "semantic_scholar",   # keep key so badges/tabs still work
    }


class SearchEngine:
    def __init__(self):
        self._oa_cache = {}

    # ── OpenAlex (replaces Semantic Scholar) ──────────────────────────────
    async def search_semantic_scholar(self, query, limit=8):
        """Fetches from OpenAlex instead of Semantic Scholar (blocked)."""
        if query in self._oa_cache:
            _p(f"  [OA] Cache hit for '{query}'")
            return self._oa_cache[query]

        _p(f"  [OA] Searching OpenAlex: '{query}' limit={limit}")
        t0 = time.time()

        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=25) as client:
                    res = await client.get(
                        _OA_BASE,
                        params={
                            "search": query,
                            "per-page": limit,
                            "select": "title,abstract_inverted_index,authorships,"
                                      "publication_year,cited_by_count,best_oa_location,"
                                      "primary_topic,doi",
                            "sort": "cited_by_count:desc",
                            "mailto": _OA_MAILTO,
                        },
                    )
                    res.raise_for_status()
                    data = res.json()

                works  = data.get("results", [])
                papers = [_normalise_openalex(w) for w in works]
                self._oa_cache[query] = papers
                _p(f"  [OA] Got {len(papers)} papers in {time.time()-t0:.1f}s")
                for i, p in enumerate(papers[:3]):
                    _p(f"       #{i+1}: {p['title'][:55]}... ({p['citations']} citations)")
                return papers

            except httpx.HTTPStatusError as exc:
                _p(f"  [OA] Attempt {attempt+1} HTTP error: {exc}")
                await asyncio.sleep(2 ** attempt)
            except Exception as exc:
                _p(f"  [OA] Attempt {attempt+1} failed: {exc}")
                await asyncio.sleep(2 ** attempt)

        _p("  [OA] All attempts failed")
        return []

    # ── Serper web search ─────────────────────────────────────────────────
    async def search_web(self, query, num=4):
        if not SERPER_API_KEY:
            _p("  [Web] No SERPER_API_KEY — skipping")
            return []
        _p(f"  [Web] Searching: '{query}' num={num}")
        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                res = await client.post(
                    "https://google.serper.dev/search",
                    headers={"X-API-KEY": SERPER_API_KEY},
                    json={"q": query, "num": num},
                )
                res.raise_for_status()
                data = res.json()
            results = [
                {
                    "title": r.get("title", ""),
                    "summary": _clean_text(r.get("snippet", ""), 700),
                    "key_takeaway": _clean_text(r.get("snippet", ""), 450),
                    "abstract": _clean_text(r.get("snippet", ""), 700),
                    "authors": [], "published": "", "citations": 0,
                    "url": r.get("link", ""), "source": "web",
                }
                for r in data.get("organic", [])
            ]
            _p(f"  [Web] Got {len(results)} results in {time.time()-t0:.1f}s")
            return results
        except Exception as exc:
            _p(f"  [Web] FAILED: {exc}")
            return []

    # ── GitHub ────────────────────────────────────────────────────────────
    async def search_github(self, query, limit=3):
        if not GITHUB_TOKEN:
            _p("  [GitHub] No GITHUB_TOKEN — skipping")
            return []
        _p(f"  [GitHub] Searching: '{query}' limit={limit}")
        t0 = time.time()
        try:
            from github import Github, Auth
            gh = Github(auth=Auth.Token(GITHUB_TOKEN))

            def _fetch():
                repos = gh.search_repositories(query=query, sort="stars")
                out = []
                for repo in repos[:limit]:
                    desc = _clean_text(repo.description or "", 700)
                    out.append({
                        "title": repo.full_name, "summary": desc,
                        "key_takeaway": desc, "abstract": desc,
                        "authors": [repo.owner.login] if repo.owner else [],
                        "published": str(repo.created_at.date()) if repo.created_at else "",
                        "citations": repo.stargazers_count,
                        "url": repo.html_url, "source": "github",
                    })
                return out

            results = await asyncio.to_thread(_fetch)
            _p(f"  [GitHub] Got {len(results)} repos in {time.time()-t0:.1f}s")
            return results
        except Exception as exc:
            _p(f"  [GitHub] FAILED: {exc}")
            return []

    def scrape(self, url, max_chars=3000):
        try:
            r = requests.get(url, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")
            return " ".join(p.get_text() for p in soup.find_all("p"))[:max_chars]
        except Exception as exc:
            return f"Scrape error: {exc}"

    async def search_all(self, query):
        _p(f"\n[SearchAll] OpenAlex + Web + GitHub in parallel: '{query}'")
        t0 = time.time()
        s2, web, gh = await asyncio.gather(
            self.search_semantic_scholar(query),
            self.search_web(query),
            self.search_github(query),
        )
        total = len(s2) + len(web) + len(gh)
        _p(f"[SearchAll] Done in {time.time()-t0:.1f}s — Academic:{len(s2)} Web:{len(web)} GitHub:{len(gh)} Total:{total}")
        return s2 + web + gh
