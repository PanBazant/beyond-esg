"""Logika walidacji wyników LLM — importowana przez 10c i testy."""
from __future__ import annotations

VALID_COVERAGE_VALUES = {"none", "marginal", "present", "dominant"}
VALID_SENTIMENT_VALUES = {"positive", "negative", "mixed", "neutral"}


def validate_llm_result(result: dict) -> dict:
    coverage = result.get("axiological_coverage", "none")
    if coverage not in VALID_COVERAGE_VALUES:
        coverage = "none"

    frames = result.get("frames") or []
    validated_frames = []
    for frame in frames:
        sentiment = frame.get("sentiment", "neutral")
        if sentiment not in VALID_SENTIMENT_VALUES:
            sentiment = "neutral"
        validated_frames.append({**frame, "sentiment": sentiment})

    return {
        "frames": validated_frames,
        "axiological_coverage": coverage,
        "notes": result.get("notes"),
    }
