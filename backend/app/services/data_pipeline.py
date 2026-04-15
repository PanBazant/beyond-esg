from __future__ import annotations

import base64
import binascii
import csv
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

from ..schemas import (
    DataPipelineKind,
    DataPipelineStatus,
    DataStatusResponse,
    DataWorklistEntry,
    DataWorklistResponse,
    RawDataImportRequest,
    RawDataImportResponse,
)
from .datasets import load_company_records


ROOT_DIR = Path(__file__).resolve().parents[3]
ANALYSIS_DIR = ROOT_DIR / "analiza"
INPUT_DIR = ANALYSIS_DIR / "input"
RAW_DIR = INPUT_DIR / "raw"
UPLOADS_DIR = RAW_DIR / "uploads"
OUT_DIR = ANALYSIS_DIR / "out"

MASTER_DATASET_PATH = OUT_DIR / "company_master_dataset.jsonl"
MASTER_SCRIPT_PATH = ANALYSIS_DIR / "03_build_company_master_dataset.py"

FUNDAMENTALS_TEMPLATE_PATH = INPUT_DIR / "company_fundamentals_template.csv"
FUNDAMENTALS_INPUT_PATH = INPUT_DIR / "company_fundamentals.csv"
FUNDAMENTALS_REPORT_PATH = OUT_DIR / "company_fundamentals_import_report.json"
FUNDAMENTALS_FEATURES_PATH = OUT_DIR / "company_profitability_features.jsonl"
FUNDAMENTALS_SUMMARY_PATH = OUT_DIR / "company_profitability_features_summary.json"
FUNDAMENTALS_WORKLIST_PATH = INPUT_DIR / "fundamentals_worklist.csv"
TECHNICALS_WORKLIST_PATH = INPUT_DIR / "technicals_worklist.csv"
FUNDAMENTALS_IMPORT_SCRIPT = ANALYSIS_DIR / "05_import_fundamentals_raw.py"
FUNDAMENTALS_BUILD_SCRIPT = ANALYSIS_DIR / "04_build_profitability_features.py"

TECHNICALS_TEMPLATE_PATH = INPUT_DIR / "company_technicals_template.csv"
TECHNICALS_INPUT_PATH = INPUT_DIR / "company_technicals.csv"
TECHNICALS_REPORT_PATH = OUT_DIR / "company_technicals_import_report.json"
TECHNICALS_FEATURES_PATH = OUT_DIR / "company_technical_features.jsonl"
TECHNICALS_SUMMARY_PATH = OUT_DIR / "company_technical_features_summary.json"
TECHNICALS_IMPORT_SCRIPT = ANALYSIS_DIR / "08_import_technicals_raw.py"
TECHNICALS_BUILD_SCRIPT = ANALYSIS_DIR / "07_build_technical_features.py"


def _ensure_dirs() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _count_jsonl_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def _count_csv_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def _load_latest_metadata(path: Path) -> tuple[str | None, str | None]:
    if not path.exists():
        return None, None

    latest_source = None
    latest_date = None
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            source = (row.get("source") or "").strip() or None
            as_of_date = (row.get("as_of_date") or "").strip() or None
            if source:
                latest_source = source
            if as_of_date:
                latest_date = as_of_date
    return latest_source, latest_date


def _build_pipeline_status(kind: DataPipelineKind) -> DataPipelineStatus:
    if kind == "fundamentals":
        template_path = FUNDAMENTALS_TEMPLATE_PATH
        input_path = FUNDAMENTALS_INPUT_PATH
        feature_path = FUNDAMENTALS_FEATURES_PATH
        report_path = FUNDAMENTALS_REPORT_PATH
        summary_path = FUNDAMENTALS_SUMMARY_PATH
    else:
        template_path = TECHNICALS_TEMPLATE_PATH
        input_path = TECHNICALS_INPUT_PATH
        feature_path = TECHNICALS_FEATURES_PATH
        report_path = TECHNICALS_REPORT_PATH
        summary_path = TECHNICALS_SUMMARY_PATH

    latest_source, latest_date = _load_latest_metadata(input_path)
    return DataPipelineStatus(
        kind=kind,
        template_exists=template_path.exists(),
        normalized_input_exists=input_path.exists(),
        normalized_rows=_count_csv_rows(input_path),
        feature_rows=_count_jsonl_rows(feature_path),
        report_exists=report_path.exists(),
        summary_exists=summary_path.exists(),
        latest_source=latest_source,
        latest_as_of_date=latest_date,
        report_path=str(report_path) if report_path.exists() else None,
        summary_path=str(summary_path) if summary_path.exists() else None,
    )


def build_data_status() -> DataStatusResponse:
    _ensure_dirs()
    upload_files = sorted([item.name for item in UPLOADS_DIR.iterdir() if item.is_file()], reverse=True)
    return DataStatusResponse(
        master_dataset_exists=MASTER_DATASET_PATH.exists(),
        master_rows=_count_jsonl_rows(MASTER_DATASET_PATH),
        raw_upload_dir=str(UPLOADS_DIR),
        raw_upload_files=upload_files[:20],
        fundamentals=_build_pipeline_status("fundamentals"),
        technicals=_build_pipeline_status("technicals"),
    )


