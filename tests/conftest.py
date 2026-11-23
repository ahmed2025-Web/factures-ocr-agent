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


def make_native_pdf(path: str, numero: str = "A-2025-0003") -> str:
    """Fabrique un PDF natif (avec couche texte) qui reprend la facture d'exemple."""
    import pymupdf

    lignes = ["FACTURE", "Aubry", "96, avenue de Meyer", "24403 Boyer",
              "SIRET : 77360260298050", "TVA intracom. : FR09773602602",
              f"Numéro de facture : {numero}", "Date d'émission : 29/04/2025",
              "Date d'échéance : 13/06/2025", "Catégorie : Conseil", "Statut : En retard",
              "Facturé à :", "Client : Dumas", "4, chemin Roger Muller", "97345 Clerc",
              "SIRET client : 16073375486850"]
    doc = pymupdf.open()
    page = doc.new_page()
    y = 50
    for text in lignes:
        page.insert_text((50, y), text)
        y += 16
    y += 10
    for row in (["Désignation", "Qté", "Prix unitaire HT", "TVA", "Total HT"],
                ["Formation DuckDB et Parquet", "5", "1 261,21 €", "20 %", "6 306,05 €"]):
        for x, text in zip([50, 250, 300, 400, 470], row):
            page.insert_text((x, y), text)
        y += 16
    y += 14
    for text in ["Total HT 6 306,05 €", "TVA 20 % 1 261,21 €", "Total TTC 7 567,26 €",
                 "Mode de paiement : Chèque", "IBAN : FR1578820812191361939909169"]:
        page.insert_text((350 if text.startswith(("Total", "TVA")) else 50, y), text)
        y += 16
    doc.save(path)
    return path
