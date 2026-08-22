from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUIDELINES = ROOT / "guidelines"
DEFAULT_INPUT = GUIDELINES / "Unihack_ Sample Dataset - Input.csv"
DEFAULT_OUTPUT_HEADERS = GUIDELINES / "Unihack_ Expected Output - Delivery Format.csv"
GOLDEN_MPNS = ("PDSH4816AF", "WDTS7024RZ")

ECOMMERCE_BLOCKLIST = (
    "amazon.",
    "ebay.",
    "walmart.",
    "homedepot.",
    "lowes.",
    "target.",
)

REQUEST_TIMEOUT = 20
PDF_MAX_BYTES = 4_000_000
USER_AGENT = "UniHack-Enrichment/1.0 (+https://github.com/shiwani42/unihack-product-enrichment)"

OUTPUT_DIR = ROOT / "output"
CACHE_DIR = ROOT / "data" / "cache"
