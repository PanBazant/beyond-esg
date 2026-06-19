import { startTransition, useEffect, useRef, useState } from "react";
import CompanyChart from "./CompanyChart.jsx";
import WizardBar from "./WizardBar.jsx";
import {
  buildPortfolioPreview,
  deleteProfile,
  exportPortfolioReport,
  fetchCatalog,
  fetchDataStatus,
  fetchDataWorklist,
  fetchProfiles,
  fetchSavedProfiles,
  importRawData,
  saveProfile,
} from "./api";

const initialWeights = {
  base_quality: 0.25,
  esg_alignment: 0.2,
  category_match: 0.15,
  profitability_alignment: 0.2,
  technical_alignment: 0.1,
  market_cap_alignment: 0.1,
};

const mosaicColors = [
  "#f5d5d0", "#d5e5f5", "#f5ecd0", "#d5f0e0",
  "#ecd5f5", "#f5f0d0", "#d5eaf5", "#f5d5e8",
  "#d5f5e8", "#f5e0d5", "#e0d5f5", "#f0f5d5",
  "#d5f5f0", "#f5d5d8", "#d8f5d5", "#f5f0e8",
];

function buildEmptyProfile(axisDefinitions = []) {
  return {
    profile_name: "custom-profile",
    categories: [],
    allowed_instrument_universes: ["common_equity"],
    custom_esg_mode: "neutral",
    profitability_mode: "neutral",
    technical_mode: "neutral",
    market_cap_mode: "neutral",
    weighting_mode: "score_weighted",
    axis_preferences: synchronizeAxisPreferences(axisDefinitions, []),
    max_holding_weight: 0.25,
    max_companies_per_category: 2,
    min_distinct_categories: 3,
    strict_category_limit: false,
    score_weights: initialWeights,
    min_posts: 4,
    portfolio_size: 10,
  };
}

const initialForm = buildEmptyProfile();

const presetGlossary = {
  anti_esg_contrarian: {
    title: "Mniej oczywiste i bardziej kontrowersyjne spółki",
    description:
      "Ten styl szuka spółek, które nie wyglądają jak klasyczny portfel ESG, ale nadal mają sensowną skalę i wyraźny sygnał z komentarzy inwestorów.",
  },
  balanced_signal: {
    title: "Zrównoważony sygnał",
    description:
      "To najbardziej neutralny styl startowy. Szuka kompromisu między jakością spółki, komentarzowym ESG i dopasowaniem do wybranych kategorii.",
  },
  classic_esg_defensive: {
    title: "Bardziej klasyczny i defensywny",
    description:
      "Ten styl bardziej premiuje spółki wyglądające bezpiecznie i zgodnie z dominującym ESG-like profilem niż profile kontrariańskie.",
  },
};

const weightingModeLabels = {
  equal: "równy udział każdej spółki",
  score_weighted: "większa waga dla wyżej ocenionych spółek",
};

function weightPercent(value) {
  return `${Math.round((value ?? 0) * 100)}%`;
}

function synchronizeAxisPreferences(axisDefinitions, currentPreferences = []) {
  const existingById = new Map(
    (currentPreferences ?? []).map((preference) => [
      preference.axis_id,
      {
        axis_id: preference.axis_id,
        axis_label: preference.axis_label,
        mode: preference.mode ?? "neutral",
        importance: preference.importance ?? 0.5,
      },
    ]),
  );

  return (axisDefinitions ?? []).map((axis) => {
    const existing = existingById.get(axis.axis_id);
    return {
      axis_id: axis.axis_id,
      axis_label: axis.label,
      mode: existing?.mode ?? "neutral",
      importance: existing?.importance ?? 0.5,
    };
  });
}

function getPresetCopy(profile) {
  if (!profile) {
    return null;
  }

  return presetGlossary[profile.id] ?? {
    title: profile.name,
    description: profile.description ?? "",
  };
}


