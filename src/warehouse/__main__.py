"""Étape 6 — commande de l'entrepôt.

    python -m src.warehouse                  # (re)crée data/entrepot.duckdb (vues seules)
    python -m src.warehouse "SELECT ..."     # exécute une requête et affiche le résultat
    python -m src.warehouse --tables         # liste les vues disponibles

Le fichier data/entrepot.duckdb est fait pour DBeaver (pilote DuckDB) : il ne
contient que des définitions de vues pointant vers les fichiers bronze/silver.
Pour ne gêner personne, ouvrez-le en LECTURE SEULE dans DBeaver
(propriétés de connexion → « Read-only connection » ou `access_mode=READ_ONLY`).
Les programmes, eux, n'utilisent pas ce fichier (voir connect()).
"""

import os
import sys

from . import connect, data_root, view_statements

DB_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "entrepot.duckdb")


def build_file(path: str = DB_FILE) -> str:
    """Écrit le fichier .duckdb de vues (remplacé à chaque fois, atomiquement)."""
    import duckdb

    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    con = duckdb.connect(tmp)
    for stmt in view_statements():
        con.execute(stmt)
    con.close()
    os.replace(tmp, path)
    return path


def _print(con, sql: str) -> None:
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    widths = [max(len(str(c)), *(len(str(r[i])) for r in rows)) if rows else len(str(c))
              for i, c in enumerate(cols)]
    print(" | ".join(str(c).ljust(w) for c, w in zip(cols, widths)))
    print("-+-".join("-" * w for w in widths))
    for r in rows:
        print(" | ".join(str(v).ljust(w) for v, w in zip(r, widths)))
    print(f"({len(rows)} ligne(s))")


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    args = sys.argv[1:]
    if not args:
        path = build_file()
        print(f"Entrepôt créé : {path}")
        print(f"Données lues depuis : {data_root()}")
        _print(connect(), "SELECT table_schema AS schema, table_name AS vue FROM information_schema.tables "
                          "ORDER BY 1, 2")
    elif args[0] == "--tables":
        _print(connect(), "SELECT table_schema AS schema, table_name AS vue FROM information_schema.tables "
                          "ORDER BY 1, 2")
    else:
        _print(connect(), " ".join(args))


if __name__ == "__main__":
    main()
