"""Étape 7 — accès à l'entrepôt pour le serveur MCP, verrouillé en lecture seule.

Les arguments des outils viennent d'un LLM : c'est une source NON FIABLE (il
peut se tromper, ou relayer une instruction malveillante cachée dans une
question). On empile donc plusieurs protections, chacune suffisant à bloquer
une famille d'attaques :

  1. Base ouverte en READ_ONLY : aucun CREATE / INSERT / UPDATE / DELETE / DROP
     possible sur l'entrepôt (refusé par DuckDB lui-même).
  2. Accès fichiers coupé (enable_external_access = false), sauf le dossier des
     données (allowed_directories) : pas de lecture de /etc/passwd, du .env, etc.,
     pas d'ATTACH d'une autre base, pas d'INSTALL d'extension.
  3. Configuration verrouillée (lock_configuration) : impossible de réactiver
     2. par un `SET` dans le SQL libre.
  4. SQL libre : on n'accepte qu'UNE instruction, de type SELECT, vérifié par le
     parseur de DuckDB (pas par une regex). Indispensable : le test a montré que
     `COPY … TO 'data/…'` passait les protections 1–3 et aurait pu écraser un
     fichier silver.
  5. Outils à filtres : requêtes PARAMÉTRÉES (valeurs passées à part, jamais
     concaténées dans le SQL) ; noms de colonnes de tri/regroupement choisis
     dans une liste blanche.
  6. Garde-fous de ressources : nombre de lignes renvoyées plafonné, délai
     maximum par requête.
"""

import os
import atexit
import tempfile
import threading

import duckdb

from ..warehouse import data_root, view_statements

MAX_ROWS = 200
TIMEOUT_S = 10.0


class SqlRefusee(ValueError):
    """Requête refusée avant exécution (pas un SELECT, plusieurs instructions…)."""


def open_readonly(root: str | None = None) -> duckdb.DuckDBPyConnection:
    """Connexion à l'entrepôt, en lecture seule et sans accès fichiers hors données."""
    root = root or data_root()
    # Fichier de vues propre à ce processus (pas de verrou partagé avec DBeaver).
    fd, path = tempfile.mkstemp(prefix="entrepot_mcp_", suffix=".duckdb")
    os.close(fd)
    os.remove(path)
    con = duckdb.connect(path)
    for stmt in view_statements(root):
        con.execute(stmt)
    con.close()
    atexit.register(lambda: os.path.exists(path) and os.remove(path))

    con = duckdb.connect(path, read_only=True)
    if not root.startswith("s3://"):
        con.execute("SET allowed_directories = ?", [[os.path.join(root, "")]])
        con.execute("SET enable_external_access = false")
    con.execute("SET lock_configuration = true")
    return con


def check_select_only(sql: str) -> str:
    """Valide une requête libre : exactement une instruction SELECT. Retourne le SQL nettoyé."""
    sql = (sql or "").strip().rstrip(";").strip()
    if not sql:
        raise SqlRefusee("requête vide")
    try:
        statements = duckdb.extract_statements(sql)
    except duckdb.Error as exc:
        raise SqlRefusee(f"SQL invalide : {exc}") from exc
    if len(statements) != 1:
        raise SqlRefusee(f"une seule instruction autorisée ({len(statements)} reçues)")
    kind = statements[0].type
    if kind != duckdb.StatementType.SELECT:
        raise SqlRefusee(f"seules les requêtes SELECT sont autorisées (reçu : {kind.name})")
    return sql


def run_query(con, sql: str, params: list | None = None, max_rows: int = MAX_ROWS) -> dict:
    """Exécute une requête avec délai maximum ; renvoie colonnes + lignes (plafonnées)."""
    cursor = con.cursor()  # curseur propre à l'appel (appels concurrents possibles)
    timer = threading.Timer(TIMEOUT_S, cursor.interrupt)
    timer.start()
    try:
        cur = cursor.execute(sql, params or [])
        columns = [d[0] for d in cur.description]
        rows = cur.fetchmany(max_rows + 1)
    finally:
        timer.cancel()
    truncated = len(rows) > max_rows
    return {
        "colonnes": columns,
        "lignes": [dict(zip(columns, map(to_json, r))) for r in rows[:max_rows]],
        "nb_lignes": min(len(rows), max_rows),
        "tronque": truncated,
    }


def to_json(value):
    """Valeurs SQL → JSON sans perte : Decimal en texte exact, dates en ISO."""
    from decimal import Decimal
    import datetime

    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return value
