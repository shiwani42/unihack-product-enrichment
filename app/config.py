import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUIDELINES = ROOT / "guidelines"
DEFAULT_INPUT = GUIDELINES / "Unihack_ Sample Dataset - Input.csv"
DEFAULT_OUTPUT_HEADERS = GUIDELINES / "Unihack_ Expected Output - Delivery Format.csv"
REFERENCE_MPNS = ("PDSH4816AF", "WDTS7024RZ")

# Shopping / e-commerce hosts the challenge forbids. Matched as hostname
# labels (amazon.com, amazon.co.uk, amzn.to) so manufacturer CDNs on
# amazonaws.com are not treated as storefronts.
ECOMMERCE_HOST_LABELS = frozenset(
    {
        "amazon",
        "amzn",
        "ebay",
        "ebayimg",
        "walmart",
        "homedepot",
        "lowes",
        "target",
        "wayfair",
        "overstock",
        "alibaba",
        "aliexpress",
        "bestbuy",
        "costco",
        "newegg",
        "etsy",
        "rakuten",
        "wish",
        "sears",
        "macys",
        "kohls",
        "temu",
        "shein",
        "flipkart",
        "mercadolibre",
        "mercadolivre",
        "ajmadison",
        "chewy",
        "instacart",
        "offerup",
        "craigslist",
    }
)
ECOMMERCE_PATH_MARKERS = (
    "google.com/shopping",
    "shopping.google",
    "facebook.com/marketplace",
    "fb.com/marketplace",
)
# Shopping / e-commerce only. Challenge forbids Amazon/eBay and the like.
# Distributors are a later fallback, not a blocklist.
DISTRIBUTOR_HOST_LABELS = frozenset(
    {
        "grainger",
        "mscdirect",
        "zoro",
        "graybar",
        "rexelusa",
        "rexel",
        "ferguson",
        "supplyhouse",
        "acwholesalers",
        "reliableparts",
        "mcmaster",
        "fastenal",
        "webstaurantstore",
    }
)
# Backward-compatible substring list used by older shopping checks.
ECOMMERCE_BLOCKLIST = (
    tuple(f"{label}." for label in sorted(ECOMMERCE_HOST_LABELS))
    + ECOMMERCE_PATH_MARKERS
)

REQUEST_TIMEOUT = 20
FETCH_TIMEOUT = int(os.environ.get("UNILOG_FETCH_TIMEOUT", "20"))
FETCH_CONNECT_TIMEOUT = float(os.environ.get("UNILOG_FETCH_CONNECT_TIMEOUT", "2"))
FETCH_URL_LIMIT = int(os.environ.get("UNILOG_FETCH_URL_LIMIT", "8"))
FOLLOW_URL_LIMIT = int(os.environ.get("UNILOG_FOLLOW_URL_LIMIT", "6"))
SECONDARY_URL_LIMIT = int(os.environ.get("UNILOG_SECONDARY_URL_LIMIT", "10"))
THIRD_PARTY_URL_LIMIT = int(os.environ.get("UNILOG_THIRD_PARTY_URL_LIMIT", "6"))
DISTRIBUTOR_URL_LIMIT = int(os.environ.get("UNILOG_DISTRIBUTOR_URL_LIMIT", "6"))
SEARCH_URL_LIMIT = int(os.environ.get("UNILOG_SEARCH_URL_LIMIT", "8"))
PDF_URL_LIMIT = int(os.environ.get("UNILOG_PDF_URL_LIMIT", "8"))
FETCH_PDFS = os.environ.get("UNILOG_FETCH_PDFS", "1").strip().lower() not in {"0", "false", "no"}
WEB_SEARCH_ENABLED = os.environ.get("UNILOG_WEB_SEARCH", "1").strip().lower() not in {"0", "false", "no"}
HTTP_RETRY_ATTEMPTS = int(os.environ.get("UNILOG_HTTP_RETRIES", "3"))
HTTP_RETRY_BASE_DELAY = float(os.environ.get("UNILOG_HTTP_RETRY_DELAY", "0.5"))
RAW_CACHE_MAX_FILES = int(os.environ.get("UNILOG_RAW_CACHE_MAX_FILES", "300"))
RAW_CACHE_TTL_DAYS = int(os.environ.get("UNILOG_RAW_CACHE_TTL_DAYS", "30"))
EVIDENCE_CACHE_TTL_DAYS = int(os.environ.get("UNILOG_EVIDENCE_CACHE_TTL_DAYS", str(RAW_CACHE_TTL_DAYS)))
PDF_MAX_BYTES = 4_000_000
USER_AGENT = "UniHack-Enrichment/1.0 (+https://github.com/shiwani42/unihack-product-enrichment)"

def _runtime_dir(env_name: str, default: Path, vercel_name: str) -> Path:
    override = os.environ.get(env_name, "").strip()
    if override:
        return Path(override)
    if os.environ.get("VERCEL"):
        return Path("/tmp/unilog") / vercel_name
    return default


OUTPUT_DIR = Path(os.environ.get("UNILOG_OUTPUT_DIR", str(ROOT / "output")))
CACHE_DIR = ROOT / "data" / "cache"
RAW_CACHE_DIR = _runtime_dir("UNILOG_RAW_CACHE_DIR", ROOT / "data" / "raw", "raw")
EVIDENCE_CACHE_DIR = _runtime_dir(
    "UNILOG_EVIDENCE_CACHE_DIR", ROOT / "data" / "evidence_cache", "evidence"
)
TAXONOMY_PATH = ROOT / "data" / "taxonomy" / "leaves.json"
CROSSWALK_PATH = ROOT / "data" / "crosswalk" / "mpn_to_unilog.json"
LLM_CACHE_DIR = _runtime_dir("UNILOG_LLM_CACHE_DIR", ROOT / "data" / "llm_cache", "llm")

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