export default function App() {
  const [catalog, setCatalog] = useState({
    categories: [],
    categories_count: 0,
    companies_count: 0,
    metrics: null,
    custom_esg_axes: [],
    custom_esg_families: [],
    axis_clusters: [],
    instrument_universes: [],
  });
  const [dataStatus, setDataStatus] = useState(null);
  const [fundamentalsWorklist, setFundamentalsWorklist] = useState([]);
  const [technicalsWorklist, setTechnicalsWorklist] = useState([]);
  const [profiles, setProfiles] = useState([]);
  const [savedProfiles, setSavedProfiles] = useState([]);
  const [selectedPresetId, setSelectedPresetId] = useState("");
  const [selectedSavedProfileId, setSelectedSavedProfileId] = useState("");
  const [form, setForm] = useState(initialForm);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [reporting, setReporting] = useState(false);
  const [savingProfile, setSavingProfile] = useState(false);
  const [deletingProfile, setDeletingProfile] = useState(false);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [dataLoading, setDataLoading] = useState(true);
  const [error, setError] = useState("");
  const [reportStatus, setReportStatus] = useState("");
  const [profileStatus, setProfileStatus] = useState("");
  const [expandedSymbol, setExpandedSymbol] = useState(null);
  const [step, setStep] = useState(1);
  // maxStep tracks the furthest step unlocked (step 4 only after first generation)
  const [maxStep, setMaxStep] = useState(3);
  const [dataStatusMessage, setDataStatusMessage] = useState("");
  const [profileDescription, setProfileDescription] = useState("");
  const [fundamentalsSourceName, setFundamentalsSourceName] = useState("");
  const [fundamentalsAsOfDate, setFundamentalsAsOfDate] = useState("");
  const [fundamentalsReplace, setFundamentalsReplace] = useState(false);
  const [fundamentalsFile, setFundamentalsFile] = useState(null);
  const [fundamentalsUploading, setFundamentalsUploading] = useState(false);
  const [technicalsSourceName, setTechnicalsSourceName] = useState("");
  const [technicalsAsOfDate, setTechnicalsAsOfDate] = useState("");
  const [technicalsReplace, setTechnicalsReplace] = useState(false);
  const [technicalsFile, setTechnicalsFile] = useState(null);
  const [technicalsUploading, setTechnicalsUploading] = useState(false);
  const [categoryQuery, setCategoryQuery] = useState("");
  const [axisQuery, setAxisQuery] = useState("");
  const [showAllAxes, setShowAllAxes] = useState(false);
  const [axisViewMode, setAxisViewMode] = useState("list"); // "list" | "groups"
  const [dimensionFilters, setDimensionFilters] = useState({
    perception_min: "",
    esg_max: "",
    profitability_min: "",
    technical_min: "",
    include_missing_perception: true,
    include_missing_esg: true,
    include_missing_profitability: true,
    include_missing_technical: true,
  });

  function applyPreset(profile, axisDefinitions = catalog.custom_esg_axes, { keepProfileName = false } = {}) {
    if (!profile) return;

    setSelectedPresetId(profile.id);
    setSelectedSavedProfileId("");
    setProfileDescription(profile.description ?? "");
    setForm((current) => ({
      ...current,
      profile_name: keepProfileName ? current.profile_name : profile.id,
      allowed_instrument_universes: [...(profile.allowed_instrument_universes?.length ? profile.allowed_instrument_universes : current.allowed_instrument_universes)],
      custom_esg_mode: profile.custom_esg_mode,
      profitability_mode: profile.profitability_mode,
      technical_mode: profile.technical_mode,
      market_cap_mode: profile.market_cap_mode,
      weighting_mode: profile.weighting_mode,
      axis_preferences: synchronizeAxisPreferences(axisDefinitions, profile.axis_preferences?.length ? profile.axis_preferences : current.axis_preferences),
      score_weights: { ...profile.score_weights },
    }));
  }

  function applySavedProfile(profile, axisDefinitions = catalog.custom_esg_axes, { keepProfileName = false } = {}) {
    if (!profile) return;

    setSelectedSavedProfileId(profile.profile_id);
    setSelectedPresetId("");
    setProfileDescription(profile.description ?? "");
    setForm((current) => ({
      ...current,
      profile_name: keepProfileName ? current.profile_name : profile.profile_name,
      categories: [...profile.categories],
      allowed_instrument_universes: [...(profile.allowed_instrument_universes?.length ? profile.allowed_instrument_universes : current.allowed_instrument_universes)],
      custom_esg_mode: profile.custom_esg_mode,
      profitability_mode: profile.profitability_mode,
      technical_mode: profile.technical_mode,
      market_cap_mode: profile.market_cap_mode,
      weighting_mode: profile.weighting_mode,
      axis_preferences: synchronizeAxisPreferences(axisDefinitions, profile.axis_preferences),
      max_holding_weight: profile.max_holding_weight,
      max_companies_per_category: profile.max_companies_per_category,
      min_distinct_categories: profile.min_distinct_categories,
      strict_category_limit: profile.strict_category_limit,
      score_weights: { ...profile.score_weights },
      min_posts: profile.min_posts,
      portfolio_size: profile.portfolio_size,
    }));
  }

  function resetToEmptyProfile(axisDefinitions = catalog.custom_esg_axes) {
    setSelectedPresetId("");
    setSelectedSavedProfileId("");
    setProfileDescription("");
    setForm(buildEmptyProfile(axisDefinitions));
  }

  async function refreshSavedProfiles(nextSelectedId = null) {
    const nextSavedProfiles = await fetchSavedProfiles();
    startTransition(() => {
      setSavedProfiles(nextSavedProfiles.saved_profiles);
      if (nextSelectedId !== null) {
        setSelectedSavedProfileId(nextSelectedId);
      }
    });
    return nextSavedProfiles.saved_profiles;
  }

  async function refreshDataOps() {
    const [nextDataStatus, nextFundamentalsWorklist, nextTechnicalsWorklist] = await Promise.all([
      fetchDataStatus(),
      fetchDataWorklist("fundamentals", { min_posts: 30, limit: 8, only_missing: true }),
      fetchDataWorklist("technicals", { min_posts: 30, limit: 8, only_missing: true }),
    ]);

    startTransition(() => {
      setDataStatus(nextDataStatus);
      setFundamentalsWorklist(nextFundamentalsWorklist.rows ?? []);
      setTechnicalsWorklist(nextTechnicalsWorklist.rows ?? []);
    });

    return {
      status: nextDataStatus,
      fundamentals: nextFundamentalsWorklist,
      technicals: nextTechnicalsWorklist,
    };
  }

  useEffect(() => {
    let active = true;

    async function loadBootstrap() {
      try {
        const [nextCatalog, nextProfiles, nextSavedProfiles, nextDataStatus, nextFundamentalsWorklist, nextTechnicalsWorklist] = await Promise.all([
          fetchCatalog(),
          fetchProfiles(),
          fetchSavedProfiles(),
          fetchDataStatus(),
          fetchDataWorklist("fundamentals", { min_posts: 30, limit: 8, only_missing: true }),
          fetchDataWorklist("technicals", { min_posts: 30, limit: 8, only_missing: true }),
        ]);
        if (!active) return;

        startTransition(() => {
          setCatalog(nextCatalog);
          setProfiles(nextProfiles.profiles);
          setSavedProfiles(nextSavedProfiles.saved_profiles);
          setDataStatus(nextDataStatus);
          setFundamentalsWorklist(nextFundamentalsWorklist.rows ?? []);
          setTechnicalsWorklist(nextTechnicalsWorklist.rows ?? []);
        });

        setSelectedPresetId("");
        setSelectedSavedProfileId("");
        setProfileDescription("");
        setForm(buildEmptyProfile(nextCatalog.custom_esg_axes));
      } catch (nextError) {
        if (!active) return;
        setError(`Nie udalo sie pobrac danych startowych: ${nextError.message}`);
      } finally {
        if (active) {
          setCatalogLoading(false);
          setDataLoading(false);
        }
      }
    }

    loadBootstrap();

    return () => {
      active = false;
    };
  }, []);

  async function handleGenerate() {
    setLoading(true);
    setError("");
    setReportStatus("");
    setProfileStatus("");

    try {
      const payload = {
        ...form,
        dimension_filters: {
          perception_min: dimensionFilters.perception_min !== "" ? Number(dimensionFilters.perception_min) : null,
          esg_max: dimensionFilters.esg_max !== "" ? Number(dimensionFilters.esg_max) : null,
          profitability_min: dimensionFilters.profitability_min !== "" ? Number(dimensionFilters.profitability_min) : null,
          technical_min: dimensionFilters.technical_min !== "" ? Number(dimensionFilters.technical_min) : null,
          include_missing_perception: dimensionFilters.include_missing_perception,
          include_missing_esg: dimensionFilters.include_missing_esg,
          include_missing_profitability: dimensionFilters.include_missing_profitability,
          include_missing_technical: dimensionFilters.include_missing_technical,
        },
      };
      const nextResult = await buildPortfolioPreview(payload);
      startTransition(() => {
        setResult(nextResult);
      });
      setStep(4);
      setMaxStep(4);
    } catch (nextError) {
      setError(`Nie udalo sie zbudowac portfela: ${nextError.message}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleReportExport() {
    setReporting(true);
    setError("");
    setReportStatus("");
    setProfileStatus("");

    try {
      const report = await exportPortfolioReport(form);
      const blob = new Blob([report.markdown], { type: "text/markdown;charset=utf-8" });
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = `${report.file_slug}.md`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(objectUrl);

      startTransition(() => {
        setResult(report.preview);
        setReportStatus(`Raport zapisany w ${report.markdown_file} oraz ${report.json_file}.`);
      });
    } catch (nextError) {
      setError(`Nie udalo sie wyeksportowac raportu: ${nextError.message}`);
    } finally {
      setReporting(false);
    }
  }

  function handleTextChange(event) {
    const { name, value } = event.target;
    setForm((current) => ({ ...current, [name]: value }));
  }

  function handleNumberChange(event) {
    const { name, value } = event.target;
    setForm((current) => ({ ...current, [name]: Number(value) }));
  }

  function handleCheckboxChange(event) {
    const { name, checked } = event.target;
    setForm((current) => ({ ...current, [name]: checked }));
  }

  function handleCategoryToggle(categoryName) {
    setForm((current) => {
      const isSelected = current.categories.includes(categoryName);
      return {
        ...current,
        categories: isSelected
          ? current.categories.filter((item) => item !== categoryName)
          : [...current.categories, categoryName],
      };
    });
  }

  function handleInstrumentUniverseToggle(universeId) {
    setForm((current) => {
      const isSelected = current.allowed_instrument_universes.includes(universeId);
      return {
        ...current,
        allowed_instrument_universes: isSelected
          ? current.allowed_instrument_universes.filter((item) => item !== universeId)
          : [...current.allowed_instrument_universes, universeId],
      };
    });
  }

  function handleSelectAllCategories() {
    setForm((current) => ({
      ...current,
      categories: catalog.categories.map((item) => item.name),
    }));
  }

  function handleClearCategories() {
    setForm((current) => ({ ...current, categories: [] }));
  }

  function handleWeightChange(event) {
    const { name, value } = event.target;
    setForm((current) => ({
      ...current,
      score_weights: {
        ...current.score_weights,
        [name]: Number(value) / 100,
      },
    }));
  }

  function handleAxisModeChange(axisId, mode) {
    setForm((current) => ({
      ...current,
      axis_preferences: synchronizeAxisPreferences(catalog.custom_esg_axes, current.axis_preferences).map((axis) =>
        axis.axis_id === axisId ? { ...axis, mode } : axis,
      ),
    }));
  }

  function handleAxisImportanceChange(axisId, value) {
    setForm((current) => ({
      ...current,
      axis_preferences: synchronizeAxisPreferences(catalog.custom_esg_axes, current.axis_preferences).map((axis) =>
        axis.axis_id === axisId ? { ...axis, importance: Number(value) / 100 } : axis,
      ),
    }));
  }

  function handlePresetChange(event) {
    const nextPresetId = event.target.value;
    if (!nextPresetId) {
      resetToEmptyProfile(catalog.custom_esg_axes);
      return;
    }
    const preset = profiles.find((item) => item.id === nextPresetId);
    if (!preset) return;
    applyPreset(preset, catalog.custom_esg_axes);
  }

  function handleSavedProfileChange(event) {
    const nextSavedProfileId = event.target.value;
    if (!nextSavedProfileId) {
      setSelectedSavedProfileId("");
      setProfileDescription("");
      return;
    }
    const savedProfile = savedProfiles.find((item) => item.profile_id === nextSavedProfileId);
    if (!savedProfile) return;
    applySavedProfile(savedProfile, catalog.custom_esg_axes);
  }

  async function handleSaveProfile() {
    setSavingProfile(true);
    setError("");
    setReportStatus("");
    setProfileStatus("");

    try {
      const saved = await saveProfile({
        ...form,
        profile_id: selectedSavedProfileId || null,
        description: profileDescription.trim() || null,
      });
      await refreshSavedProfiles(saved.profile_id);
      applySavedProfile(saved, catalog.custom_esg_axes);
      setProfileStatus(`Profil "${saved.profile_name}" zostal zapisany w bibliotece uzytkownika.`);
    } catch (nextError) {
      setError(`Nie udalo sie zapisac profilu: ${nextError.message}`);
    } finally {
      setSavingProfile(false);
    }
  }

  async function handleDeleteProfile() {
    if (!selectedSavedProfileId) return;
    const savedProfile = savedProfiles.find((item) => item.profile_id === selectedSavedProfileId);
    const label = savedProfile?.profile_name ?? selectedSavedProfileId;
    if (!window.confirm(`Usunac zapisany profil "${label}"?`)) {
      return;
    }

    setDeletingProfile(true);
    setError("");
    setReportStatus("");
    setProfileStatus("");

    try {
      const response = await deleteProfile(selectedSavedProfileId);
      if (!response.deleted) {
        throw new Error("Backend nie potwierdzil usuniecia profilu.");
      }
      await refreshSavedProfiles("");
      setProfileStatus(`Profil "${label}" zostal usuniety z biblioteki.`);
      setSelectedSavedProfileId("");
    } catch (nextError) {
      setError(`Nie udalo sie usunac profilu: ${nextError.message}`);
    } finally {
      setDeletingProfile(false);
    }
  }

  async function handleDataUpload(kind) {
    const isFundamentals = kind === "fundamentals";
    const file = isFundamentals ? fundamentalsFile : technicalsFile;
    if (!file) {
      setError(`Najpierw wybierz plik CSV dla ${isFundamentals ? "fundamentow" : "technikaliow"}.`);
      return;
    }

    if (isFundamentals) {
      setFundamentalsUploading(true);
    } else {
      setTechnicalsUploading(true);
    }

    setError("");
    setReportStatus("");
    setProfileStatus("");
    setDataStatusMessage("");

    try {
      const response = await importRawData(kind, {
        file,
        source_name: isFundamentals ? fundamentalsSourceName.trim() || null : technicalsSourceName.trim() || null,
        as_of_date: isFundamentals ? fundamentalsAsOfDate.trim() || null : technicalsAsOfDate.trim() || null,
        replace: isFundamentals ? fundamentalsReplace : technicalsReplace,
      });
      await refreshDataOps();
      const nextCatalog = await fetchCatalog();
      startTransition(() => {
        setCatalog(nextCatalog);
      });
      setDataStatusMessage(
        `Import ${isFundamentals ? "fundamentow" : "technikaliow"} zakonczony. Wgrany plik: ${response.saved_file}.`,
      );

      if (isFundamentals) {
        setFundamentalsFile(null);
      } else {
        setTechnicalsFile(null);
      }
    } catch (nextError) {
      setError(`Nie udalo sie zaimportowac ${isFundamentals ? "fundamentow" : "technikaliow"}: ${nextError.message}`);
    } finally {
      if (isFundamentals) {
        setFundamentalsUploading(false);
      } else {
        setTechnicalsUploading(false);
      }
    }
  }

  const metrics = result?.metrics ?? catalog.metrics;
  const resolvedWeights = result?.score_weights ?? form.score_weights;
  const activePreset = profiles.find((profile) => profile.id === selectedPresetId);
  const activeSavedProfile = savedProfiles.find((profile) => profile.profile_id === selectedSavedProfileId);
  const axisDefinitions = catalog.custom_esg_axes ?? [];
  const instrumentUniverseDefinitions = catalog.instrument_universes ?? [];
  const axisPreferences = synchronizeAxisPreferences(axisDefinitions, form.axis_preferences);
  const fundamentalsStatus = dataStatus?.fundamentals;
  const technicalsStatus = dataStatus?.technicals;
  const activePresetCopy = getPresetCopy(activePreset);
  const normalizedCategoryQuery = categoryQuery.trim().toLowerCase();
  const normalizedAxisQuery = axisQuery.trim().toLowerCase();
  const visibleCategories = catalog.categories.filter((item) =>
    normalizedCategoryQuery ? item.name.toLowerCase().includes(normalizedCategoryQuery) : true,
  );
  const sortedAxisDefinitions = [...axisDefinitions].sort(
    (a, b) => (b.corpus_weight ?? 0) - (a.corpus_weight ?? 0)
  );
  const filteredAxisDefinitions = sortedAxisDefinitions.filter((axis) => {
    if (!normalizedAxisQuery) return true;
    const haystack = [axis.label, axis.family_label, ...(axis.keywords ?? []), ...(axis.topic_labels ?? [])]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(normalizedAxisQuery);
  });
  const displayedAxisDefinitions = showAllAxes ? filteredAxisDefinitions : filteredAxisDefinitions.slice(0, 18);
  const selectedCategoryCount = form.categories.length;

  return (
    <div className="app-shell">
      <div className="mosaic-sidebar">
        {mosaicColors.map((color, i) => (
          <div key={i} className="mosaic-block" style={{ background: color }} />
        ))}
      </div>

      <div className="app-content">
        <WizardBar step={step} maxStep={maxStep} onStep={setStep} />

        <main className="wizard-main">
        {/* ── STEP 1: START ── */}
        {step === 1 && (
        <section className="wizard-step-panel">
          <div className="start-hero">
            <p className="eyebrow">Inżynieria selekcji wartości</p>
            <h1 className="glitch-milk" data-text="Kreator portfela ESG-like">
              Kreator portfela ESG-like
            </h1>
            <p className="hero-copy">
              Zbuduj portfel inwestycyjny oparty na własnych wartościach — nie na gotowych standardach ESG.
              Wybierz preset jako punkt startowy albo zacznij od zera.
            </p>
          </div>

          <div className="preset-grid">
            {profiles.map((profile) => {
              const copy = getPresetCopy(profile);
              return (
                <button
                  key={profile.id}
                  type="button"
                  className={`preset-card${selectedPresetId === profile.id ? " selected" : ""}`}
                  onClick={() => { applyPreset(profile); setStep(2); }}
                  disabled={catalogLoading}
                >
                  <strong>{copy?.title ?? profile.name}</strong>
                  <p>{copy?.description ?? ""}</p>
                </button>
              );
            })}
            <button
              type="button"
              className={`preset-card preset-card-blank${!selectedPresetId ? " selected" : ""}`}
              onClick={() => { resetToEmptyProfile(catalog?.custom_esg_axes); setStep(2); }}
              disabled={catalogLoading}
            >
              <strong>Od zera</strong>
              <p>Zacznij z pustymi ustawieniami i skonfiguruj wszystko ręcznie.</p>
            </button>
          </div>

          {savedProfiles.length > 0 && (
            <details className="details-card">
              <summary>Wczytaj zapisany profil ({savedProfiles.length})</summary>
              <div className="details-body">
                <select
                  value={selectedSavedProfileId}
                  onChange={handleSavedProfileChange}
                  disabled={catalogLoading}
                >
                  <option value="">Wybierz profil...</option>
                  {savedProfiles.map((profile) => (
                    <option key={profile.profile_id} value={profile.profile_id}>
                      {profile.profile_name}
                    </option>
                  ))}
                </select>
                {activeSavedProfile && (
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => setStep(2)}
                  >
                    Wczytaj i przejdź dalej →
                  </button>
                )}
              </div>
            </details>
          )}

          <div className="step-nav">
            <span />
            <button type="button" className="primary-button" onClick={() => setStep(2)} disabled={catalogLoading}>
              Dalej →
            </button>
          </div>
        </section>
        )}

        {/* ── STEP 2: WARTOŚCI ── */}
        {step === 2 && (
        <section className="wizard-step-panel">

          <div className="panel">
            <div className="panel-head">
              <h2>Kategorie spółek</h2>
              <span className="badge ghost">{form.categories.length > 0 ? `${form.categories.length} wybranych` : "wszystkie"}</span>
            </div>
            <div className="category-picker">
              <div className="category-picker-head">
                <strong>Wybrane: {form.categories.length}</strong>
                <span>{catalog.categories_count} dostępnych kategorii</span>
              </div>
              <input
                value={categoryQuery}
                onChange={(event) => setCategoryQuery(event.target.value)}
                placeholder="Szukaj kategorii, np. software, oil, retail..."
                disabled={catalogLoading}
              />
              <div className="category-actions">
                <button type="button" className="secondary-button compact-button" onClick={handleSelectAllCategories} disabled={catalogLoading}>Wszystkie</button>
                <button type="button" className="secondary-button compact-button" onClick={handleClearCategories} disabled={catalogLoading}>Wyczyść</button>
              </div>
              <div className="category-list" role="group" aria-label="Lista kategorii">
                {visibleCategories.map((item) => {
                  const selected = form.categories.includes(item.name);
                  return (
                    <label key={item.slug} className={`category-option${selected ? " selected" : ""}`}>
                      <input type="checkbox" checked={selected} onChange={() => handleCategoryToggle(item.name)} />
                      <span>{item.name}</span>
                    </label>
                  );
                })}
              </div>
            </div>
          </div>

          <div className="panel">
  <div className="panel-head">
    <h2>Percepcja spółek — osie organiczne</h2>
    <div className="axis-view-toggle">
      <button type="button" className={`chart-pill${axisViewMode === "list" ? " active" : ""}`} onClick={() => setAxisViewMode("list")}>Lista</button>
      <button type="button" className={`chart-pill${axisViewMode === "groups" ? " active" : ""}`} onClick={() => setAxisViewMode("groups")}>Grupy</button>
    </div>
  </div>
  <p className="panel-copy">
    Każda oś opisuje, jak inwestorzy postrzegają spółkę przez pryzmat komentarzy.
    Ekspozycja = jak mocno spółka jest z tą osią kojarzona. Nastawienie = ton komentarzy.
    Waga 0 = ignoruj tę oś, waga 2 = silnie uwzględnij.
  </p>
  <div className="axis-toolbar">
    <input
      type="search"
      value={axisQuery}
      onChange={(e) => setAxisQuery(e.target.value)}
      placeholder="Szukaj osi, słowa kluczowego..."
    />
  </div>
  {(() => {
    const maxWeight = Math.max(...filteredAxisDefinitions.map((ax) => ax.corpus_weight ?? 0), 1);
    const AxisCard = ({ axis }) => {
      const pref = axisPreferences.find((p) => p.axis_id === axis.axis_id);
      const importance = pref?.importance ?? 0.5;
      const sentColor = (axis.average_sentiment ?? 0) >= 0 ? "#21513f" : "#c0392b";
      const barPct = Math.min(100, ((axis.corpus_weight ?? 0) / maxWeight) * 100).toFixed(1);
      return (
        <article className={`axis-card${importance === 0 ? " axis-card--muted" : ""}`}>
          <div className="axis-card-head">
            <strong className="axis-card-label">{axis.label}</strong>
            <span className="axis-card-sentiment" style={{ color: sentColor }}>
              {(axis.average_sentiment ?? 0) >= 0 ? "▲" : "▼"}{Math.abs((axis.average_sentiment ?? 0) * 100).toFixed(0)}%
            </span>
          </div>
          <div className="axis-card-exposure">
            <div className="axis-card-exposure-bar" style={{ width: `${barPct}%` }} />
          </div>
          {axis.keywords?.length > 0 && (
            <div className="axis-keywords">
              {axis.keywords.slice(0, 4).map((kw) => <span key={kw}>{kw}</span>)}
            </div>
          )}
          <label className="axis-weight-label">
            <span>Waga: {(importance * 2).toFixed(1)}×</span>
            <input
              type="range" min="0" max="100" step="1"
              value={importance * 100}
              onChange={(e) => handleAxisImportanceChange(axis.axis_id, e.target.value)}
            />
          </label>
        </article>
      );
    };
    return (
      <>
        {axisViewMode === "list" && (
          <div className="axis-card-grid">
            {(showAllAxes ? filteredAxisDefinitions : filteredAxisDefinitions.slice(0, 20)).map((axis) => (
              <AxisCard key={axis.axis_id} axis={axis} />
            ))}
          </div>
        )}
        {axisViewMode === "groups" && (
          <div className="axis-cluster-list">
            {(catalog.axis_clusters ?? []).map((cluster) => {
              const clusterAxes = filteredAxisDefinitions.filter((ax) => ax.cluster_id === cluster.cluster_id);
              if (!clusterAxes.length) return null;
              return (
                <details key={cluster.cluster_id} className="axis-cluster-section" open={cluster.cluster_id < 3}>
                  <summary className="axis-cluster-summary">
                    <strong>{cluster.cluster_label}</strong>
                    <span className="badge ghost">{clusterAxes.length} osi</span>
                  </summary>
                  <div className="axis-card-grid">
                    {clusterAxes.map((axis) => <AxisCard key={axis.axis_id} axis={axis} />)}
                  </div>
                </details>
              );
            })}
          </div>
        )}
        {filteredAxisDefinitions.length > 20 && axisViewMode === "list" && (
          <button type="button" className="secondary-button" onClick={() => setShowAllAxes((v) => !v)}>
            {showAllAxes ? "Pokaż mniej" : `Pokaż wszystkie ${filteredAxisDefinitions.length}`}
          </button>
        )}
      </>
    );
  })()}
</div>

          <div className="panel">
            <div className="panel-head"><h2>Dodatkowe filtry</h2></div>
            <div className="mini-grid">
              <label>
                <span>Priorytet rentowności</span>
                <select name="profitability_mode" value={form.profitability_mode} onChange={handleTextChange}>
                  <option value="prefer_high">Preferuj wysoką rentowność</option>
                  <option value="neutral">Neutralnie</option>
                  <option value="prefer_low">Preferuj niską rentowność</option>
                </select>
              </label>
              <label>
                <span>Priorytet techniczny</span>
                <select name="technical_mode" value={form.technical_mode} onChange={handleTextChange}>
                  <option value="prefer_high">Preferuj mocniejszy sygnał</option>
                  <option value="neutral">Neutralnie</option>
                  <option value="prefer_low">Preferuj słabszy sygnał</option>
                </select>
              </label>
              <label>
                <span>Bias kapitalizacji</span>
                <select name="market_cap_mode" value={form.market_cap_mode} onChange={handleTextChange}>
                  <option value="neutral">Neutralnie</option>
                  <option value="prefer_large">Preferuj duże spółki</option>
                  <option value="prefer_small">Preferuj mniejsze spółki</option>
                </select>
              </label>
            </div>
          </div>

          <div className="step-nav">
            <button type="button" className="secondary-button" onClick={() => setStep(1)}>← Wróć</button>
            <button type="button" className="primary-button" onClick={() => setStep(3)}>Dalej →</button>
          </div>
        </section>
        )}

        {/* ── STEP 3: PARAMETRY ── */}
        {step === 3 && (
        <section className="wizard-step-panel">
          <div className="panel">
            <div className="panel-head"><h2>Parametry portfela</h2></div>
            <div className="mini-grid">
              <label>
                <span>Ile spółek ma mieć portfel</span>
                <input type="number" min="1" max="50" name="portfolio_size" value={form.portfolio_size} onChange={handleNumberChange} />
              </label>
              <label>
                <span>Minimalna liczba komentarzy na spółkę</span>
                <input type="number" min="0" max="500" name="min_posts" value={form.min_posts} onChange={handleNumberChange} />
              </label>
              <label>
                <span>Maksymalna waga jednej spółki</span>
                <input type="number" min="0.05" max="1" step="0.01" name="max_holding_weight" value={form.max_holding_weight} onChange={handleNumberChange} />
              </label>
              <label>
                <span>Maksymalnie spółek na kategorię</span>
                <input type="number" min="0" max="20" name="max_companies_per_category" value={form.max_companies_per_category} onChange={handleNumberChange} />
              </label>
              <label>
                <span>Minimalna liczba kategorii</span>
                <input type="number" min="1" max="20" name="min_distinct_categories" value={form.min_distinct_categories} onChange={handleNumberChange} />
              </label>
              <label>
                <span>Jak rozkładać wagi w portfelu</span>
                <select name="weighting_mode" value={form.weighting_mode} onChange={handleTextChange}>
                  <option value="equal">Równy udział</option>
                  <option value="score_weighted">Ważenie wynikiem</option>
                </select>
              </label>
            </div>
            <label className="checkbox-row">
              <input type="checkbox" name="strict_category_limit" checked={form.strict_category_limit} onChange={handleCheckboxChange} />
              <span>Trzymaj ścisły limit kategorii nawet kosztem mniejszej liczby pozycji</span>
            </label>
          </div>

          <div className="panel">
            <div className="panel-head"><h2>Wagi składowych scoringu</h2></div>
            <div className="weights-block">
              <label>
                <span>Jakość bazowa: {weightPercent(form.score_weights.base_quality)}</span>
                <input type="range" min="0" max="100" step="1" name="base_quality" value={form.score_weights.base_quality * 100} onChange={handleWeightChange} />
              </label>
              <label>
                <span>Custom ESG: {weightPercent(form.score_weights.esg_alignment)}</span>
                <input type="range" min="0" max="100" step="1" name="esg_alignment" value={form.score_weights.esg_alignment * 100} onChange={handleWeightChange} />
              </label>
              <label>
                <span>Dopasowanie kategorii: {weightPercent(form.score_weights.category_match)}</span>
                <input type="range" min="0" max="100" step="1" name="category_match" value={form.score_weights.category_match * 100} onChange={handleWeightChange} />
              </label>
              <label>
                <span>Rentowność: {weightPercent(form.score_weights.profitability_alignment)}</span>
                <input type="range" min="0" max="100" step="1" name="profitability_alignment" value={form.score_weights.profitability_alignment * 100} onChange={handleWeightChange} />
              </label>
              <label>
                <span>Technikalia: {weightPercent(form.score_weights.technical_alignment)}</span>
                <input type="range" min="0" max="100" step="1" name="technical_alignment" value={form.score_weights.technical_alignment * 100} onChange={handleWeightChange} />
              </label>
              <label>
                <span>Kapitalizacja: {weightPercent(form.score_weights.market_cap_alignment)}</span>
                <input type="range" min="0" max="100" step="1" name="market_cap_alignment" value={form.score_weights.market_cap_alignment * 100} onChange={handleWeightChange} />
              </label>
            </div>
          </div>

          <div className="panel">
            <div className="panel-head"><h2>Filtry wymiarów</h2></div>
            <p className="panel-copy">Spółki niespełniające progu są wykluczone z wyników. Brak danych = spółka przechodzi (toggle).</p>
            <div className="dimension-filter-grid">
              <div className="dimension-filter-row">
                <label>
                  <span>Percepcja min (0–1)</span>
                  <input type="number" min="0" max="1" step="0.05" placeholder="brak progu" value={dimensionFilters.perception_min} onChange={(e) => setDimensionFilters((f) => ({ ...f, perception_min: e.target.value }))} />
                </label>
                <label className="checkbox-row">
                  <input type="checkbox" checked={dimensionFilters.include_missing_perception} onChange={(e) => setDimensionFilters((f) => ({ ...f, include_missing_perception: e.target.checked }))} />
                  <span>Uwzględnij bez percepcji</span>
                </label>
              </div>
              <div className="dimension-filter-row">
                <label>
                  <span>ESG ryzyko max (niższy = lepszy)</span>
                  <input type="number" min="0" max="100" step="1" placeholder="brak progu" value={dimensionFilters.esg_max} onChange={(e) => setDimensionFilters((f) => ({ ...f, esg_max: e.target.value }))} />
                </label>
                <label className="checkbox-row">
                  <input type="checkbox" checked={dimensionFilters.include_missing_esg} onChange={(e) => setDimensionFilters((f) => ({ ...f, include_missing_esg: e.target.checked }))} />
                  <span>Uwzględnij bez ESG</span>
                </label>
              </div>
              <div className="dimension-filter-row">
                <label>
                  <span>Rentowność min (0–100)</span>
                  <input type="number" min="0" max="100" step="1" placeholder="brak progu" value={dimensionFilters.profitability_min} onChange={(e) => setDimensionFilters((f) => ({ ...f, profitability_min: e.target.value }))} />
                </label>
                <label className="checkbox-row">
                  <input type="checkbox" checked={dimensionFilters.include_missing_profitability} onChange={(e) => setDimensionFilters((f) => ({ ...f, include_missing_profitability: e.target.checked }))} />
                  <span>Uwzględnij bez fundamentów</span>
                </label>
              </div>
              <div className="dimension-filter-row">
                <label>
                  <span>Technikalia min (0–100)</span>
                  <input type="number" min="0" max="100" step="1" placeholder="brak progu" value={dimensionFilters.technical_min} onChange={(e) => setDimensionFilters((f) => ({ ...f, technical_min: e.target.value }))} />
                </label>
                <label className="checkbox-row">
                  <input type="checkbox" checked={dimensionFilters.include_missing_technical} onChange={(e) => setDimensionFilters((f) => ({ ...f, include_missing_technical: e.target.checked }))} />
                  <span>Uwzględnij bez technikaliów</span>
                </label>
              </div>
            </div>
          </div>

          <details className="details-card">
            <summary>Zapis profilu</summary>
            <div className="details-body">
              <label>
                <span>Nazwa zapisywanego profilu</span>
                <input name="profile_name" value={form.profile_name} onChange={handleTextChange} />
              </label>
              <label>
                <span>Opis profilu</span>
                <textarea name="profile_description" value={profileDescription} onChange={(event) => setProfileDescription(event.target.value)} rows={3} placeholder="Opcjonalny opis strategii." />
              </label>
              <div className="action-row">
                <button type="button" className="secondary-button" onClick={handleSaveProfile} disabled={loading || savingProfile || catalogLoading}>
                  {savingProfile ? "Zapisywanie..." : selectedSavedProfileId ? "Aktualizuj profil" : "Zapisz profil"}
                </button>
                <button type="button" className="secondary-button danger-button" onClick={handleDeleteProfile} disabled={!selectedSavedProfileId || savingProfile || deletingProfile}>
                  {deletingProfile ? "Usuwanie..." : "Usuń profil"}
                </button>
              </div>
              {profileStatus && <p className="profile-status">{profileStatus}</p>}
            </div>
          </details>

          {error && <p className="error-message">{error}</p>}

          <div className="step-nav">
            <button type="button" className="secondary-button" onClick={() => setStep(2)}>← Wróć</button>
            <button
              type="button"
              className="primary-button"
              onClick={handleGenerate}
              disabled={loading || catalogLoading}
            >
              {loading ? "Generowanie..." : "Generuj portfel →"}
            </button>
          </div>
        </section>
        )}

        {/* ── STEP 4: WYNIKI ── */}
        {step === 4 && (
        <section className="wizard-step-panel">
          <div className="step-nav" style={{ paddingTop: 0 }}>
            <button type="button" className="secondary-button" onClick={() => setStep(3)}>← Zmień parametry</button>
            <div style={{ display: "flex", gap: 8 }}>
              <button type="button" className="secondary-button" onClick={handleGenerate} disabled={loading}>
                {loading ? "Generowanie..." : "Generuj ponownie"}
              </button>
              <button type="button" className="secondary-button" onClick={handleReportExport} disabled={reporting}>
                {reporting ? "Eksport..." : "Eksportuj raport .md"}
              </button>
            </div>
          </div>

          {!result ? (
            <p className="chart-status">
              Brak wyników.{" "}
              <button type="button" className="secondary-button" onClick={() => setStep(3)}>Wróć do parametrów</button>
            </p>
          ) : (
            <>
              {result.warnings.length > 0 ? (
                <div className="warning-box">
                  <h3>Uwagi do prototypu</h3>
                  <ul>
                    {result.warnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              <p className="panel-copy">
                Sposob rozkladania wag: <strong>{weightingModeLabels[result.weighting_mode] ?? result.weighting_mode}</strong>. Spolek po filtracji:{" "}
                <strong>{result.matched_companies}</strong>.
              </p>

              {result.comparison ? (
                <div className="comparison-block">
                  <div className="comparison-head">
                    <h3>Jak Twoj portfel wypada wzgledem benchmarku ESG-like</h3>
                    <span>{result.comparison.benchmark.label}</span>
                  </div>
                  <div className="comparison-grid">
                    <article>
                      <span className="stat-label">Wspolne spolki</span>
                      <strong>{result.comparison.metrics.overlap_count}</strong>
                    </article>
                    <article>
                      <span className="stat-label">Overlap ratio</span>
                      <strong>{(result.comparison.metrics.overlap_ratio * 100).toFixed(1)}%</strong>
                    </article>
                    <article>
                      <span className="stat-label">Delta custom ESG</span>
                      <strong>{result.comparison.metrics.custom_esg_delta != null ? result.comparison.metrics.custom_esg_delta.toFixed(2) : "n/d"}</strong>
                    </article>
                    <article>
                      <span className="stat-label">Delta sentymentu</span>
                      <strong>{result.comparison.metrics.sentiment_delta != null ? result.comparison.metrics.sentiment_delta.toFixed(4) : "n/d"}</strong>
                    </article>
                    <article>
                      <span className="stat-label">Delta kategorii</span>
                      <strong>{result.comparison.metrics.distinct_categories_delta}</strong>
                    </article>
                  </div>
                  <div className="portfolio-strip comparison-strip">
                    {result.comparison.benchmark.holdings.map((holding) => (
                      <article key={`benchmark-${holding.symbol}`} className="holding-card comparison-card">
                        <span className="holding-symbol">{holding.symbol}</span>
                        <strong>{holding.company_name}</strong>
                        <span>{holding.category}</span>
                        <span className="holding-weight">{(holding.weight * 100).toFixed(1)}%</span>
                        <span>score {holding.selection_score.toFixed(4)}</span>
                      </article>
                    ))}
                  </div>
                </div>
              ) : null}

              <div className="summary-grid">
                <article>
                  <span className="stat-label">Pozycji</span>
                  <strong>{result.summary.selected_companies}</strong>
                </article>
                <article>
                  <span className="stat-label">Kategorie</span>
                  <strong>{result.summary.distinct_categories}</strong>
                </article>
                <article>
                  <span className="stat-label">Sredni custom ESG</span>
                  <strong>{result.summary.average_custom_esg != null ? result.summary.average_custom_esg.toFixed(2) : "n/d"}</strong>
                </article>
                <article>
                  <span className="stat-label">Srednia rentownosc</span>
                  <strong>{result.summary.average_profitability != null ? result.summary.average_profitability.toFixed(2) : "n/d"}</strong>
                </article>
                <article>
                  <span className="stat-label">Srednia technika</span>
                  <strong>{result.summary.average_technical != null ? result.summary.average_technical.toFixed(2) : "n/d"}</strong>
                </article>
                <article>
                  <span className="stat-label">HHI koncentracji</span>
                  <strong>{result.summary.concentration_hhi.toFixed(4)}</strong>
                </article>
                <article>
                  <span className="stat-label">Top kategoria</span>
                  <strong>{result.summary.top_category ?? "n/d"}</strong>
                </article>
              </div>

              <div className="allocation-strip">
                {result.category_allocations.map((allocation) => (
                  <article key={allocation.category} className="allocation-card">
                    <strong>{allocation.category}</strong>
                    <span>{allocation.holdings_count} spolek</span>
                    <span>{(allocation.total_weight * 100).toFixed(1)}% wagi</span>
                    <span>avg score {allocation.average_selection_score.toFixed(4)}</span>
                  </article>
                ))}
              </div>

              <div className="portfolio-strip">
                {result.holdings.map((holding) => (
                  <article key={holding.symbol} className="holding-card">
                    <span className="holding-symbol">{holding.symbol}</span>
                    <strong>{holding.company_name}</strong>
                    <span>{holding.category}</span>
                    <span className="holding-weight">{(holding.weight * 100).toFixed(1)}%</span>
                    <span>score {holding.selection_score.toFixed(4)}</span>
                  </article>
                ))}
              </div>

              <div className="company-table">
                {result.companies.map((company) => (
                  <article key={company.symbol} className={`company-row${expandedSymbol === company.symbol ? " company-row--expanded" : ""}`}>
                    <div>
                      <div className="company-headline">
                        <strong>{company.symbol}</strong>
                        <span>{company.company_name}</span>
                      </div>
                      <p className="company-meta">
                        {company.category}
                        {company.industry ? ` / ${company.industry}` : ""}
                        {company.market_cap_label ? ` / ${company.market_cap_label}` : ""}
                      </p>
                      <div className="company-dimensions">
                        <div className="company-dim">
                          <span className="company-dim-label">Percepcja</span>
                          <strong className="company-dim-value">{company.perception_score != null ? company.perception_score.toFixed(2) : "n/d"}</strong>
                        </div>
                        <div className="company-dim">
                          <span className="company-dim-label">ESG ryzyko</span>
                          <strong className="company-dim-value">{company.real_esg_total_score != null ? company.real_esg_total_score.toFixed(1) : "n/d"}</strong>
                        </div>
                        <div className="company-dim">
                          <span className="company-dim-label">Rentowność</span>
                          <strong className="company-dim-value">{company.profitability_score != null ? company.profitability_score.toFixed(1) : "n/d"}</strong>
                        </div>
                        <div className="company-dim">
                          <span className="company-dim-label">Technikalia</span>
                          <strong className="company-dim-value">{company.technical_score != null ? company.technical_score.toFixed(1) : "n/d"}</strong>
                        </div>
                      </div>
                      {company.custom_esg_families?.length ? (
                        <div className="axis-strip family-strip">
                          {company.custom_esg_families.slice(0, 5).map((family) => (
                            <article key={`${company.symbol}-${family.family_id}`} className="axis-chip family-chip" title={family.summary ?? family.label}>
                              <strong>{family.label}</strong>
                              <span>{family.score != null ? `score ${family.score.toFixed(2)}` : "score n/d"}</span>
                              <span>{family.exposure != null ? `exp ${family.exposure.toFixed(3)}` : "exp n/d"}</span>
                              <span>{family.esg_relevance != null ? `rel ${family.esg_relevance.toFixed(2)}` : "rel n/d"}</span>
                            </article>
                          ))}
                          {company.custom_esg_families.length > 5 ? (
                            <article className="axis-chip axis-chip-more family-chip-more">
                              <strong>+{company.custom_esg_families.length - 5}</strong>
                              <span>Pozostale rodziny ukryte</span>
                            </article>
                          ) : null}
                        </div>
                      ) : null}
                      {company.custom_esg_axes?.length ? (
                        <div className="axis-strip">
                          {company.custom_esg_axes.slice(0, 8).map((axis) => (
                            <article key={`${company.symbol}-${axis.axis_id}`} className="axis-chip" title={axis.summary ?? axis.label}>
                              <strong>{axis.label}</strong>
                              {axis.family_label ? <span>{axis.family_label}</span> : null}
                              <span>{axis.score != null ? `score ${axis.score.toFixed(2)}` : "score n/d"}</span>
                              <span>{axis.exposure != null ? `exp ${axis.exposure.toFixed(3)}` : "exp n/d"}</span>
                              <span>{axis.confidence != null ? `conf ${axis.confidence.toFixed(3)}` : "conf n/d"}</span>
                            </article>
                          ))}
                          {company.custom_esg_axes.length > 8 ? (
                            <article className="axis-chip axis-chip-more">
                              <strong>+{company.custom_esg_axes.length - 8}</strong>
                              <span>Pozostale wymiary ukryte</span>
                            </article>
                          ) : null}
                        </div>
                      ) : null}
                      <p className="company-meta">
                        base {company.score_breakdown.base_quality.toFixed(4)} / esg {company.score_breakdown.esg_alignment.toFixed(4)} / kat.{" "}
                        {company.score_breakdown.category_match.toFixed(4)} / rent. {company.score_breakdown.profitability_alignment.toFixed(4)} / tech.{" "}
                        {company.score_breakdown.technical_alignment.toFixed(4)} / cap{" "}
                        {company.score_breakdown.market_cap_alignment.toFixed(4)}
                      </p>
                      <div className="axiological-profile">
                        {company.axiological_profile_null || company.axiological_coverage == null ? (
                          <p className="axiological-null">Brak profilu aksjologicznego</p>
                        ) : (
                          <>
                            <div className="axiological-metrics">
                              <div className="axiological-metric">
                                <span>Pokrycie</span>
                                <strong>{(company.axiological_coverage * 100).toFixed(0)}%</strong>
                              </div>
                              <div className="axiological-metric">
                                <span>Pewność</span>
                                <strong>{company.axiological_confidence != null ? company.axiological_confidence.toFixed(2) : "n/d"}</strong>
                              </div>
                              <div className="axiological-metric">
                                <span>Zgodność metod</span>
                                <strong>{company.axiological_inter_method_agreement != null ? (company.axiological_inter_method_agreement * 100).toFixed(0) + "%" : "n/d"}</strong>
                              </div>
                            </div>
                            {company.axiological_low_signal && (
                              <p className="axiological-low-signal">
                                ⚠ Niski sygnał wartościowy — interpretuj ostrożnie
                              </p>
                            )}
                            {company.axiological_frames?.length > 0 && (
                              <div className="axiological-frames">
                                {company.axiological_frames.slice(0, 6).map((frame, i) => (
                                  <span key={i} className="axiological-frame-chip">
                                    {String(frame.label ?? frame).toLowerCase()}
                                  </span>
                                ))}
                                {company.axiological_frames.length > 6 && (
                                  <span className="axiological-frame-chip axiological-frame-more">
                                    +{company.axiological_frames.length - 6}
                                  </span>
                                )}
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    </div>
                    <div className="score-box">
                      <span>score</span>
                      <strong>{company.selection_score.toFixed(4)}</strong>
                      <button
                        className="expand-btn"
                        onClick={() => setExpandedSymbol(expandedSymbol === company.symbol ? null : company.symbol)}
                        title={expandedSymbol === company.symbol ? "Zwiń" : "Wykres i analiza"}
                      >
                        {expandedSymbol === company.symbol ? "▲" : "▼"}
                      </button>
                    </div>
                    <div className="explanations">
                      {company.explanations.map((item) => (
                        <p key={`${company.symbol}-${item.title}`}>
                          <strong>{item.title}:</strong> {item.detail}
                        </p>
                      ))}
                    </div>
                    {expandedSymbol === company.symbol && (
                      <CompanyChart symbol={company.symbol} />
                    )}
                  </article>
                ))}
              </div>
            </>
          )}
        </section>
        )}
      </main>
      </div>
    </div>
  );
}
