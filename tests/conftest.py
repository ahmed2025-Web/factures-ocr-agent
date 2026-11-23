"""Outils communs aux tests : fabriquer des enregistrements bronze à partir des fixtures."""

import os

import pytest

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture_text(name: str) -> str:
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return fh.read()


def bronze_record(text: str, source_key: str, method: str = "ocr", sha: str | None = None) -> dict:
    return {
        "source_key": source_key,
        "source_sha256": sha or ("sha-" + source_key),
        "extraction_method": method,
        "ingested_at": "2026-11-20T10:00:00",
        "status": "ok",
        "text": text,
    }


@pytest.fixture
def ocr_text():
    return fixture_text("ocr_A-2025-0003.md")


@pytest.fixture
def natif_text():
    return fixture_text("natif_A-2025-0003.txt")
