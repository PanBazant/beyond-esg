from pathlib import Path

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import router


ROOT_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIST_DIR = ROOT_DIR / "frontend" / "dist"
FRONTEND_ASSETS_DIR = FRONTEND_DIST_DIR / "assets"
FRONTEND_INDEX_PATH = FRONTEND_DIST_DIR / "index.html"


app = FastAPI(
    title="Value Selection API",
    version="0.1.0",
    summary="API wspierajace selekcje spolek i budowe portfela ETF-opodobnego.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


if FRONTEND_ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_ASSETS_DIR)), name="frontend-assets")


def _frontend_file_or_index(path: str) -> FileResponse:
    candidate = (FRONTEND_DIST_DIR / path).resolve()
    try:
        candidate.relative_to(FRONTEND_DIST_DIR.resolve())
    except ValueError:
        return FileResponse(FRONTEND_INDEX_PATH)

    if candidate.exists() and candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(FRONTEND_INDEX_PATH)


if FRONTEND_INDEX_PATH.exists():
    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    async def frontend_index() -> FileResponse:
        return FileResponse(FRONTEND_INDEX_PATH)


    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def frontend_fallback(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        return _frontend_file_or_index(full_path)
