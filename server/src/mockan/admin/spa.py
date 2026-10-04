"""Serve the built Panel (G-11, OQ-03): static files plus an `index.html` router fallback."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response

# These prefixes belong to the Admin API; an unknown path under them is a 404, never the Panel.
_API_PREFIXES = frozenset({"api", "hubs"})


def normalise_base_path(base_path: str) -> str:
    """`"/"` or `"/_mockan/admin"`: leading slash, no trailing slash (except the root)."""
    return "/" + base_path.strip().strip("/") if base_path.strip("/") else "/"


def mount_panel(app: FastAPI, static_dir: Path, base_path: str) -> None:
    """Add the Panel routes. Call it last: they are catch-alls under `base_path`."""
    root = static_dir.resolve()
    index = root / "index.html"
    prefix = "" if normalise_base_path(base_path) == "/" else normalise_base_path(base_path)

    def serve(path: str) -> Response:
        if not prefix and path.split("/", 1)[0] in _API_PREFIXES:
            raise HTTPException(404)
        if path:
            try:
                candidate = (root / path).resolve()
            except OSError, ValueError:  # e.g. a NUL byte
                raise HTTPException(404) from None
            if candidate.is_relative_to(root) and candidate.is_file():
                return FileResponse(candidate)
            if "." in path.rsplit("/", 1)[-1]:  # a missing asset is a 404, not the app shell
                raise HTTPException(404)
        return FileResponse(index, headers={"cache-control": "no-cache"})

    @app.get(prefix + "/{path:path}", include_in_schema=False)
    async def panel(path: str) -> Response:
        return serve(path)

    if prefix:  # `/_mockan/admin` without the trailing slash

        @app.get(prefix, include_in_schema=False)
        async def panel_root() -> Response:
            return serve("")
