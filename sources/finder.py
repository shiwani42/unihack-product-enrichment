import re

from app.config import ECOMMERCE_BLOCKLIST


def is_blocked_url(url: str) -> bool:
    lowered = url.lower()
    return any(block in lowered for block in ECOMMERCE_BLOCKLIST)


def candidate_mfr_urls(mpn: str, domains: list[str]) -> list[str]:
    urls: list[str] = []
    for domain in domains:
        base = domain if domain.startswith("http") else f"https://www.{domain}"
        if "frigidaire" in domain:
            urls.append(f"https://support.frigidaire.com/Owner-Center/Product-Support/{mpn}")
            urls.append(f"https://www.frigidaire.com/en/p/owner-center/product-support/{mpn}")
        elif "whirlpool" in domain or "kitchenaid" in domain:
            search_mpn = mpn[:-1] if mpn.endswith("Z") and len(mpn) > 4 else mpn
            urls.append(f"https://learnwhirlpool.com/smartsearchresults?searchtext={search_mpn}")
            urls.append(f"https://www.kitchenaid.com/search.html?searchTerm={mpn}")
        elif "geappliances" in domain or "cafeappliances" in domain:
            urls.append(f"https://www.geappliances.com/appliance/{mpn}")
            urls.append(f"https://www.cafeappliances.com/appliance/{mpn}")
        elif "lg.com" in domain:
            urls.append(f"https://www.lg.com/us/search?search={mpn}")
        elif "hunterfan" in domain:
            urls.append(f"https://www.hunterfan.com/search?q={mpn}")
        elif "kichler" in domain:
            urls.append(f"https://www.kichler.com/search?q={mpn}")
        elif "diablotools" in domain:
            urls.append(f"https://www.diablotools.com/search?q={mpn}")
        elif "milwaukeetool" in domain:
            urls.append(f"https://www.milwaukeetool.com/Search/{mpn}")
        elif "3m.com" in domain:
            urls.append(f"https://www.3m.com/3M/en_US/search/?q={mpn}")
        else:
            urls.append(f"{base}/search?q={mpn}")
    return urls


def best_mfr_url(mpn: str, domains: list[str]) -> str:
    candidates = [url for url in candidate_mfr_urls(mpn, domains) if not is_blocked_url(url)]
    return candidates[0] if candidates else ""
