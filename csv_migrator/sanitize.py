import re

_INVALID_CHARS = re.compile(r"[ \-.()\[\]&]")
_REPEATED_UNDERSCORE = re.compile(r"_+")


def sanitize_identifier(name: str) -> str:
    cleaned = _INVALID_CHARS.sub("_", name)
    cleaned = _REPEATED_UNDERSCORE.sub("_", cleaned)
    cleaned = cleaned.strip("_") or "Column"
    if cleaned[0].isdigit():
        cleaned = "Table_" + cleaned
    return cleaned


def table_name_from_filename(filename: str) -> str:
    stem = filename
    if stem.lower().endswith(".csv"):
        stem = stem[:-4]
    return sanitize_identifier(stem)


def dedupe_headers(headers: list[str]) -> list[str]:
    sanitized = [sanitize_identifier(h) for h in headers]
    seen: dict[str, int] = {}
    result = []
    for name in sanitized:
        if name not in seen:
            seen[name] = 0
            result.append(name)
        else:
            seen[name] += 1
            result.append(f"{name}_{seen[name]}")
    return result
