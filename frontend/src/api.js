const defaultApiBase =
  typeof window !== "undefined" ? `${window.location.origin}/api/v1` : "http://localhost:8000/api/v1";

const API_BASE = import.meta.env.VITE_API_BASE ?? defaultApiBase;

async function parseResponse(response) {
  if (!response.ok) {
    const text = await response.text();
    let message = text || `HTTP ${response.status}`;
    try {
      const json = JSON.parse(text);
      message = json.detail ?? json.message ?? message;
    } catch {}
    throw new Error(message);
  }

  return response.json();
}

async function fileToBase64(file) {
  const buffer = await file.arrayBuffer();
  let binary = "";
  const bytes = new Uint8Array(buffer);
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    const chunk = bytes.subarray(index, index + chunkSize);
    binary += String.fromCharCode(...chunk);
  }
  return window.btoa(binary);
}

export async function fetchCatalog() {
  const response = await fetch(`${API_BASE}/catalog`);
  return parseResponse(response);
}

export async function fetchDataStatus() {
  const response = await fetch(`${API_BASE}/data/status`);
  return parseResponse(response);
}

export async function fetchDataWorklist(kind, params = {}) {
  const search = new URLSearchParams();
  if (params.min_posts != null) search.set("min_posts", String(params.min_posts));
  if (params.limit != null) search.set("limit", String(params.limit));
  if (params.only_missing != null) search.set("only_missing", String(params.only_missing));
  const query = search.toString();
  const response = await fetch(`${API_BASE}/data/worklists/${kind}${query ? `?${query}` : ""}`);
  return parseResponse(response);
}

export async function fetchProfiles() {
  const response = await fetch(`${API_BASE}/profiles`);
  return parseResponse(response);
}

export async function fetchSavedProfiles() {
  const response = await fetch(`${API_BASE}/profiles/saved`);
  return parseResponse(response);
}

export async function saveProfile(payload) {
  const response = await fetch(`${API_BASE}/profiles/saved`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return parseResponse(response);
}

export async function deleteProfile(profileId) {
  const response = await fetch(`${API_BASE}/profiles/saved/${profileId}`, {
    method: "DELETE",
  });

  return parseResponse(response);
}

export async function buildPortfolioPreview(payload) {
  const response = await fetch(`${API_BASE}/portfolio/preview`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return parseResponse(response);
}

export async function exportPortfolioReport(payload) {
  const response = await fetch(`${API_BASE}/portfolio/report`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return parseResponse(response);
}

export async function fetchMarketData(symbol, period = "1y") {
  const response = await fetch(`${API_BASE}/company/${encodeURIComponent(symbol)}/market-data?period=${period}`);
  return parseResponse(response);
}

export async function importRawData(kind, { file, source_name, as_of_date, replace = false }) {
  const file_content_base64 = await fileToBase64(file);
  const response = await fetch(`${API_BASE}/data/import/${kind}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      file_name: file.name,
      file_content_base64,
      source_name,
      as_of_date,
      replace,
    }),
  });

  return parseResponse(response);
}
