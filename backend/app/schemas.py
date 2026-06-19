from typing import Any, Literal

from pydantic import BaseModel, Field


CustomEsgMode = Literal["prefer_low", "neutral", "prefer_high"]
PreferenceMode = Literal["prefer_low", "neutral", "prefer_high"]
MarketCapMode = Literal["prefer_large", "neutral", "prefer_small"]
WeightingMode = Literal["equal", "score_weighted"]
DataPipelineKind = Literal["fundamentals", "technicals"]
InstrumentUniverseClass = Literal["common_equity", "reit", "fund_etf_trust", "ambiguous", "crypto_coin"]


class HealthResponse(BaseModel):
    status: str


class CatalogItem(BaseModel):
    slug: str
    name: str


class MetricAvailability(BaseModel):
    categories: bool = True
    market_cap: bool = True
    posts_count: bool = True
    custom_esg: bool = False
    profitability: bool = False
    technicals: bool = False
    axiological: bool = False


class CommentEsgAxisDefinition(BaseModel):
    axis_id: int
    label: str
    family_id: str | None = None
    family_label: str | None = None
    summary: str | None = None
    keywords: list[str] = Field(default_factory=list)
    topic_labels: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    topic_count: int = 0
    corpus_weight: float = 0.0
    average_sentiment: float = 0.0
    cluster_id: int | None = None
    cluster_label: str | None = None


class AxisClusterDefinition(BaseModel):
    cluster_id: int
    cluster_label: str
    axis_count: int


class DimensionFilters(BaseModel):
    perception_min: float | None = Field(default=None, ge=0.0, le=1.0)
    esg_max: float | None = Field(default=None, ge=0.0)
    profitability_min: float | None = Field(default=None, ge=0.0, le=100.0)
    technical_min: float | None = Field(default=None, ge=0.0, le=100.0)
    include_missing_perception: bool = True
    include_missing_esg: bool = True
    include_missing_profitability: bool = True
    include_missing_technical: bool = True


class CommentEsgFamilyDefinition(BaseModel):
    family_id: str
    label: str
    summary: str | None = None
    dominant_axis_code: str | None = None
    dominant_axis_label: str | None = None
    keywords: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    topic_labels: list[str] = Field(default_factory=list)
    member_axis_ids: list[int] = Field(default_factory=list)
    member_dimensions_count: int = 0
    esg_relevance: float = 0.0


class InstrumentUniverseDefinition(BaseModel):
    id: InstrumentUniverseClass
    label: str
    description: str
    companies_count: int = 0
    default_selected: bool = False


class CatalogResponse(BaseModel):
    categories: list[CatalogItem]
    categories_count: int
    companies_count: int
    metrics: MetricAvailability
    custom_esg_axes: list[CommentEsgAxisDefinition] = Field(default_factory=list)
    custom_esg_families: list[CommentEsgFamilyDefinition] = Field(default_factory=list)
    axis_clusters: list[AxisClusterDefinition] = Field(default_factory=list)
    instrument_universes: list[InstrumentUniverseDefinition] = Field(default_factory=list)


class ScoreWeights(BaseModel):
    base_quality: float = Field(default=0.25, ge=0.0, le=1.0)
    esg_alignment: float = Field(default=0.20, ge=0.0, le=1.0)
    category_match: float = Field(default=0.15, ge=0.0, le=1.0)
    profitability_alignment: float = Field(default=0.20, ge=0.0, le=1.0)
    technical_alignment: float = Field(default=0.10, ge=0.0, le=1.0)
    market_cap_alignment: float = Field(default=0.10, ge=0.0, le=1.0)


class AxisPreference(BaseModel):
    axis_id: int = Field(ge=0)
    axis_label: str | None = None
    mode: PreferenceMode = "neutral"
    importance: float = Field(default=0.5, ge=0.0, le=1.0)


