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

function buildFamilyDefinitionMap(familyDefinitions = []) {
  return new Map((familyDefinitions ?? []).map((family) => [family.family_id, family]));
}

function groupAxesByFamily(axisDefinitions = [], familyDefinitions = []) {
  const familyDefinitionMap = buildFamilyDefinitionMap(familyDefinitions);
  const families = new Map();

  for (const axis of axisDefinitions) {
    const familyId = axis.family_id ?? `axis-${axis.axis_id}`;
    const familyDefinition = familyDefinitionMap.get(familyId);
    const familyLabel = familyDefinition?.label ?? axis.family_label ?? axis.label;
    const existing = families.get(familyId);
    if (existing) {
      existing.axes.push(axis);
      continue;
    }

    families.set(familyId, {
      familyId,
      familyLabel,
      summary: familyDefinition?.summary ?? null,
      keywords: familyDefinition?.keywords ?? [],
      topicLabels: familyDefinition?.topic_labels ?? [],
      examples: familyDefinition?.examples ?? [],
      memberDimensionsCount: familyDefinition?.member_dimensions_count ?? 0,
      esgRelevance: familyDefinition?.esg_relevance ?? null,
      axes: [axis],
    });
  }

  return [...families.values()].sort((left, right) => left.familyLabel.localeCompare(right.familyLabel));
}

function summarizeFamilyMode(familyPreferences = []) {
  if (!familyPreferences.length) {
    return "neutral";
  }

  const counts = familyPreferences.reduce(
    (bucket, preference) => {
      const mode = preference.mode ?? "neutral";
      bucket[mode] = (bucket[mode] ?? 0) + 1;
      return bucket;
    },
    { prefer_high: 0, neutral: 0, prefer_low: 0 },
  );

  if (counts.prefer_high === familyPreferences.length) return "prefer_high";
  if (counts.prefer_low === familyPreferences.length) return "prefer_low";
  if (counts.neutral === familyPreferences.length) return "neutral";
  return "mixed";
}

function familyModeLabel(mode) {
  if (mode === "prefer_high") return "wzmacniana";
  if (mode === "prefer_low") return "oslabiana";
  if (mode === "mixed") return "mieszana";
  return "neutralna";
}

function describeEsgRelevance(value) {
  const numeric = Number(value ?? 0);
  if (numeric >= 0.55) return "mocno buduje wynik ESG-like";
  if (numeric >= 0.35) return "realnie wplywa na ESG-like";
  if (numeric > 0) return "slabiej, ale nadal jest czescia modelu";
  return "rodzina pomocnicza";
}

function resolveFamilyLens(family) {
  const code = String(family?.dominant_axis_code ?? "").toUpperCase();
  if (code === "E" || code === "S" || code === "G") return code;
  return "MIX";
}

function buildFamilySections(families = []) {
  const definitions = [
    {
      id: "G",
      label: "Governance i zaufanie",
      description: "Rodziny zwiazane z zarzadem, disclosure, zgodnoscia, insiderami i sygnalami ostrzegawczymi rynku.",
    },
    {
      id: "S",
      label: "Wplyw spoleczny i interesariusze",
      description: "Rodziny komentujace produkt, klienta, pracownikow, bezpieczenstwo i spoleczne koszty dzialalnosci.",
    },
    {
      id: "E",
      label: "Srodowisko, zasoby i wydobycie",
      description: "Rodziny dotyczace wydobycia, presji srodowiskowej, energii i bardziej zasobooszczednych modeli biznesu.",
    },
    {
      id: "MIX",
      label: "Rodziny mieszane",
      description: "Organiczne rodziny z komentarzy, ktore nie ukladaja sie jeszcze czysto w jedno streszczenie E, S albo G.",
    },
  ];

  return definitions
    .map((definition) => ({
      ...definition,
      families: families.filter((family) => resolveFamilyLens(family) === definition.id),
    }))
    .filter((section) => section.families.length > 0);
}

