import re

MARKER_RE = re.compile(r"\[(\d+)\]")


def parse_markers(text: str) -> list[int]:
    seen: set[int] = set()
    ordered: list[int] = []
    for match in MARKER_RE.finditer(text):
        value = int(match.group(1))
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered
