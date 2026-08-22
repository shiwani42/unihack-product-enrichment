import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUIDELINES = ROOT / "guidelines"
DEFAULT_INPUT = GUIDELINES / "Unihack_ Sample Dataset - Input.csv"
DEFAULT_OUTPUT_HEADERS = GUIDELINES / "Unihack_ Expected Output - Delivery Format.csv"
REFERENCE_MPNS = ("PDSH4816AF", "WDTS7024RZ")

ECOMMERCE_BLOCKLIST = (
    "amazon.",
    "ebay.",
    "walmart.",
    "homedepot.",
    "lowes.",
    "target.",
)

REQUEST_TIMEOUT = 20
FETCH_TIMEOUT = 12
FETCH_URL_LIMIT = 3
HTTP_RETRY_ATTEMPTS = int(os.environ.get("UNILOG_HTTP_RETRIES", "3"))
HTTP_RETRY_BASE_DELAY = float(os.environ.get("UNILOG_HTTP_RETRY_DELAY", "0.5"))
RAW_CACHE_MAX_FILES = int(os.environ.get("UNILOG_RAW_CACHE_MAX_FILES", "300"))
RAW_CACHE_TTL_DAYS = int(os.environ.get("UNILOG_RAW_CACHE_TTL_DAYS", "30"))
PDF_MAX_BYTES = 4_000_000
USER_AGENT = "UniHack-Enrichment/1.0 (+https://github.com/shiwani42/unihack-product-enrichment)"

OUTPUT_DIR = Path(os.environ.get("UNILOG_OUTPUT_DIR", str(ROOT / "output")))
CACHE_DIR = ROOT / "data" / "cache"
RAW_CACHE_DIR = ROOT / "data" / "raw"
TAXONOMY_PATH = ROOT / "data" / "taxonomy" / "leaves.json"
CROSSWALK_PATH = ROOT / "data" / "crosswalk" / "mpn_to_unilog.json"
LLM_CACHE_DIR = ROOT / "data" / "llm_cache"

# LLM fallback: opt-in only, cheap model, strict budget (see extract/llm_fallback.py)
LLM_MODEL = os.environ.get("UNILOG_LLM_MODEL", "gpt-4o-mini")
LLM_MAX_DESC_CHARS = int(os.environ.get("UNILOG_LLM_MAX_DESC_CHARS", "100"))
LLM_MAX_OUTPUT_TOKENS = int(os.environ.get("UNILOG_LLM_MAX_OUTPUT_TOKENS", "80"))
LLM_MAX_CALLS_PER_RUN = int(os.environ.get("UNILOG_LLM_MAX_CALLS", "50"))


def is_llm_enabled() -> bool:
    """Explicit opt-in: set UNILOG_LLM_ENABLED=1 and OPENAI_API_KEY."""
    if os.environ.get("UNILOG_LLM_ENABLED", "").lower() not in {"1", "true", "yes"}:
        return False
    return bool(os.environ.get("OPENAI_API_KEY", "").strip())


# Backward compat alias
ENABLE_LLM_FALLBACK = is_llm_enabled()