export default function App() {
  const [catalog, setCatalog] = useState({
    categories: [],
    categories_count: 0,
    companies_count: 0,
    metrics: null,
    custom_esg_axes: [],
    custom_esg_families: [],
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
      const nextResult = await buildPortfolioPreview(form);
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

  function handleAxisFamilyModeChange(familyAxes, mode) {
    const axisIds = new Set(familyAxes.map((axis) => axis.axis_id));
    setForm((current) => ({
      ...current,
      axis_preferences: synchronizeAxisPreferences(catalog.custom_esg_axes, current.axis_preferences).map((axis) =>
        axisIds.has(axis.axis_id) ? { ...axis, mode } : axis,
      ),
    }));
  }

  function handleAxisFamilyImportanceChange(familyAxes, value) {
    const nextImportance = Number(value) / 100;
    const axisIds = new Set(familyAxes.map((axis) => axis.axis_id));
    setForm((current) => ({
      ...current,
      axis_preferences: synchronizeAxisPreferences(catalog.custom_esg_axes, current.axis_preferences).map((axis) =>
        axisIds.has(axis.axis_id) ? { ...axis, importance: nextImportance } : axis,
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
  const familyDefinitions = catalog.custom_esg_families ?? [];
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
  const sortedAxisDefinitions = [...axisDefinitions].sort((left, right) => {
    const leftFamily = (left.family_label ?? left.label).toLowerCase();
    const rightFamily = (right.family_label ?? right.label).toLowerCase();
    if (leftFamily !== rightFamily) {
      return leftFamily.localeCompare(rightFamily);
    }
    return left.label.localeCompare(right.label);
  });
  const filteredAxisDefinitions = sortedAxisDefinitions.filter((axis) => {
    if (!normalizedAxisQuery) return true;
    const haystack = [axis.label, axis.family_label, ...(axis.keywords ?? []), ...(axis.topic_labels ?? [])]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(normalizedAxisQuery);
  });
  const displayedAxisDefinitions = showAllAxes ? filteredAxisDefinitions : filteredAxisDefinitions.slice(0, 18);
  const axisFamilies = groupAxesByFamily(displayedAxisDefinitions, familyDefinitions);
  const filteredEsgFamilies = familyDefinitions
    .filter((family) => (family.esg_relevance ?? 0) >= 0.05)
    .filter((family) => {
      if (!normalizedAxisQuery) return true;
      const haystack = [family.label, family.summary, ...(family.keywords ?? []), ...(family.topic_labels ?? [])]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(normalizedAxisQuery);
    })
    .map((family) => ({
      ...family,
      axes: axisDefinitions.filter((axis) => (family.member_axis_ids ?? []).includes(axis.axis_id)),
    }))
    .filter((family) => family.axes.length > 0);
  const familySections = buildFamilySections(filteredEsgFamilies);
  const configuredFamilyCount = filteredEsgFamilies.filter((family) => {
    const familyPreferences = family.axes.map((axis) =>
      axisPreferences.find((item) => item.axis_id === axis.axis_id) ?? {
        axis_id: axis.axis_id,
        axis_label: axis.label,
        mode: "neutral",
        importance: 0.5,
      },
    );
    const familyMode = summarizeFamilyMode(familyPreferences);
    const averageImportance =
      familyPreferences.reduce((sum, preference) => sum + (preference.importance ?? 0.5), 0) /
      Math.max(familyPreferences.length, 1);
    return familyMode !== "neutral" || Math.abs(averageImportance - 0.5) > 0.05;
  }).length;
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
        <header className="hero">
          <p className="eyebrow">Inzynieria selekcji wartosci</p>
          <h1
            className="glitch-milk"
            data-text="Kreator portfela oparty na wlasnym ESG-like"
          >
            Kreator portfela oparty na wlasnym ESG-like
          </h1>
          <p className="hero-copy">
            Najpierw ustawiasz, jakie rodziny wartosci maja budowac Twoj autorski wynik ESG-like. Potem zawezasz rynek i
            budujesz portfel, ktory aplikacja zestawia z benchmarkiem ESG-like.
          </p>
        </header>

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

        <section className="panel control-panel">
          <div className="panel-head">
            <h2>Ustaw model i portfel</h2>
            <span className="badge">ESG-like builder</span>
          </div>

          <form onSubmit={(e) => e.preventDefault()} className="form-grid">
            <section className="step-card">
              <div className="step-card-head">
                <span className="step-index">1</span>
                <div>
                  <strong>Profil startowy</strong>
                  <p>Zacznij od pustego profilu albo wez preset tylko jako punkt wyjscia.</p>
                </div>
              </div>

              <label>
                <span>Styl startowy</span>
                <select value={selectedPresetId} onChange={handlePresetChange} disabled={catalogLoading}>
                  <option value="">Pusty profil startowy</option>
                  {profiles.map((profile) => (
                    <option key={profile.id} value={profile.id}>
                      {getPresetCopy(profile)?.title ?? profile.name}
                    </option>
                  ))}
                </select>
              </label>

              {activePresetCopy ? <p className="preset-description">{activePresetCopy.description}</p> : null}

              {!activePresetCopy ? (
                <p className="preset-description">
                  Startujesz od pustego profilu. Presety sa opcjonalne i maja tylko pomoc szybciej ustawic sensowny start.
                </p>
              ) : null}

              <div className="button-row">
                <button
                  type="button"
                  className="secondary-button compact-button"
                  onClick={() => resetToEmptyProfile(catalog.custom_esg_axes)}
                  disabled={catalogLoading}
                >
                  Wroc do pustego profilu
                </button>
              </div>

              <label>
                <span>Wczytaj zapisany profil</span>
                <select value={selectedSavedProfileId} onChange={handleSavedProfileChange} disabled={catalogLoading}>
                  <option value="">Brak</option>
                  {savedProfiles.map((profile) => (
                    <option key={profile.profile_id} value={profile.profile_id}>
                      {profile.profile_name}
                    </option>
                  ))}
                </select>
              </label>

              {activeSavedProfile ? (
                <p className="preset-description">
                  {activeSavedProfile.description || "Profil zapisany lokalnie. Mozesz go nadpisac biezaca konfiguracja albo usunac z biblioteki."}
                </p>
              ) : null}
            </section>

            <section className="step-card">
              <div className="step-card-head">
                <span className="step-index">2</span>
                <div>
                  <strong>Z czego ma powstac Twoje ESG-like</strong>
                  <p>Tu wybierasz rodziny wartosci wydobyte z komentarzy inwestorow. To one buduja glowny wynik ESG-like.</p>
                </div>
              </div>

              <div className="axis-preferences-block main-esg-block">
                <div className="axis-preferences-head">
                  <h3>Rodziny wykryte w komentarzach</h3>
                  <span>{filteredEsgFamilies.length} rodzin / {configuredFamilyCount} juz zmienionych</span>
                </div>

                <div className="axis-toolbar">
                  <input
                    type="search"
                    value={axisQuery}
                    onChange={(event) => setAxisQuery(event.target.value)}
                    placeholder="Szukaj rodziny, slowa kluczowego albo motywu z komentarzy"
                  />
                </div>

                <p className="preset-description">
                  Pod spodem model ma dziesiatki pojedynczych wymiarow i tematow. Tutaj pracujesz juz na ich czytelniejszych rodzinach, z ktorych skladamy finalny wynik ESG-like.
                </p>

                <div className="family-section-list">
                  {familySections.map((section) => (
                    <section key={section.id} className="family-section">
                      <div className="family-section-head">
                        <div>
                          <strong>{section.label}</strong>
                          <p>{section.description}</p>
                        </div>
                        <span className="badge ghost">{section.families.length} rodzin</span>
                      </div>

                      <div className="axis-family-list main-family-list">
                        {section.families.map((family) => {
                          const familyPreferences = family.axes.map((axis) =>
                            axisPreferences.find((item) => item.axis_id === axis.axis_id) ?? {
                              axis_id: axis.axis_id,
                              axis_label: axis.label,
                              mode: "neutral",
                              importance: 0.5,
                            },
                          );
                          const averageImportance =
                            familyPreferences.reduce((sum, preference) => sum + (preference.importance ?? 0.5), 0) /
                            Math.max(familyPreferences.length, 1);
                          const familyMode = summarizeFamilyMode(familyPreferences);

                          return (
                            <article key={family.family_id} className="axis-family-card main-family-card">
                              <div className="axis-family-head">
                                <div className="axis-family-title">
                                  <strong>{family.label}</strong>
                                  <span>{familyModeLabel(familyMode)}</span>
                                </div>
                              </div>

                              <div className="family-pill-row">
                                <span className="family-pill">{family.member_dimensions_count || family.axes.length} wykryte wymiary</span>
                                <span className="family-pill">{describeEsgRelevance(family.esg_relevance)}</span>
                                <span className="family-pill">{weightPercent(averageImportance)} znaczenia</span>
                              </div>

                              {family.summary ? <p className="family-summary">{family.summary}</p> : null}

                              {family.topic_labels?.length ? (
                                <p className="family-topic-preview">
                                  Wykryte motywy: {family.topic_labels.slice(0, 3).join(" • ")}
                                </p>
                              ) : null}

                              {family.keywords?.length ? (
                                <div className="axis-keywords">
                                  {family.keywords.slice(0, 6).map((keyword) => (
                                    <span key={`${family.family_id}-${keyword}`}>{keyword}</span>
                                  ))}
                                </div>
                              ) : null}

                              <div className="family-mode-buttons">
                                <button
                                  type="button"
                                  className={`ghost-button mode-button${familyMode === "prefer_high" ? " is-active is-positive" : ""}`}
                                  onClick={() => handleAxisFamilyModeChange(family.axes, "prefer_high")}
                                >
                                  Wzmacniaj
                                </button>
                                <button
                                  type="button"
                                  className={`ghost-button mode-button${familyMode === "neutral" ? " is-active" : ""}`}
                                  onClick={() => handleAxisFamilyModeChange(family.axes, "neutral")}
                                >
                                  Neutralnie
                                </button>
                                <button
                                  type="button"
                                  className={`ghost-button mode-button${familyMode === "prefer_low" ? " is-active is-negative" : ""}`}
                                  onClick={() => handleAxisFamilyModeChange(family.axes, "prefer_low")}
                                >
                                  Oslabiaj
                                </button>
                              </div>

                              <label className="axis-family-importance">
                                <span>Jak mocno ta rodzina ma wplywac na ESG-like</span>
                                <input
                                  type="range"
                                  min="0"
                                  max="100"
                                  step="1"
                                  value={averageImportance * 100}
                                  onChange={(event) => handleAxisFamilyImportanceChange(family.axes, event.target.value)}
                                />
                              </label>
                            </article>
                          );
                        })}
                      </div>
                    </section>
                  ))}
                </div>
              </div>
            </section>

            <section className="step-card">
              <div className="step-card-head">
                <span className="step-index">3</span>
                <div>
                  <strong>Rynek i kategorie</strong>
                  <p>Jesli nic nie zaznaczysz, model pracuje na calym dostepnym rynku akcji.</p>
                </div>
              </div>
              <div className="category-picker">
                <div className="category-picker-head">
                  <strong>Wybrane: {form.categories.length}</strong>
                  <span>{catalog.categories_count} dostepnych kategorii</span>
                </div>

                <input
                  value={categoryQuery}
                  onChange={(event) => setCategoryQuery(event.target.value)}
                  placeholder="Szukaj kategorii, np. software, oil, retail..."
                  disabled={catalogLoading}
                />

                <div className="category-actions">
                  <button type="button" className="secondary-button compact-button" onClick={handleSelectAllCategories} disabled={catalogLoading}>
                    Wszystkie
                  </button>
                  <button type="button" className="secondary-button compact-button" onClick={handleClearCategories} disabled={catalogLoading}>
                    Wyczyść
                  </button>
                </div>

                <div className="category-list" role="group" aria-label="Lista kategorii">
                  {visibleCategories.map((item) => {
                    const selected = form.categories.includes(item.name);
                    return (
                      <label key={item.slug} className={`category-option${selected ? " selected" : ""}`}>
                        <input
                          type="checkbox"
                          checked={selected}
                          onChange={() => handleCategoryToggle(item.name)}
                        />
                        <span>{item.name}</span>
                      </label>
                    );
                  })}
                </div>
              </div>
            </section>

            <section className="step-card">
              <div className="step-card-head">
                <span className="step-index">4</span>
                <div>
                  <strong>Parametry portfela</strong>
                  <p>Na koniec ustaw wielkosc portfela, minimalny sygnal z komentarzy i sposob wazenia.</p>
                </div>
              </div>

              <div className="mini-grid">
                <label>
                  <span>Ile spolek ma miec portfel</span>
                  <input type="number" min="1" max="50" name="portfolio_size" value={form.portfolio_size} onChange={handleNumberChange} />
                </label>

                <label>
                  <span>Minimalna liczba komentarzy na spolke</span>
                  <input type="number" min="0" max="500" name="min_posts" value={form.min_posts} onChange={handleNumberChange} />
                </label>
              </div>

              <label>
                <span>Jak rozkladac wagi w portfelu</span>
                <select name="weighting_mode" value={form.weighting_mode} onChange={handleTextChange}>
                  <option value="equal">Rowny udzial</option>
                  <option value="score_weighted">Wazenie wynikiem</option>
                </select>
              </label>

              <div className="action-row">
                <button type="button" className="primary-button" onClick={handleGenerate} disabled={loading || reporting || catalogLoading}>
                  {loading ? "Budowanie..." : "Zbuduj portfel"}
                </button>
                <button type="button" className="secondary-button" onClick={handleReportExport} disabled={loading || reporting || catalogLoading}>
                  {reporting ? "Eksport..." : "Eksportuj raport .md"}
                </button>
              </div>
            </section>

            <details className="details-card">
              <summary>Zaawansowane ustawienia i zapis profilu</summary>
              <div className="details-body">
                <label>
                  <span>Nazwa zapisywanego profilu</span>
                  <input name="profile_name" value={form.profile_name} onChange={handleTextChange} />
                </label>

                <label>
                  <span>Opis profilu</span>
                  <textarea
                    name="profile_description"
                    value={profileDescription}
                    onChange={(event) => setProfileDescription(event.target.value)}
                    rows={4}
                    placeholder="Na przyklad: profil pod spolki kontrowersyjne, ale z sensowna skala i mocnym sygnalem spolecznosciowym."
                  />
                </label>

                <label>
                  <span>Glowny kierunek wzgledem streszczenia ESG-like</span>
                  <select name="custom_esg_mode" value={form.custom_esg_mode} onChange={handleTextChange}>
                    <option value="prefer_low">Preferuj nizsza zgodnosc z klasycznym ESG</option>
                    <option value="neutral">Neutralnie</option>
                    <option value="prefer_high">Preferuj wyzsza zgodnosc z klasycznym ESG</option>
                  </select>
                </label>

                <div className="axis-preferences-block">
                  <div className="axis-preferences-head">
                    <h3>Dokladne osie i debug modelu komentarzowego</h3>
                    <span>
                      {axisDefinitions.length
                        ? `${familyDefinitions.length || axisFamilies.length} rodzin / ${axisDefinitions.length} wymiarow`
                        : "brak wymiarow"}
                    </span>
                  </div>

                  {axisDefinitions.length ? (
                    <>
                      <div className="axis-toolbar">
                        <input
                          type="search"
                          value={axisQuery}
                          onChange={(event) => setAxisQuery(event.target.value)}
                          placeholder="Szukaj wymiaru, rodziny albo slowa kluczowego"
                        />
                        <div className="axis-toolbar-actions">
                          <button type="button" className="ghost-button" onClick={() => setShowAllAxes(false)}>
                            Pokaz 18
                          </button>
                          <button type="button" className="ghost-button" onClick={() => setShowAllAxes(true)}>
                            Pokaz wszystkie
                          </button>
                        </div>
                      </div>
                      <p className="preset-description">
                        To jest warstwa bardziej techniczna. Jesli chcesz tylko zbudowac portfel, wystarczy glowny wybor rodzin wyzej.
                        Tutaj mozesz zejsc do poziomu pojedynczych osi jezykowych i zobaczyc, z czego sklada sie model.
                      </p>
                      <p className="preset-description">
                        Wyswietlane: <strong>{displayedAxisDefinitions.length}</strong> z <strong>{filteredAxisDefinitions.length}</strong> pasujacych wymiarow.
                        {!showAllAxes && filteredAxisDefinitions.length > displayedAxisDefinitions.length
                          ? " Reszta jest ukryta, zeby ekran pozostawal czytelny."
                          : ""}
                      </p>
                      <div className="axis-family-list">
                        {axisFamilies.map((family) => {
                          const familyPreferences = family.axes.map((axis) =>
                            axisPreferences.find((item) => item.axis_id === axis.axis_id) ?? {
                              axis_id: axis.axis_id,
                              axis_label: axis.label,
                              mode: "neutral",
                              importance: 0.5,
                            },
                          );
                          const averageImportance =
                            familyPreferences.reduce((sum, preference) => sum + (preference.importance ?? 0.5), 0) /
                            Math.max(familyPreferences.length, 1);

                          return (
                            <article key={family.familyId} className="axis-family-card">
                              <div className="axis-family-head">
                                <div className="axis-family-title">
                                  <strong>{family.familyLabel}</strong>
                                  <span>
                                    {family.axes.length} osi / {family.memberDimensionsCount || family.axes.length} wymiarow
                                    {family.esgRelevance != null ? ` / ESG relevance ${family.esgRelevance.toFixed(2)}` : ""}
                                  </span>
                                </div>
                                <div className="axis-family-actions">
                                  <button type="button" className="ghost-button" onClick={() => handleAxisFamilyModeChange(family.axes, "prefer_high")}>
                                    Wysoko
                                  </button>
                                  <button type="button" className="ghost-button" onClick={() => handleAxisFamilyModeChange(family.axes, "neutral")}>
                                    Neutralnie
                                  </button>
                                  <button type="button" className="ghost-button" onClick={() => handleAxisFamilyModeChange(family.axes, "prefer_low")}>
                                    Nisko
                                  </button>
                                </div>
                              </div>

                              {family.summary ? <p className="family-summary">{family.summary}</p> : null}
                              {family.keywords?.length ? (
                                <div className="axis-keywords">
                                  {family.keywords.slice(0, 6).map((keyword) => (
                                    <span key={`${family.familyId}-${keyword}`}>{keyword}</span>
                                  ))}
                                </div>
                              ) : null}

                              <label className="axis-family-importance">
                                <span>Znaczenie calej rodziny: {weightPercent(averageImportance)}</span>
                                <input
                                  type="range"
                                  min="0"
                                  max="100"
                                  step="1"
                                  value={averageImportance * 100}
                                  onChange={(event) => handleAxisFamilyImportanceChange(family.axes, event.target.value)}
                                />
                              </label>

                              <div className="axis-family-dimensions">
                                {family.axes.map((axis) => {
                                  const preference = axisPreferences.find((item) => item.axis_id === axis.axis_id) ?? {
                                    axis_id: axis.axis_id,
                                    axis_label: axis.label,
                                    mode: "neutral",
                                    importance: 0.5,
                                  };

                                  return (
                                    <article key={axis.axis_id} className="axis-preference-card">
                                      <div className="axis-card-head">
                                        <strong>{axis.label}</strong>
                                        <span>axis #{axis.axis_id + 1}</span>
                                      </div>
                                      {axis.summary ? <p>{axis.summary}</p> : null}
                                      {axis.keywords?.length ? (
                                        <div className="axis-keywords">
                                          {axis.keywords.slice(0, 6).map((keyword) => (
                                            <span key={`${axis.axis_id}-${keyword}`}>{keyword}</span>
                                          ))}
                                        </div>
                                      ) : null}
                                      <div className="axis-controls">
                                        <label>
                                          <span>Preferencja</span>
                                          <select value={preference.mode} onChange={(event) => handleAxisModeChange(axis.axis_id, event.target.value)}>
                                            <option value="neutral">Neutralnie</option>
                                            <option value="prefer_high">Preferuj wysoki wynik</option>
                                            <option value="prefer_low">Preferuj niski wynik</option>
                                          </select>
                                        </label>
                                        <label>
                                          <span>Znaczenie osi: {weightPercent(preference.importance)}</span>
                                          <input
                                            type="range"
                                            min="0"
                                            max="100"
                                            step="1"
                                            value={preference.importance * 100}
                                            onChange={(event) => handleAxisImportanceChange(axis.axis_id, event.target.value)}
                                          />
                                        </label>
                                      </div>
                                      {axis.examples?.length ? (
                                        <div className="axis-examples">
                                          <blockquote>{axis.examples[0]}</blockquote>
                                        </div>
                                      ) : null}
                                    </article>
                                  );
                                })}
                              </div>
                            </article>
                          );
                        })}
                      </div>
                    </>
                  ) : (
                    <p className="preset-description">
                      Wymiary pojawia sie automatycznie, gdy katalog ma juz policzony model wartosci z komentarzy.
                    </p>
                  )}
                </div>

                <div className="mini-grid">
                  <label>
                    <span>Priorytet rentownosci</span>
                    <select name="profitability_mode" value={form.profitability_mode} onChange={handleTextChange}>
                      <option value="prefer_high">Preferuj wysoka rentownosc</option>
                      <option value="neutral">Neutralnie</option>
                      <option value="prefer_low">Preferuj niska rentownosc</option>
                    </select>
                  </label>

                  <label>
                    <span>Priorytet techniczny</span>
                    <select name="technical_mode" value={form.technical_mode} onChange={handleTextChange}>
                      <option value="prefer_high">Preferuj mocniejszy sygnal techniczny</option>
                      <option value="neutral">Neutralnie</option>
                      <option value="prefer_low">Preferuj slabszy sygnal techniczny</option>
                    </select>
                  </label>
                </div>

                <label>
                  <span>Bias kapitalizacji</span>
                  <select name="market_cap_mode" value={form.market_cap_mode} onChange={handleTextChange}>
                    <option value="neutral">Neutralnie</option>
                    <option value="prefer_large">Preferuj duze spolki</option>
                    <option value="prefer_small">Preferuj mniejsze spolki</option>
                  </select>
                </label>

                <div className="mini-grid">
                  <label>
                    <span>Maksymalna waga jednej spolki</span>
                    <input
                      type="number"
                      min="0.05"
                      max="1"
                      step="0.01"
                      name="max_holding_weight"
                      value={form.max_holding_weight}
                      onChange={handleNumberChange}
                    />
                  </label>

                  <label>
                    <span>Maksymalnie spolek na kategorie</span>
                    <input
                      type="number"
                      min="0"
                      max="20"
                      name="max_companies_per_category"
                      value={form.max_companies_per_category}
                      onChange={handleNumberChange}
                    />
                  </label>
                </div>

                <label>
                  <span>Minimalna liczba kategorii</span>
                  <input
                    type="number"
                    min="1"
                    max="20"
                    name="min_distinct_categories"
                    value={form.min_distinct_categories}
                    onChange={handleNumberChange}
                  />
                </label>

                <label className="checkbox-row">
                  <input type="checkbox" name="strict_category_limit" checked={form.strict_category_limit} onChange={handleCheckboxChange} />
                  <span>Trzymaj scisly limit kategorii nawet kosztem mniejszej liczby pozycji</span>
                </label>

                <div className="weights-block">
                  <h3>Wagi scoringu</h3>

                  <label>
                    <span>Jakosc bazowa: {weightPercent(form.score_weights.base_quality)}</span>
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
                    <span>Rentownosc: {weightPercent(form.score_weights.profitability_alignment)}</span>
                    <input
                      type="range"
                      min="0"
                      max="100"
                      step="1"
                      name="profitability_alignment"
                      value={form.score_weights.profitability_alignment * 100}
                      onChange={handleWeightChange}
                    />
                  </label>

                  <label>
                    <span>Technikalia: {weightPercent(form.score_weights.technical_alignment)}</span>
                    <input
                      type="range"
                      min="0"
                      max="100"
                      step="1"
                      name="technical_alignment"
                      value={form.score_weights.technical_alignment * 100}
                      onChange={handleWeightChange}
                    />
                  </label>

                  <label>
                    <span>Kapitalizacja: {weightPercent(form.score_weights.market_cap_alignment)}</span>
                    <input type="range" min="0" max="100" step="1" name="market_cap_alignment" value={form.score_weights.market_cap_alignment * 100} onChange={handleWeightChange} />
                  </label>
                </div>

                <div className="action-row">
                  <button type="button" className="secondary-button" onClick={handleSaveProfile} disabled={loading || reporting || savingProfile || deletingProfile || catalogLoading}>
                    {savingProfile ? "Zapisywanie..." : selectedSavedProfileId ? "Aktualizuj zapisany profil" : "Zapisz profil do biblioteki"}
                  </button>
                  <button
                    type="button"
                    className="secondary-button danger-button"
                    onClick={handleDeleteProfile}
                    disabled={!selectedSavedProfileId || loading || reporting || savingProfile || deletingProfile || catalogLoading}
                  >
                    {deletingProfile ? "Usuwanie..." : "Usun zapisany profil"}
                  </button>
                </div>
              </div>
            </details>
          </form>
        </section>

        <section className="panel status-panel">
          <div className="panel-head">
            <h2>Stan danych</h2>
            <span className="badge ghost">Live from scrapper</span>
          </div>

          <div className="stats-grid">
            <article>
              <span className="stat-label">Kategorie</span>
              <strong>{catalog.categories_count}</strong>
            </article>
            <article>
              <span className="stat-label">Spolki w katalogu</span>
              <strong>{catalog.companies_count}</strong>
            </article>
            <article>
              <span className="stat-label">Custom ESG</span>
              <strong>{metrics?.custom_esg ? "gotowe" : "w budowie"}</strong>
            </article>
            <article>
              <span className="stat-label">Rentownosc</span>
              <strong>{metrics?.profitability ? "gotowe" : "brak danych"}</strong>
            </article>
            <article>
              <span className="stat-label">Technikalia</span>
              <strong>{metrics?.technicals ? "gotowe" : "brak danych"}</strong>
            </article>
            <article>
              <span className="stat-label">Profil aksjologiczny</span>
              <strong>{metrics?.axiological ? "gotowe" : "brak danych"}</strong>
            </article>
            <article>
              <span className="stat-label">Profile</span>
              <strong>{profiles.length}</strong>
            </article>
            <article>
              <span className="stat-label">Zapisane profile</span>
              <strong>{savedProfiles.length}</strong>
            </article>
            <article>
              <span className="stat-label">Rodziny komentarzy</span>
              <strong>{familyDefinitions.length || axisFamilies.length}</strong>
            </article>
            <article>
              <span className="stat-label">Osie komentarzy</span>
              <strong>{axisDefinitions.length}</strong>
            </article>
          </div>

          <div className="allocation-strip instrument-summary-strip">
            {instrumentUniverseDefinitions.map((item) => (
              <article key={`universe-${item.id}`} className="allocation-card">
                <strong>{item.label}</strong>
                <span>{item.companies_count} rekordow</span>
                <span>{item.default_selected ? "domyslnie wlaczone" : "domyslnie wylaczone"}</span>
              </article>
            ))}
          </div>

          {error ? <p className="error-box">{error}</p> : null}
          {reportStatus ? <p className="success-box">{reportStatus}</p> : null}
          {profileStatus ? <p className="success-box">{profileStatus}</p> : null}

          <p className="panel-copy">
            Ten panel pokazuje, na jakich danych aktualnie pracuje aplikacja. Jesli chcesz tylko zbudowac
            portfel, nie musisz nic tu zmieniac. Import CSV i priorytety uzupelniania danych sa schowane nizej
            jako sekcja robocza.
          </p>

          <div className="weights-inline">
            <span>Aktywne wagi:</span>
            <strong>jakosc {weightPercent(resolvedWeights.base_quality)}</strong>
            <strong>esg {weightPercent(resolvedWeights.esg_alignment)}</strong>
            <strong>kategoria {weightPercent(resolvedWeights.category_match)}</strong>
            <strong>rentownosc {weightPercent(resolvedWeights.profitability_alignment)}</strong>
            <strong>technika {weightPercent(resolvedWeights.technical_alignment)}</strong>
            <strong>cap {weightPercent(resolvedWeights.market_cap_alignment)}</strong>
          </div>

          <details className="details-card details-card-data">
            <summary>Panel roboczy: dane i import CSV</summary>
            <div className="details-body">
              <div className="ops-block">
                <div className="ops-head">
                  <h3>Operacje danych</h3>
                  <span>{dataLoading ? "ladowanie..." : "gotowe do importu CSV"}</span>
                </div>

                {dataStatusMessage ? <p className="success-box">{dataStatusMessage}</p> : null}

                <div className="ops-grid">
                  <article className="ops-card">
                <h4>Fundamenty</h4>
                <p>
                  template {fundamentalsStatus?.template_exists ? "tak" : "nie"} / input {fundamentalsStatus?.normalized_rows ?? 0} /
                  features {fundamentalsStatus?.feature_rows ?? 0}
                </p>
                <p>{fundamentalsStatus?.latest_source ? `zrodlo: ${fundamentalsStatus.latest_source}` : "zrodlo: n/d"}</p>
                <label>
                  <span>CSV fundamentals</span>
                  <input type="file" accept=".csv,text/csv" onChange={(event) => setFundamentalsFile(event.target.files?.[0] ?? null)} />
                </label>
                <label>
                  <span>Nazwa zrodla</span>
                  <input value={fundamentalsSourceName} onChange={(event) => setFundamentalsSourceName(event.target.value)} placeholder="np. Koyfin Export" />
                </label>
                <label>
                  <span>Data snapshotu</span>
                  <input value={fundamentalsAsOfDate} onChange={(event) => setFundamentalsAsOfDate(event.target.value)} placeholder="YYYY-MM-DD" />
                </label>
                <label className="checkbox-row">
                  <input type="checkbox" checked={fundamentalsReplace} onChange={(event) => setFundamentalsReplace(event.target.checked)} />
                  <span>Nadpisz puste i istniejace wartosci</span>
                </label>
                <button type="button" className="secondary-button" disabled={fundamentalsUploading || catalogLoading} onClick={() => handleDataUpload("fundamentals")}>
                  {fundamentalsUploading ? "Import..." : "Importuj fundamentals CSV"}
                </button>
                  </article>

                  <article className="ops-card">
                <h4>Technikalia</h4>
                <p>
                  template {technicalsStatus?.template_exists ? "tak" : "nie"} / input {technicalsStatus?.normalized_rows ?? 0} /
                  features {technicalsStatus?.feature_rows ?? 0}
                </p>
                <p>{technicalsStatus?.latest_source ? `zrodlo: ${technicalsStatus.latest_source}` : "zrodlo: n/d"}</p>
                <label>
                  <span>CSV technicals</span>
                  <input type="file" accept=".csv,text/csv" onChange={(event) => setTechnicalsFile(event.target.files?.[0] ?? null)} />
                </label>
                <label>
                  <span>Nazwa zrodla</span>
                  <input value={technicalsSourceName} onChange={(event) => setTechnicalsSourceName(event.target.value)} placeholder="np. Technical Export" />
                </label>
                <label>
                  <span>Data snapshotu</span>
                  <input value={technicalsAsOfDate} onChange={(event) => setTechnicalsAsOfDate(event.target.value)} placeholder="YYYY-MM-DD" />
                </label>
                <label className="checkbox-row">
                  <input type="checkbox" checked={technicalsReplace} onChange={(event) => setTechnicalsReplace(event.target.checked)} />
                  <span>Nadpisz puste i istniejace wartosci</span>
                </label>
                <button type="button" className="secondary-button" disabled={technicalsUploading || catalogLoading} onClick={() => handleDataUpload("technicals")}>
                  {technicalsUploading ? "Import..." : "Importuj technicals CSV"}
                </button>
                  </article>
                </div>

                <div className="worklist-grid">
                  <article className="worklist-card">
                <h4>Priorytet fundamentals</h4>
                <p>Najbardziej aktywne spolki bez rentownosci w datasecie.</p>
                <div className="worklist-list">
                  {fundamentalsWorklist.map((item) => (
                    <div key={`fund-${item.symbol}`} className="worklist-row">
                      <strong>{item.symbol}</strong>
                      <span>{item.posts_count} postow</span>
                      <span>{item.category}</span>
                    </div>
                  ))}
                </div>
                  </article>

                  <article className="worklist-card">
                <h4>Priorytet technicals</h4>
                <p>Najbardziej aktywne spolki bez technikaliow w datasecie.</p>
                <div className="worklist-list">
                  {technicalsWorklist.map((item) => (
                    <div key={`tech-${item.symbol}`} className="worklist-row">
                      <strong>{item.symbol}</strong>
                      <span>{item.posts_count} postow</span>
                      <span>{item.category}</span>
                    </div>
                  ))}
                </div>
                  </article>
                </div>
              </div>
            </div>
          </details>
        </section>

        <section className="panel result-panel">
          <div className="panel-head">
            <h2>Wynik i porownanie</h2>
            <span className="badge accent">{result ? `${result.holdings.length} pozycji` : "brak wyniku"}</span>
          </div>

          {!result ? (
            <div className="empty-state-card">
              <p className="empty-state">
                Po zbudowaniu portfela tutaj pojawi sie Twoj sklad, benchmark ESG-like i porownanie obu wersji.
              </p>
              <div className="summary-grid empty-summary-grid">
                <article>
                  <span className="stat-label">Rodziny ESG-like</span>
                  <strong>{filteredEsgFamilies.length}</strong>
                </article>
                <article>
                  <span className="stat-label">Zmienione rodziny</span>
                  <strong>{configuredFamilyCount}</strong>
                </article>
                <article>
                  <span className="stat-label">Kategorie rynku</span>
                  <strong>{selectedCategoryCount || "caly rynek"}</strong>
                </article>
                <article>
                  <span className="stat-label">Docelowy portfel</span>
                  <strong>{form.portfolio_size} spolek</strong>
                </article>
              </div>
              <p className="panel-copy">
                Jesli chcesz szybko zobaczyc efekt, zostaw pusty profil, ustaw 2-3 rodziny wartosci i kliknij
                <strong> Zbuduj portfel</strong>.
              </p>
            </div>
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
                      <p className="company-meta">
                        {company.custom_esg_proxy_score != null ? `custom ESG ${company.custom_esg_proxy_score.toFixed(2)}` : "custom ESG n/d"}
                        {company.custom_esg_metric_version ? ` / ${company.custom_esg_metric_version}` : ""}
                        {company.real_esg_total_score != null ? ` / real ESG ${company.real_esg_total_score.toFixed(2)}` : ""}
                        {company.real_esg_source ? ` / zrodlo ${company.real_esg_source}` : ""}
                        {company.profitability_score != null ? ` / profitability ${company.profitability_score.toFixed(2)}` : " / profitability n/d"}
                        {company.technical_score != null ? ` / technical ${company.technical_score.toFixed(2)}` : " / technical n/d"}
                        {company.avg_sentiment != null ? ` / avg sentyment ${company.avg_sentiment.toFixed(4)}` : ""}
                        {company.coverage_score != null ? ` / coverage ${company.coverage_score.toFixed(4)}` : ""}
                      </p>
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
      </main>
      </div>
    </div>
  );
}
