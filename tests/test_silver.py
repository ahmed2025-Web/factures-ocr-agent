"""Tests de l'étape 4 (couche silver). Lancer : python -m pytest tests/test_silver.py"""

import datetime
from decimal import Decimal

import duckdb

from src.silver import normalize as nz
from src.silver.parser import parse_invoice
from src.silver.pipeline import transform, write_parquet
from tests.conftest import bronze_record


# --- normalize ----------------------------------------------------------------
def test_montants_formats_varies():
    assert nz.parse_money("1 261,21 €") == Decimal("1261.21")
    assert nz.parse_money("6 306,05 €") == Decimal("6306.05")   # espace fine insécable
    assert nz.parse_money("6 306,05 ·") == Decimal("6306.05")        # € mal décodé (pypdf)
    assert nz.parse_money("1,234.50") == Decimal("1234.50")
    assert nz.parse_money("illisible") is None


def test_montants_sont_des_decimal_exacts():
    total = sum(nz.parse_money(x) for x in ["0,10", "0,20"])
    assert total == Decimal("0.30")   # avec des float : 0.30000000000000004


def test_dates():
    assert nz.parse_date("29/04/2025") == datetime.date(2025, 4, 29)
    assert nz.parse_date("29 avril 2025") == datetime.date(2025, 4, 29)
    assert nz.parse_date("31/02/2025") is None   # on ne devine pas


def test_iban_et_siret():
    assert nz.iban_ok("FR1578820812191361939909169")
    assert not nz.iban_ok("FR1578820812191361939909168")
    assert nz.luhn_ok("77360260298050")


# --- parser -------------------------------------------------------------------
def _check_A_2025_0003(f):
    assert f.numero_facture == "A-2025-0003"
    assert f.fournisseur == "Aubry"
    assert f.client == "Dumas"
    assert f.date_emission == datetime.date(2025, 4, 29)
    assert f.date_echeance == datetime.date(2025, 6, 13)
    assert f.statut == "En retard"
    assert f.categorie == "Conseil"
    assert (f.total_ht, f.total_tva, f.total_ttc) == (
        Decimal("6306.05"), Decimal("1261.21"), Decimal("7567.26"))
    assert len(f.lignes) == 1
    l = f.lignes[0]
    assert l.designation == "Formation DuckDB et Parquet"
    assert (l.quantite, l.prix_unitaire_ht, l.taux_tva, l.total_ht) == (
        Decimal("5"), Decimal("1261.21"), Decimal("20.00"), Decimal("6306.05"))


def test_parse_sortie_ocr(ocr_text):
    f = parse_invoice(ocr_text)
    _check_A_2025_0003(f)
    assert f.iban == "FR1578820812191361939909169"
    assert f.mode_paiement == "Chèque"


def test_parse_texte_natif(natif_text):
    _check_A_2025_0003(parse_invoice(natif_text))


def test_parse_tableau_markdown(ocr_text):
    import re
    md = ("| Désignation | Qté | Prix unitaire HT | TVA | Total HT |\n|---|---|---|---|---|\n"
          "| Formation DuckDB et Parquet | 5 | 1 261,21 € | 20 % | 6 306,05 € |\n")
    text = re.sub(r"<table.*?</table>", md, ocr_text, flags=re.S)
    _check_A_2025_0003(parse_invoice(text))


def test_texte_vide():
    assert parse_invoice("").numero_facture is None


# --- contrôles + pipeline ------------------------------------------------------
def test_facture_valide(ocr_text):
    out = transform([bronze_record(ocr_text, "facture_A-2025-0003_scan.pdf")])
    (fac,) = out["factures"]
    # Le SIRET client de cet exemple ne passe pas la clé de Luhn : c'est signalé.
    assert fac["anomalies"] == "siret_invalide"
    assert fac["statut_qualite"] == "signalee"
    assert out["quarantaine"] == []
    assert len(out["lignes"]) == 1


def test_montant_incoherent_signale(ocr_text):
    faux = ocr_text.replace("**Total TTC** 7 567,26 €", "**Total TTC** 7 567,28 €")
    (fac,) = transform([bronze_record(faux, "x.pdf")])["factures"]
    assert "ht_plus_tva_neq_ttc" in fac["anomalies"]
    assert fac["total_ttc"] == Decimal("7567.28")   # valeur lue, pas « corrigée »


def test_ligne_incoherente_signalee(ocr_text):
    faux = ocr_text.replace("<td>5</td>", "<td>4</td>")
    (fac,) = transform([bronze_record(faux, "x.pdf")])["factures"]
    assert "ligne_qte_x_pu_neq_total" in fac["anomalies"]


def test_rejet_avec_motif(ocr_text):
    illisible = ocr_text.replace("A-2025-0003", "")
    out = transform([bronze_record(illisible, "abime.pdf")])
    assert out["factures"] == []
    (q,) = out["quarantaine"]
    assert q["motif"] == "champ_obligatoire_manquant"
    assert "numero_facture" in q["details"]


def test_doublon_ecarte_texte_natif_prefere(ocr_text, natif_text):
    out = transform([
        bronze_record(ocr_text, "facture_A-2025-0003_scan.pdf", "ocr"),
        bronze_record(natif_text, "facture_A-2025-0003_texte.pdf", "pdf_text"),
    ])
    (fac,) = out["factures"]
    assert fac["source_key"] == "facture_A-2025-0003_texte.pdf"
    (q,) = out["quarantaine"]
    assert q["motif"] == "doublon" and q["source_key"].endswith("_scan.pdf")


def test_aucune_facture_perdue(ocr_text, natif_text):
    records = [bronze_record(ocr_text, "a.pdf"), bronze_record(natif_text, "b.pdf", "pdf_text"),
               bronze_record("n'importe quoi", "c.pdf")]
    out = transform(records)
    assert len(out["factures"]) + len(out["quarantaine"]) == len(records)


def test_parquet_types(tmp_path, ocr_text):
    write_parquet(transform([bronze_record(ocr_text, "a.pdf")]), str(tmp_path))
    con = duckdb.connect()
    types = dict(con.execute(
        f"SELECT column_name, column_type FROM (DESCRIBE SELECT * FROM '{tmp_path}/factures.parquet')"
    ).fetchall())
    assert types["total_ttc"] == "DECIMAL(14,2)"
    assert types["date_emission"] == "DATE"
    assert con.execute(f"SELECT total_ttc FROM '{tmp_path}/factures.parquet'").fetchone()[0] == Decimal("7567.26")
