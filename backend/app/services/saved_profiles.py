from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from ..schemas import SavedProfileCatalogResponse, SavedProfileDeleteResponse, SavedProfileRecord, SavedProfileUpsertRequest


ROOT_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT_DIR / "backend" / "data"
STORAGE_PATH = DATA_DIR / "custom_profiles.json"
SLUG_RE = re.compile(r"[^a-z0-9]+")


def _ensure_storage() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not STORAGE_PATH.exists():
        STORAGE_PATH.write_text("[]\n", encoding="utf-8")


def _slugify(value: str) -> str:
    return SLUG_RE.sub("-", value.strip().lower()).strip("-") or "custom-profile"


def _read_saved_profiles() -> list[SavedProfileRecord]:
    _ensure_storage()
    raw = STORAGE_PATH.read_text(encoding="utf-8").strip() or "[]"
    doc = json.loads(raw)
    profiles = [SavedProfileRecord(**item) for item in doc]
    profiles.sort(key=lambda item: (item.updated_at, item.created_at, item.profile_name), reverse=True)
    return profiles


def _write_saved_profiles(profiles: list[SavedProfileRecord]) -> None:
    _ensure_storage()
    payload = [item.model_dump() for item in profiles]
    STORAGE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_saved_profile_catalog() -> SavedProfileCatalogResponse:
    return SavedProfileCatalogResponse(saved_profiles=_read_saved_profiles())


def _generate_profile_id(profile_name: str, existing_ids: set[str]) -> str:
    base = _slugify(profile_name)
    candidate = base
    suffix = 2
    while candidate in existing_ids:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def upsert_saved_profile(payload: SavedProfileUpsertRequest) -> SavedProfileRecord:
    profiles = _read_saved_profiles()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    existing_ids = {item.profile_id for item in profiles}

    target_id = (payload.profile_id or "").strip() or None
    existing = next((item for item in profiles if item.profile_id == target_id), None) if target_id else None

    if existing is None:
        profile_id = _generate_profile_id(payload.profile_name, existing_ids)
        record = SavedProfileRecord(
            profile_id=profile_id,
            description=payload.description,
            created_at=now,
            updated_at=now,
            **payload.model_dump(exclude={"profile_id", "description"}),
        )
        profiles.append(record)
    else:
        updated = SavedProfileRecord(
            profile_id=existing.profile_id,
            description=payload.description,
            created_at=existing.created_at,
            updated_at=now,
            **payload.model_dump(exclude={"profile_id", "description"}),
        )
        profiles = [updated if item.profile_id == existing.profile_id else item for item in profiles]
        record = updated

    _write_saved_profiles(profiles)
    return record


def delete_saved_profile(profile_id: str) -> SavedProfileDeleteResponse:
    profiles = _read_saved_profiles()
    remaining = [item for item in profiles if item.profile_id != profile_id]
    deleted = len(remaining) != len(profiles)
    if deleted:
        _write_saved_profiles(remaining)
    return SavedProfileDeleteResponse(profile_id=profile_id, deleted=deleted)
