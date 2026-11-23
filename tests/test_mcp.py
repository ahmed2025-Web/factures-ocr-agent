"""Tests de l'étape 7 : un vrai client MCP lance le serveur (stdio) et appelle
CHAQUE outil, puis on vérifie qu'aucune écriture n'est possible.

    python -m pytest tests/test_mcp.py -v
"""

import os
import sys
import json
import asyncio
import hashlib
import glob
from decimal import Decimal

import pytest
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def call_all(data_root: str, calls: list[tuple[str, dict]]) -> tuple[list, list]:
    """Lance le serveur, liste ses outils, exécute les appels. Retourne (noms d'outils, résultats)."""
    params = StdioServerParameters(command=sys.executable, args=["-m", "src.mcp_server.server"],
                                   cwd=ROOT, env={**os.environ, "DATA_ROOT": data_root})

    async def run():
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                names = [t.name for t in (await s.list_tools()).tools]
                out = []
                for name, args in calls:
                    res = await s.call_tool(name, args)
                    out.append(json.loads(res.content[0].text))
                return names, out

    return asyncio.run(run())


@pytest.fixture(scope="module")
def root(tmp_path_factory):
    from tests.conftest import build_data_root
    return build_data_root(tmp_path_factory.mktemp("mcp") / "data")


def test_chaque_outil(root):
    names, (lst, tot, grp, det, absent, schema, sql, gold) = call_all(root, [
        ("lister_factures", {"fournisseur": "aubry"}),
        ("compter_et_totaliser", {"statut": "en retard", "annee": 2025}),
        ("compter_et_totaliser", {"regrouper_par": "fournisseur"}),
        ("detail_facture", {"numero_facture": "a-2025-0003"}),
        ("detail_facture", {"numero_facture": "Z-9999"}),
        ("decrire_schema", {}),
        ("requete_sql", {"sql": "SELECT count(*) AS n FROM silver.lignes"}),
        ("indicateur_gold", {"indicateur": "encours_fournisseur"}),
    ])
    assert set(names) == {"lister_factures", "compter_et_totaliser", "detail_facture",
                          "decrire_schema", "requete_sql", "indicateur_gold"}

    assert lst["nb_factures_correspondantes"] == 2
    assert {f["numero_facture"] for f in lst["factures"]} == {"A-2025-0003", "A-2025-0007"}

    # La question de l'énoncé : montant TTC des factures en retard en 2025.
    assert tot["nb_factures"] == 1 and Decimal(tot["total_ttc"]) == Decimal("7567.26")

    assert {g["fournisseur"]: g["nb_factures"] for g in grp["groupes"]} == {"Aubry": 2, "Bernard SA": 1}

    assert det["facture"]["fournisseur"] == "Aubry"
    assert det["lignes"][0]["designation"] == "Formation DuckDB et Parquet"
    assert "erreur" in absent and "conseil" in absent

    assert "silver.factures" in schema["tables"] and "En retard" in schema["valeurs_statut"]
    assert sql["lignes"] == [{"n": 3}]
    assert len(gold["lignes"]) == 2

    # Transparence : chaque réponse cite le SQL réellement exécuté.
    for r in (lst, tot, grp, det, absent, schema, sql, gold):
        assert r["sql_executees"] and all("sql" in t for t in r["sql_executees"])
    # Filtres paramétrés : la valeur n'est pas dans le SQL, elle est à part.
    assert "aubry" not in lst["sql_executees"][0]["sql"].lower()
    assert lst["sql_executees"][0]["parametres"] == ["aubry"]


ATTAQUES = [
    "DROP VIEW silver.factures",
    "DELETE FROM silver.factures",
    "UPDATE silver.factures SET total_ttc = 0",
    "INSERT INTO silver.factures SELECT * FROM silver.factures",
    "CREATE TABLE pirate AS SELECT 1",
    "SELECT 1; DROP VIEW silver.factures",
    "COPY silver.factures TO 'silver/factures.parquet'",
    "COPY (SELECT 1 AS x) TO 'silver/factures.parquet' (FORMAT parquet)",
    "ATTACH '/tmp/autre.duckdb' AS autre",
    "SET lock_configuration = false",
    "SET enable_external_access = true",
    "INSTALL httpfs",
    "PRAGMA database_list",
    "SELECT * FROM read_text('/etc/passwd')",
    f"SELECT * FROM read_text('{ROOT}/.env.example')",
    "SELECT * FROM query('DROP VIEW silver.factures')",
    "EXPORT DATABASE '/tmp/export'",
]


def _silver_fingerprint(root):
    return {p: hashlib.sha256(open(p, "rb").read()).hexdigest()
            for p in sorted(glob.glob(os.path.join(root, "silver", "*")))}


def test_aucune_modification_possible(root):
    before = _silver_fingerprint(root)
    calls = [("requete_sql", {"sql": a}) for a in ATTAQUES]
    # Injection via un filtre : la valeur est un paramètre, donc inoffensive.
    calls += [("lister_factures", {"fournisseur": "x'); DROP VIEW silver.factures; --"}),
              ("detail_facture", {"numero_facture": "' OR 1=1 --"}),
              ("lister_factures", {"tri": "total_ttc; DROP VIEW silver.factures"}),
              ("compter_et_totaliser", {"regrouper_par": "1); DROP VIEW silver.factures; --"}),
              ("requete_sql", {"sql": "SELECT count(*) AS n FROM silver.factures"})]
    _, results = call_all(root, calls)

    for attaque, res in zip(ATTAQUES, results):
        assert "erreur" in res, f"non bloqué : {attaque}"
    inj_filtre, inj_detail, inj_tri, inj_group, final = results[len(ATTAQUES):]
    assert inj_filtre["nb_factures_correspondantes"] == 0
    assert "erreur" in inj_detail          # aucune facture ne porte ce « numéro »
    assert "erreur" in inj_tri and "erreur" in inj_group
    assert final["lignes"] == [{"n": 3}]    # les données sont toujours là
    assert _silver_fingerprint(root) == before   # fichiers silver intacts, octet pour octet


def test_erreur_sql_aide_le_llm_a_se_corriger(root):
    _, (res,) = call_all(root, [("requete_sql", {"sql": "SELECT montant FROM silver.factures"})])
    assert "erreur" in res and "montant" in res["conseil"] and "decrire_schema" in res["conseil"]
    assert res["sql_executees"][0]["sql"] == "SELECT montant FROM silver.factures"


def test_resultats_plafonnes(root):
    _, (res,) = call_all(root, [("requete_sql", {"sql": "SELECT * FROM range(1000)"})])
    assert res["nb_lignes"] == 200 and res["tronque"] is True
