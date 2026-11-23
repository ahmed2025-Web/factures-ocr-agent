"""Étape 6 — entrepôt : bronze et silver interrogeables en SQL.

Séparation stockage / calcul :
  - STOCKAGE : les fichiers, en un seul exemplaire —
        bronze : data/bronze/*.json         (écrits par l'étape 3)
        silver : data/silver/*.parquet      (écrits par l'étape 4)
  - CALCUL   : DuckDB, qui lit ces fichiers à la demande. Aucune donnée n'est
    copiée dans une base : l'entrepôt n'est qu'un ensemble de VUES.

Deux façons d'y accéder :
  - les programmes (MCP, agent, évaluation) appellent `connect()` : une
    connexion DuckDB EN MÉMOIRE, propre au processus, avec les vues. Pas de
    fichier de base partagé → pas de verrou : DBeaver ouvert à côté ne bloque
    rien, et plusieurs programmes lisent en même temps sans conflit.
  - les outils graphiques (DBeaver) ouvrent `data/entrepot.duckdb`, généré par
    `python -m src.warehouse` : un fichier qui ne contient QUE les définitions
    des vues (quelques Ko), pas les données.

Chemins : la racine des données vient de DATA_ROOT (défaut : <dépôt>/data).
Les vues sont créées avec des chemins absolus calculés au lancement, donc
valides sur chaque machine / conteneur : on régénère le fichier .duckdb
localement (une commande, < 1 s) au lieu de le partager. DATA_ROOT peut aussi
être un préfixe S3 (s3://bucket/prefixe) : DuckDB lit alors directement le
bucket avec les identifiants S3 du .env.
"""

import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Vues de l'entrepôt : (schéma, nom) → (lecteur DuckDB, chemin relatif à DATA_ROOT).
SOURCES = {
    ("bronze", "documents"): ("read_json", "bronze/*.json"),
    ("silver", "factures"): ("read_parquet", "silver/factures.parquet"),
    ("silver", "lignes"): ("read_parquet", "silver/lignes.parquet"),
    ("silver", "quarantaine"): ("read_parquet", "silver/quarantaine.parquet"),
}

# Couche gold (bonus) : indicateurs métier, calculés à la volée sur la silver.
GOLD_VIEWS = {
    "ca_mensuel": """
        SELECT date_trunc('month', date_emission)::DATE AS mois,
               count(*) AS nb_factures,
               sum(total_ht) AS total_ht, sum(total_ttc) AS total_ttc
        FROM silver.factures GROUP BY 1 ORDER BY 1""",
    "encours_fournisseur": """
        SELECT fournisseur,
               count(*) AS nb_factures_non_payees,
               sum(total_ttc) AS encours_ttc,
               sum(total_ttc) FILTER (WHERE statut = 'En retard') AS dont_en_retard_ttc
        FROM silver.factures
        WHERE statut IS DISTINCT FROM 'Payée'
        GROUP BY 1 ORDER BY encours_ttc DESC""",
}


def data_root() -> str:
    root = os.environ.get("DATA_ROOT") or os.path.join(ROOT, "data")
    return root if root.startswith("s3://") else os.path.abspath(root)


def _configure_s3(con) -> None:
    """Rend un DATA_ROOT s3://… lisible (passerelle S3 Hyperfluid, identifiants du .env)."""
    endpoint = os.environ.get("S3_ENDPOINT_URL", "").replace("https://", "").replace("http://", "")
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute(
        "CREATE OR REPLACE SECRET entrepot_s3 (TYPE s3, KEY_ID ?, SECRET ?, ENDPOINT ?, "
        "URL_STYLE 'path', REGION 'us-east-1')",
        [os.environ.get("S3_ACCESS_KEY", ""), os.environ.get("S3_SECRET_KEY", ""), endpoint],
    )


def _exists(root: str, pattern: str) -> bool:
    if root.startswith("s3://"):
        return True  # on laisse DuckDB signaler une absence éventuelle
    import glob
    return bool(glob.glob(os.path.join(root, pattern)))


def view_statements(root: str | None = None) -> list[str]:
    """Instructions SQL qui créent l'entrepôt (schémas + vues) pour une racine donnée."""
    root = root or data_root()
    sep = "/" if root.startswith("s3://") else os.sep
    stmts = ["CREATE SCHEMA IF NOT EXISTS bronze", "CREATE SCHEMA IF NOT EXISTS silver",
             "CREATE SCHEMA IF NOT EXISTS gold"]
    for (schema, name), (reader, rel) in SOURCES.items():
        if not _exists(root, rel):
            continue  # couche pas encore produite : la vue sera créée au prochain lancement
        path = (root.rstrip("/") + "/" + rel) if sep == "/" else os.path.join(root, rel)
        path = path.replace("'", "''")
        opts = ", format = 'auto', union_by_name = true" if reader == "read_json" else ""
        stmts.append(f"CREATE OR REPLACE VIEW {schema}.{name} AS SELECT * FROM {reader}('{path}'{opts})")
    if _exists(root, SOURCES[("silver", "factures")][1]):
        for name, sql in GOLD_VIEWS.items():
            stmts.append(f"CREATE OR REPLACE VIEW gold.{name} AS {sql}")
    return stmts


def connect(root: str | None = None):
    """Connexion DuckDB en mémoire, avec toutes les vues de l'entrepôt.

    Chaque appel donne une connexion indépendante : aucun verrou partagé.
    """
    import duckdb

    root = root or data_root()
    con = duckdb.connect(":memory:")
    if root.startswith("s3://"):
        _configure_s3(con)
    for stmt in view_statements(root):
        con.execute(stmt)
    return con
