"""Shared mobile description padding per style guidelines (60-80 chars)."""


def pad_mobile(text: str, mpn: str, brand: str = "", manufacturer: str = "", minimum: int = 60) -> str:
    parts = [part.strip() for part in text.split(",") if part.strip()]
    candidate = ", ".join(parts)[:80]
    if len(candidate) >= minimum:
        return candidate

    fillers = [manufacturer, brand.replace("®", "").replace("™", ""), mpn, "Industrial Product"]
    for filler in fillers:
        if filler and filler not in candidate:
            candidate = f"{candidate}, {filler}".strip(", ")
        if len(candidate) >= minimum:
            break

    while len(candidate) < minimum and len(candidate) < 78:
        candidate = f"{candidate}, {mpn}"
        if len(candidate) >= minimum:
            break
        candidate = f"{candidate}, Spec"

    return candidate[:80]
