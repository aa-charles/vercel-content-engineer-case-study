"""Shared utilities used across agents and prompt_context."""

import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Load .env once at import time. Silent if no .env exists (env vars may be set
# externally via shell, CI, etc.). All three agents import from utils, so this
# runs before any Anthropic() client is constructed.
load_dotenv()

# Cache directory for fetched source pages. Resolved relative to this file's
# location so all callers (agents + prompt_context) see the same path.
RAW_DIR = Path(__file__).parent / "outputs" / "raw"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def slug(url: str) -> str:
    """URL → filesystem-safe slug (max 80 chars). Used for cache filenames."""
    return re.sub(r"[^a-z0-9]+", "-", url.lower()).strip("-")[:80]


def fetch(url: str) -> str:
    """GET a URL and return cleaned text content (script/style/noscript stripped, whitespace normalized)."""
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", text)


def output_path(kind: str) -> Path:
    """
    Return the piece-scoped path for a pipeline output file.

    Reads the comparison id from sources.json (e.g.
    'vercel-workflows-vs-cloudflare-workflows') and constructs:

      outputs/<prefix>_<id>.<ext>

    Valid kinds:
      'extractions'                 → outputs/extractions_<id>.json
      'comparison_matrix'           → outputs/comparison_matrix_<id>.json
      'comparison_brief'            → outputs/comparison_brief_<id>.md
      'agent_draft'                 → outputs/agent_draft_<id>.md
      'agent_draft_revision_notes'  → outputs/agent_draft_revision_notes_<id>.md

    All outputs are piece-scoped so multiple comparison runs can coexist in
    outputs/ without filename collision.
    """
    sources_path = Path(__file__).parent / "sources.json"
    cid = json.loads(sources_path.read_text())["id"]
    filenames = {
        "extractions":                f"extractions_{cid}.json",
        "comparison_matrix":          f"comparison_matrix_{cid}.json",
        "comparison_brief":           f"comparison_brief_{cid}.md",
        "agent_draft":                f"agent_draft_{cid}.md",
        "agent_draft_revision_notes": f"agent_draft_revision_notes_{cid}.md",
    }
    if kind not in filenames:
        raise ValueError(f"Unknown output kind: {kind!r}. Valid: {sorted(filenames)}")
    return Path(__file__).parent / "outputs" / filenames[kind]
