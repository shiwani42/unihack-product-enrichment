import re

from app.config import ECOMMERCE_BLOCKLIST


def is_blocked_url(url: str) -> bool:
    lowered = url.lower()
    return any(block in lowered for block in ECOMMERCE_BLOCKLIST)


def candidate_mfr_urls(mpn: str, domains: list[str]) -> list[str]:
    urls: list[str] = []
    for domain in domains:
        if "frigidaire" in domain:
            urls.append(f"https://support.frigidaire.com/Owner-Center/Product-Support/{mpn}")
            urls.append(f"https://www.frigidaire.com/en/p/owner-center/product-support/{mpn}")
        elif "whirlpool" in domain:
            search_mpn = mpn[:-1] if mpn.endswith("Z") and len(mpn) > 4 else mpn
            urls.append(f"https://learnwhirlpool.com/smartsearchresults?searchtext={search_mpn}")
            urls.append(f"https://learnwhirlpool.com/smartsearchresults?searchtext={mpn}")
            urls.append(f"https://www.whirlpool.com/kitchen/dishwashers/p.{mpn.lower()}.html")
        elif "geappliances" in domain:
            urls.append(f"https://www.geappliances.com/appliance/{mpn}")
    return urls


def search_query(mpn: str, brand_key: str, domains: list[str]) -> str:
    domain_clause = f"site:{domains[0]}" if domains else ""
    brand_clause = brand_key or ""
    return " ".join(part for part in [mpn, brand_clause, "specifications", domain_clause] if part)
