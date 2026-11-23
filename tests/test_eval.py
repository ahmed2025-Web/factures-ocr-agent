"""Tests de l'étape 5 (évaluation OCR), sans appel réseau : l'OCR est simulé."""

import pytest

from src.eval import ocr_eval, truth
from tests.conftest import make_native_pdf, fixture_text


@pytest.fixture
def setup(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    raw.mkdir()
    make_native_pdf(str(raw / "facture_A-2025-0003_texte.pdf"))
    monkeypatch.setattr(truth, "TRUTH_CSV", str(tmp_path / "verite.csv"))
    monkeypatch.setattr(ocr_eval, "load_truth", lambda: truth.load_truth(str(tmp_path / "verite.csv")))
    monkeypatch.setattr(ocr_eval, "CACHE_DIR", str(tmp_path / "cache"))
    return raw, tmp_path


def _fake_ocr(monkeypatch, text_by_dpi):
    import src.ocr.client as client
    monkeypatch.setattr(client, "ocr_pdf_page", lambda path, page_index=0, dpi=200: (text_by_dpi[dpi], 1.5))


def test_verite_terrain_depuis_pdf_natif(setup):
    raw, tmp = setup
    assert truth.build_from_native(str(raw), str(tmp / "verite.csv")) == 1
    (row,) = truth.load_truth(str(tmp / "verite.csv"))
    assert row["numero_facture"] == "A-2025-0003"
    assert row["total_ttc"] == "7567.26"
    assert row["origine"] == "natif_rasterise"
    # relancer n'ajoute rien (idempotent)
    assert truth.build_from_native(str(raw), str(tmp / "verite.csv")) == 0


def test_precision_par_champ_deux_reglages(setup, monkeypatch):
    raw, tmp = setup
    truth.build_from_native(str(raw), str(tmp / "verite.csv"))
    bon = fixture_text("ocr_A-2025-0003.md")
    abime = bon.replace("7 567,26", "7 561,26").replace("Dumas", "Dumos")
    _fake_ocr(monkeypatch, {300: bon, 100: abime})

    res = ocr_eval.evaluate([300, 100], raw_dir=str(raw), use_cache=False)
    assert res[300]["fields"]["total_ttc"] == [1, 1]
    assert res[100]["fields"]["total_ttc"] == [0, 1]
    assert res[100]["fields"]["client"] == [0, 1]
    assert res[100]["fields"]["numero_facture"] == [1, 1]
    assert {e[1] for e in res[100]["errors"]} == {"total_ttc", "client"}
    table = ocr_eval.report(res)
    assert "| `total_ttc` | 100 % (1/1" in table and "300 DPI" in table


def test_cache_evite_un_second_appel(setup, monkeypatch):
    raw, tmp = setup
    calls = []
    import src.ocr.client as client
    monkeypatch.setattr(client, "ocr_pdf_page",
                        lambda *a, **k: calls.append(1) or (fixture_text("ocr_A-2025-0003.md"), 2.0))
    pdf = str(raw / "facture_A-2025-0003_texte.pdf")
    ocr_eval.ocr_text(pdf, 200)
    ocr_eval.ocr_text(pdf, 200)
    assert len(calls) == 1


def test_comparaison_stricte():
    assert ocr_eval.same("total_ttc", "7567.26", "7567.260")
    assert not ocr_eval.same("total_ttc", "7567.26", "7567.27")
    assert ocr_eval.same("client", "Dumas", " Dumas ")


def test_intervalle_wilson():
    lo, hi = ocr_eval.wilson(9, 10)
    assert 0.55 < lo < 0.6 and 0.98 < hi <= 1.0
