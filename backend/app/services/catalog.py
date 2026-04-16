from ..schemas import (
    AxisClusterDefinition,
    CatalogItem,
    CatalogResponse,
    CommentEsgAxisDefinition,
    CommentEsgFamilyDefinition,
    InstrumentUniverseDefinition,
    MetricAvailability,
)
from .datasets import (
    load_axis_clusters_catalog,
    load_category_catalog,
    load_comment_esg_axes_catalog,
    load_comment_esg_family_catalog,
    load_company_records,
    load_instrument_universe_catalog,
    metric_availability,
)


def build_catalog() -> CatalogResponse:
    companies = load_company_records()
    categories = [CatalogItem(slug=item["slug"], name=item["name"]) for item in load_category_catalog()]
    custom_esg_axes = [CommentEsgAxisDefinition(**item) for item in load_comment_esg_axes_catalog()]
    custom_esg_families = [CommentEsgFamilyDefinition(**item) for item in load_comment_esg_family_catalog()]
    axis_clusters = [AxisClusterDefinition(**item) for item in load_axis_clusters_catalog()]
    instrument_universes = [InstrumentUniverseDefinition(**item) for item in load_instrument_universe_catalog()]

    return CatalogResponse(
        categories=categories,
        categories_count=len(categories),
        companies_count=len(companies),
        metrics=MetricAvailability(**metric_availability(companies)),
        custom_esg_axes=custom_esg_axes,
        custom_esg_families=custom_esg_families,
        axis_clusters=axis_clusters,
        instrument_universes=instrument_universes,
    )
