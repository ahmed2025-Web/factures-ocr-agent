"""Tests de l'étape 6 (entrepôt)."""

import os
import subprocess
import sys
from decimal import Decimal

import duckdb

from src import warehouse
from src.warehouse.__main__ import build_file


def test_vues_bronze_silver_gold(data_root):
    con = warehouse.connect(data_root)
    vues = {tuple(r) for r in con.execute(
        "SELECT table_schema, table_name FROM information_schema.tables").fetchall()}
    assert {("bronze", "documents"), ("silver", "factures"), ("silver", "lignes"),
            ("silver", "quarantaine"), ("gold", "ca_mensuel"), ("gold", "encours_fournisseur")} <= vues


def test_requete_sql_silver(data_root):
    con = warehouse.connect(data_root)
    n, ttc = con.execute("SELECT count(*), sum(total_ttc) FROM silver.factures "
                         "WHERE statut = 'En retard' AND year(date_emission) = 2025").fetchone()
    assert (n, ttc) == (1, Decimal("7567.26"))
    assert con.execute("SELECT count(*) FROM bronze.documents").fetchone()[0] == 4
    assert con.execute("SELECT motif FROM silver.quarantaine").fetchall() == [("champ_obligatoire_manquant",)]


def test_donnees_en_un_seul_exemplaire(data_root, tmp_path):
    """Le fichier .duckdb ne contient que des vues : il reste minuscule et sans table."""
    os.environ["DATA_ROOT"] = data_root
    try:
        path = build_file(str(tmp_path / "entrepot.duckdb"))
    finally:
        del os.environ["DATA_ROOT"]
    con = duckdb.connect(path, read_only=True)
    types = {r[0] for r in con.execute("SELECT table_type FROM information_schema.tables").fetchall()}
    assert types == {"VIEW"}
    assert con.execute("SELECT count(*) FROM silver.factures").fetchone()[0] == 3


def test_outil_graphique_ne_bloque_pas_les_programmes(data_root, tmp_path):
    """Un autre processus ouvre le fichier en écriture (pire cas « DBeaver ») :
    les programmes, qui passent par connect(), continuent de fonctionner."""
    os.environ["DATA_ROOT"] = data_root
    try:
        path = build_file(str(tmp_path / "entrepot.duckdb"))
    finally:
        del os.environ["DATA_ROOT"]
    holder = subprocess.Popen(
        [sys.executable, "-c",
         f"import duckdb,time; c=duckdb.connect({path!r}); print('ok', flush=True); time.sleep(30)"],
        stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "ok"   # le fichier est verrouillé par l'autre processus
        con = warehouse.connect(data_root)
        assert con.execute("SELECT count(*) FROM silver.factures").fetchone()[0] == 3
    finally:
        holder.kill()


def test_gold_encours(data_root):
    con = warehouse.connect(data_root)
    rows = dict(con.execute("SELECT fournisseur, encours_ttc FROM gold.encours_fournisseur").fetchall())
    assert rows == {"Aubry": Decimal("7567.26"), "Bernard SA": Decimal("7567.26")}