def build_data_worklist(kind: DataPipelineKind, *, min_posts: int = 30, limit: int = 100, only_missing: bool = True) -> DataWorklistResponse:
    companies = load_company_records()
    filtered = [company for company in companies if int(company.get("posts_count") or 0) >= min_posts]

    if kind == "fundamentals" and only_missing:
        filtered = [company for company in filtered if company.get("profitability_score") is None]
    if kind == "technicals" and only_missing:
        filtered = [company for company in filtered if company.get("technical_score") is None]

    filtered.sort(
        key=lambda item: (
            -(int(item.get("posts_count") or 0)),
            int(item.get("rank_in_category") or 999999),
            str(item.get("symbol") or ""),
        )
    )
    rows = filtered[:limit]

    worklist_path = FUNDAMENTALS_WORKLIST_PATH if kind == "fundamentals" else TECHNICALS_WORKLIST_PATH
    with worklist_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "symbol",
                "company_name",
                "category",
                "industry",
                "instrument_universe",
                "instrument_universe_label",
                "posts_count",
                "custom_esg_proxy_score",
                "market_cap_label",
                "rank_in_category",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "symbol": row.get("symbol"),
                    "company_name": row.get("company_name"),
                    "category": row.get("category"),
                    "industry": row.get("industry"),
                    "instrument_universe": row.get("instrument_universe"),
                    "instrument_universe_label": row.get("instrument_universe_label"),
                    "posts_count": row.get("posts_count"),
                    "custom_esg_proxy_score": row.get("custom_esg_proxy_score"),
                    "market_cap_label": row.get("market_cap_label"),
                    "rank_in_category": row.get("rank_in_category"),
                }
            )

    return DataWorklistResponse(
        kind=kind,
        min_posts=min_posts,
        limit=limit,
        only_missing=only_missing,
        output_file=str(worklist_path),
        rows=[
            DataWorklistEntry(
                symbol=str(row.get("symbol") or ""),
                company_name=str(row.get("company_name") or row.get("symbol") or ""),
                category=str(row.get("category") or "Unknown"),
                industry=row.get("industry"),
                instrument_universe=str(row.get("instrument_universe") or "ambiguous"),
                instrument_universe_label=str(row.get("instrument_universe_label") or "Niejednoznaczne"),
                posts_count=int(row.get("posts_count") or 0),
                custom_esg_proxy_score=float(row["custom_esg_proxy_score"]) if row.get("custom_esg_proxy_score") is not None else None,
                market_cap_label=row.get("market_cap_label"),
                rank_in_category=int(row["rank_in_category"]) if row.get("rank_in_category") is not None else None,
            )
            for row in rows
        ],
    )


def _run_script(script_path: Path, *args: str) -> None:
    process = subprocess.run(
        [sys.executable, str(script_path), *args],
        cwd=str(ROOT_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if process.returncode != 0:
        message = process.stderr.strip() or process.stdout.strip() or f"Script failed: {script_path.name}"
        raise HTTPException(status_code=500, detail=message)


def _ensure_template_for_kind(kind: DataPipelineKind) -> None:
    if kind == "fundamentals":
        if not FUNDAMENTALS_TEMPLATE_PATH.exists() and not FUNDAMENTALS_INPUT_PATH.exists():
            _run_script(FUNDAMENTALS_BUILD_SCRIPT)
    else:
        if not TECHNICALS_TEMPLATE_PATH.exists() and not TECHNICALS_INPUT_PATH.exists():
            _run_script(TECHNICALS_BUILD_SCRIPT)


def _safe_upload_name(file_name: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {".", "-", "_"} else "-" for char in file_name.strip())
    cleaned = cleaned.strip(".-_") or "upload.csv"
    if not cleaned.lower().endswith(".csv"):
        cleaned = f"{cleaned}.csv"
    return cleaned[:180]


def import_raw_data(kind: DataPipelineKind, payload: RawDataImportRequest) -> RawDataImportResponse:
    _ensure_dirs()
    _ensure_template_for_kind(kind)

    try:
        raw_bytes = base64.b64decode(payload.file_content_base64.encode("utf-8"), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Nie udalo sie zdekodowac pliku CSV: {exc}") from exc

    if not raw_bytes.strip():
        raise HTTPException(status_code=400, detail="Wgrany plik jest pusty.")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_name = _safe_upload_name(payload.file_name)
    saved_file = UPLOADS_DIR / f"{kind}-{timestamp}-{safe_name}"
    saved_file.write_bytes(raw_bytes)

    if kind == "fundamentals":
        import_script = FUNDAMENTALS_IMPORT_SCRIPT
        build_script = FUNDAMENTALS_BUILD_SCRIPT
        report_path = FUNDAMENTALS_REPORT_PATH
        summary_path = FUNDAMENTALS_SUMMARY_PATH
    else:
        import_script = TECHNICALS_IMPORT_SCRIPT
        build_script = TECHNICALS_BUILD_SCRIPT
        report_path = TECHNICALS_REPORT_PATH
        summary_path = TECHNICALS_SUMMARY_PATH

    import_args = ["--input-file", str(saved_file)]
    if payload.source_name:
        import_args.extend(["--source-name", payload.source_name])
    if payload.as_of_date:
        import_args.extend(["--as-of-date", payload.as_of_date])
    if payload.replace:
        import_args.append("--replace")

    _run_script(import_script, *import_args)
    _run_script(build_script)
    _run_script(MASTER_SCRIPT_PATH)

    return RawDataImportResponse(
        kind=kind,
        saved_file=str(saved_file),
        import_report=_load_json(report_path),
        feature_summary=_load_json(summary_path),
        master_summary=_load_json(OUT_DIR / "company_master_summary.json"),
        status=_build_pipeline_status(kind),
    )