class ProfilePreset(BaseModel):
    id: str
    name: str
    description: str
    allowed_instrument_universes: list[InstrumentUniverseClass] = Field(
        default_factory=lambda: ["common_equity"]
    )
    custom_esg_mode: CustomEsgMode
    profitability_mode: PreferenceMode
    technical_mode: PreferenceMode
    market_cap_mode: MarketCapMode
    weighting_mode: WeightingMode
    score_weights: ScoreWeights
    axis_preferences: list[AxisPreference] = Field(default_factory=list)


class ProfileCatalogResponse(BaseModel):
    profiles: list[ProfilePreset]


class PortfolioPreviewRequest(BaseModel):
    profile_name: str = Field(default="custom-profile", min_length=1, max_length=100)
    categories: list[str] = Field(default_factory=list)
    allowed_instrument_universes: list[InstrumentUniverseClass] = Field(
        default_factory=lambda: ["common_equity"]
    )
    custom_esg_mode: CustomEsgMode = "neutral"
    profitability_mode: PreferenceMode = "prefer_high"
    technical_mode: PreferenceMode = "prefer_high"
    market_cap_mode: MarketCapMode = "neutral"
    weighting_mode: WeightingMode = "equal"
    axis_preferences: list[AxisPreference] = Field(default_factory=list)
    max_holding_weight: float = Field(default=0.25, ge=0.05, le=1.0)
    max_companies_per_category: int = Field(default=2, ge=0, le=20)
    min_distinct_categories: int = Field(default=3, ge=1, le=20)
    strict_category_limit: bool = False
    score_weights: ScoreWeights = Field(default_factory=ScoreWeights)
    min_posts: int = Field(default=4, ge=0, le=500)
    portfolio_size: int = Field(default=10, ge=1, le=50)
    dimension_filters: DimensionFilters = Field(default_factory=DimensionFilters)


class SavedProfileUpsertRequest(PortfolioPreviewRequest):
    profile_id: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)


class SavedProfileRecord(PortfolioPreviewRequest):
    profile_id: str
    description: str | None = None
    created_at: str
    updated_at: str


class SavedProfileCatalogResponse(BaseModel):
    saved_profiles: list[SavedProfileRecord]


class SavedProfileDeleteResponse(BaseModel):
    profile_id: str
    deleted: bool


class CompanyExplanation(BaseModel):
    title: str
    detail: str


class CustomEsgAxisPreview(BaseModel):
    axis_id: int
    label: str
    family_label: str | None = None
    summary: str | None = None
    keywords: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    score: float | None = None
    exposure: float | None = None
    confidence: float | None = None


class CustomEsgFamilyPreview(BaseModel):
    family_id: str
    label: str
    summary: str | None = None
    dominant_axis_code: str | None = None
    dominant_axis_label: str | None = None
    keywords: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    score: float | None = None
    exposure: float | None = None
    confidence: float | None = None
    esg_relevance: float | None = None


class ScoreBreakdown(BaseModel):
    base_quality: float
    esg_alignment: float
    category_match: float
    profitability_alignment: float
    technical_alignment: float
    market_cap_alignment: float


class CompanyPreview(BaseModel):
    symbol: str
    company_name: str
    category: str
    industry: str | None = None
    instrument_universe: InstrumentUniverseClass
    instrument_universe_label: str
    instrument_universe_reason: str | None = None
    posts_count: int
    market_cap_label: str | None = None
    market_cap_numeric: float | None = None
    rank_in_category: int | None = None
    custom_esg_proxy_score: float | None = None
    custom_esg_confidence: float | None = None
    custom_esg_metric_version: str | None = None
    real_esg_total_score: float | None = None
    real_esg_environment_score: float | None = None
    real_esg_social_score: float | None = None
    real_esg_governance_score: float | None = None
    real_esg_source: str | None = None
    custom_esg_axes: list[CustomEsgAxisPreview] = Field(default_factory=list)
    custom_esg_families: list[CustomEsgFamilyPreview] = Field(default_factory=list)
    profitability_score: float | None = None
    technical_score: float | None = None
    avg_sentiment: float | None = None
    coverage_score: float | None = None
    perception_score: float | None = None
    axiological_coverage: float | None = None
    axiological_confidence: float | None = None
    axiological_inter_method_agreement: float | None = None
    axiological_frames: list[dict] = Field(default_factory=list)
    axiological_has_signal: bool = False
    axiological_profile_null: bool = True
    axiological_low_signal: bool = False
    selection_score: float
    score_breakdown: ScoreBreakdown
    explanations: list[CompanyExplanation]


