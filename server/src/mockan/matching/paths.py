"""Path normalisation for the compilers. Paths are decoded, after the DeveloperSlug."""


def normalise(path: str) -> str:
    """Strip one trailing `/` unless the path is the root."""
    if len(path) > 1 and path.endswith("/"):
        return path[:-1]
    return path


def segments(path: str) -> list[str] | None:
    """Split a normalised path into segments. `/` has none. `None` when the path is not absolute."""
    if not path.startswith("/"):
        return None
    if path == "/":
        return []
    return path[1:].split("/")
