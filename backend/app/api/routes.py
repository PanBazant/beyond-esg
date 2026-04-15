from fastapi import APIRouter, HTTPException, Query

from ..schemas import (
    CatalogResponse,
    DataStatusResponse,
    DataWorklistResponse,
    HealthResponse,
    PortfolioPreviewRequest,
    PortfolioPreviewResponse,
    PortfolioReportResponse,
    ProfileCatalogResponse,
    RawDataImportRequest,
    RawDataImportResponse,
    SavedProfileCatalogResponse,
    SavedProfileDeleteResponse,
    SavedProfileRecord,
    SavedProfileUpsertRequest,
)
from ..services.catalog import build_catalog
from ..services.data_pipeline import build_data_status, build_data_worklist, import_raw_data
from ..services.portfolio import build_portfolio_preview
from ..services.presets import build_profile_catalog
from ..services.reporting import generate_portfolio_report
from ..services.saved_profiles import build_saved_profile_catalog, delete_saved_profile, upsert_saved_profile


router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def healthcheck() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/catalog", response_model=CatalogResponse)
async def catalog() -> CatalogResponse:
    return build_catalog()


@router.get("/data/status", response_model=DataStatusResponse)
async def data_status() -> DataStatusResponse:
    return build_data_status()


@router.get("/data/worklists/{kind}", response_model=DataWorklistResponse)
async def data_worklist(
    kind: str,
    min_posts: int = Query(default=30, ge=0, le=500),
    limit: int = Query(default=100, ge=1, le=1000),
    only_missing: bool = True,
) -> DataWorklistResponse:
    if kind not in {"fundamentals", "technicals"}:
        raise HTTPException(status_code=404, detail="Unknown worklist kind.")
    return build_data_worklist(kind, min_posts=min_posts, limit=limit, only_missing=only_missing)


@router.post("/data/import/{kind}", response_model=RawDataImportResponse)
async def data_import(kind: str, payload: RawDataImportRequest) -> RawDataImportResponse:
    if kind not in {"fundamentals", "technicals"}:
        raise HTTPException(status_code=404, detail="Unknown import kind.")
    return import_raw_data(kind, payload)


@router.get("/profiles", response_model=ProfileCatalogResponse)
async def profiles() -> ProfileCatalogResponse:
    return build_profile_catalog()


@router.get("/profiles/saved", response_model=SavedProfileCatalogResponse)
async def saved_profiles() -> SavedProfileCatalogResponse:
    return build_saved_profile_catalog()


@router.post("/profiles/saved", response_model=SavedProfileRecord)
async def save_profile(payload: SavedProfileUpsertRequest) -> SavedProfileRecord:
    return upsert_saved_profile(payload)


@router.delete("/profiles/saved/{profile_id}", response_model=SavedProfileDeleteResponse)
async def remove_profile(profile_id: str) -> SavedProfileDeleteResponse:
    return delete_saved_profile(profile_id)


@router.post("/portfolio/preview", response_model=PortfolioPreviewResponse)
async def portfolio_preview(payload: PortfolioPreviewRequest) -> PortfolioPreviewResponse:
    return build_portfolio_preview(payload)


@router.post("/portfolio/report", response_model=PortfolioReportResponse)
async def portfolio_report(payload: PortfolioPreviewRequest) -> PortfolioReportResponse:
    return generate_portfolio_report(payload)