class PortfolioHolding(BaseModel):
    symbol: str
    company_name: str
    weight: float
    selection_score: float
    category: str
    instrument_universe: InstrumentUniverseClass
    instrument_universe_label: str


class CategoryAllocation(BaseModel):
    category: str
    holdings_count: int
    total_weight: float
    average_selection_score: float


class PortfolioSummary(BaseModel):
    selected_companies: int
    distinct_categories: int
    average_custom_esg: float | None = None
    average_profitability: float | None = None
    average_technical: float | None = None
    average_sentiment: float | None = None
    average_posts_count: float | None = None
    average_axiological_coverage: float | None = None
    concentration_hhi: float
    max_holding_weight: float
    top_category: str | None = None


class BenchmarkPortfolio(BaseModel):
    label: str
    custom_esg_mode: CustomEsgMode
    summary: PortfolioSummary
    category_allocations: list[CategoryAllocation]
    holdings: list[PortfolioHolding]


class PortfolioComparisonMetrics(BaseModel):
    overlap_count: int
    overlap_ratio: float
    custom_esg_delta: float | None = None
    profitability_delta: float | None = None
    technical_delta: float | None = None
    sentiment_delta: float | None = None
    distinct_categories_delta: int


class PortfolioComparison(BaseModel):
    benchmark: BenchmarkPortfolio
    metrics: PortfolioComparisonMetrics


class PortfolioPreviewResponse(BaseModel):
    profile_name: str
    matched_companies: int
    metrics: MetricAvailability
    score_weights: ScoreWeights
    weighting_mode: WeightingMode
    warnings: list[str]
    summary: PortfolioSummary
    category_allocations: list[CategoryAllocation]
    companies: list[CompanyPreview]
    holdings: list[PortfolioHolding]
    comparison: PortfolioComparison | None = None


class PortfolioReportResponse(BaseModel):
    profile_name: str
    generated_at: str
    file_slug: str
    markdown_file: str
    json_file: str
    markdown: str
    preview: PortfolioPreviewResponse


class DataPipelineStatus(BaseModel):
    kind: DataPipelineKind
    template_exists: bool
    normalized_input_exists: bool
    normalized_rows: int
    feature_rows: int
    report_exists: bool
    summary_exists: bool
    latest_source: str | None = None
    latest_as_of_date: str | None = None
    report_path: str | None = None
    summary_path: str | None = None


class DataStatusResponse(BaseModel):
    master_dataset_exists: bool
    master_rows: int
    raw_upload_dir: str
    raw_upload_files: list[str] = Field(default_factory=list)
    fundamentals: DataPipelineStatus
    technicals: DataPipelineStatus


class DataWorklistEntry(BaseModel):
    symbol: str
    company_name: str
    category: str
    industry: str | None = None
    instrument_universe: InstrumentUniverseClass
    instrument_universe_label: str
    posts_count: int
    custom_esg_proxy_score: float | None = None
    market_cap_label: str | None = None
    rank_in_category: int | None = None


class DataWorklistResponse(BaseModel):
    kind: DataPipelineKind
    min_posts: int
    limit: int
    only_missing: bool
    output_file: str | None = None
    rows: list[DataWorklistEntry] = Field(default_factory=list)


class RawDataImportRequest(BaseModel):
    file_name: str = Field(min_length=1, max_length=200)
    file_content_base64: str = Field(min_length=1)
    source_name: str | None = Field(default=None, max_length=100)
    as_of_date: str | None = Field(default=None, max_length=20)
    replace: bool = False


class RawDataImportResponse(BaseModel):
    kind: DataPipelineKind
    saved_file: str
    import_report: dict[str, Any] = Field(default_factory=dict)
    feature_summary: dict[str, Any] = Field(default_factory=dict)
    master_summary: dict[str, Any] = Field(default_factory=dict)
    status: DataPipelineStatus
