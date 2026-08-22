PLACEHOLDER_BRANDS = {
    "-- unbranded --",
    "-- no unilog brand --",
    "-- no dib brand --",
    "-- no dib brand--",
}


def is_placeholder(value: str | None) -> bool:
    if not value:
        return True
    return value.strip().lower() in PLACEHOLDER_BRANDS


def clean_brand(value: str | None) -> str:
    if is_placeholder(value):
        return ""
    return (value or "").strip()
