"""Étape 7 — logique des outils MCP (indépendante du protocole, donc testable seule).

Chaque outil renvoie un dict qui contient TOUJOURS :
  - "sql_executees" : la ou les requêtes réellement exécutées, avec leurs
    paramètres (transparence) ;
  - soit le résultat, soit "erreur" + "conseil" : un message qui aide le LLM à
    se corriger (colonne inconnue → liste des colonnes, etc.), au lieu d'un
    simple plantage.
"""

import re
import datetime
from decimal import Decimal

import duckdb

from .db import run_query, check_select_only, SqlRefusee, MAX_ROWS

# Colonnes autorisées pour trier / regrouper (liste blanche : ces noms sont
# insérés dans le SQL, ils ne doivent donc JAMAIS venir tels quels du LLM).
TRI = {
    "date_emission": "date_emission", "date_echeance": "date_echeance",
    "total_ttc": "total_ttc", "total_ht": "total_ht",
    "fournisseur": "fournisseur", "client": "client", "numero_facture": "numero_facture",
}
REGROUPEMENTS = {
    "fournisseur": "fournisseur", "client": "client", "statut": "statut",
    "categorie": "categorie", "statut_qualite": "statut_qualite",
    "annee": "year(date_emission)", "mois": "strftime(date_emission, '%Y-%m')",
}

COLONNES_LISTE = ("numero_facture, fournisseur, client, date_emission, date_echeance, "
                  "statut, categorie, total_ht, total_tva, total_ttc, statut_qualite")


def _norm(col: str) -> str:
    """Comparaison insensible à la casse et aux accents (« payee » trouve « Payée »)."""
    return f"lower(strip_accents({col}))"


def _date(value, name: str):
    if value in (None, ""):
        return None
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError:
        raise ValueError(f"{name} doit être une date au format AAAA-MM-JJ (reçu : {value!r})")


def build_where(fournisseur=None, client=None, statut=None, categorie=None,
                date_debut=None, date_fin=None, annee=None, montant_min=None,
                montant_max=None, statut_qualite=None) -> tuple[str, list]:
    """Clause WHERE paramétrée : les valeurs vont dans `params`, jamais dans le SQL."""
    conds, params = [], []
    for col, value in (("fournisseur", fournisseur), ("client", client), ("categorie", categorie)):
        if value:
            conds.append(f"contains({_norm(col)}, {_norm('?')})")
            params.append(str(value))
    for col, value in (("statut", statut), ("statut_qualite", statut_qualite)):
        if value:
            conds.append(f"{_norm(col)} = {_norm('?')}")
            params.append(str(value))
    if (d := _date(date_debut, "date_debut")) is not None:
        conds.append("date_emission >= ?")
        params.append(d)
    if (d := _date(date_fin, "date_fin")) is not None:
        conds.append("date_emission <= ?")
        params.append(d)
    if annee not in (None, ""):
        conds.append("year(date_emission) = ?")
        params.append(int(annee))
    if montant_min not in (None, ""):
        conds.append("total_ttc >= ?")
        params.append(Decimal(str(montant_min)))
    if montant_max not in (None, ""):
        conds.append("total_ttc <= ?")
        params.append(Decimal(str(montant_max)))
    return (" WHERE " + " AND ".join(conds)) if conds else "", params


def _trace(sql: str, params: list) -> dict:
    return {"sql": " ".join(sql.split()), "parametres": [str(p) for p in params]}


def _erreur(exc: Exception, sql_executees: list, conseil: str) -> dict:
    return {"erreur": f"{type(exc).__name__}: {exc}", "conseil": conseil, "sql_executees": sql_executees}


# --- Outils ------------------------------------------------------------------------
def lister_factures(con, limite: int = 50, tri: str = "date_emission", ordre: str = "desc", **filtres) -> dict:
    if tri not in TRI:
        return {"erreur": f"tri inconnu : {tri!r}", "conseil": f"valeurs possibles : {', '.join(TRI)}",
                "sql_executees": []}
    direction = "ASC" if str(ordre).lower() == "asc" else "DESC"
    limite = max(1, min(int(limite or 50), MAX_ROWS))
    try:
        where, params = build_where(**filtres)
    except ValueError as exc:
        return _erreur(exc, [], "corrigez le format de l'argument puis réessayez")
    sql = (f"SELECT {COLONNES_LISTE} FROM silver.factures{where} "
           f"ORDER BY {TRI[tri]} {direction}, numero_facture LIMIT {limite}")
    count_sql = f"SELECT count(*) AS nb FROM silver.factures{where}"
    res = run_query(con, sql, params)
    total = run_query(con, count_sql, params)["lignes"][0]["nb"]
    return {"sql_executees": [_trace(sql, params), _trace(count_sql, params)],
            "nb_factures_correspondantes": total, "nb_renvoyees": res["nb_lignes"],
            "factures": res["lignes"]}


def compter_et_totaliser(con, regrouper_par: str | None = None, **filtres) -> dict:
    try:
        where, params = build_where(**filtres)
    except ValueError as exc:
        return _erreur(exc, [], "corrigez le format de l'argument puis réessayez")
    aggs = ("count(*) AS nb_factures, sum(total_ht) AS total_ht, "
            "sum(total_tva) AS total_tva, sum(total_ttc) AS total_ttc")
    if regrouper_par:
        if regrouper_par not in REGROUPEMENTS:
            return {"erreur": f"regroupement inconnu : {regrouper_par!r}",
                    "conseil": f"valeurs possibles : {', '.join(REGROUPEMENTS)}", "sql_executees": []}
        expr = REGROUPEMENTS[regrouper_par]
        sql = (f"SELECT {expr} AS {regrouper_par}, {aggs} FROM silver.factures{where} "
               f"GROUP BY 1 ORDER BY total_ttc DESC NULLS LAST")
    else:
        sql = f"SELECT {aggs} FROM silver.factures{where}"
    res = run_query(con, sql, params)
    out = {"sql_executees": [_trace(sql, params)]}
    if regrouper_par:
        out["groupes"] = res["lignes"]
    else:
        out.update(res["lignes"][0])
    return out


def detail_facture(con, numero_facture: str) -> dict:
    numero = str(numero_facture or "").strip()
    sql_f = "SELECT * FROM silver.factures WHERE upper(numero_facture) = upper(?)"
    sql_l = ("SELECT num_ligne, designation, quantite, prix_unitaire_ht, taux_tva, total_ht "
             "FROM silver.lignes WHERE upper(numero_facture) = upper(?) ORDER BY num_ligne")
    traces = [_trace(sql_f, [numero])]
    fac = run_query(con, sql_f, [numero])
    if not fac["lignes"]:
        sql_q = "SELECT source_key, motif, details FROM silver.quarantaine WHERE upper(numero_facture) = upper(?)"
        traces.append(_trace(sql_q, [numero]))
        q = run_query(con, sql_q, [numero])["lignes"]
        conseil = ("cette facture a été écartée (quarantaine), voir 'quarantaine'" if q else
                   "vérifiez le numéro (format du type A-2025-0003) ou utilisez lister_factures pour le retrouver")
        return {"erreur": f"facture {numero!r} introuvable dans silver.factures",
                "conseil": conseil, "quarantaine": q, "sql_executees": traces}
    traces.append(_trace(sql_l, [numero]))
    return {"sql_executees": traces, "facture": fac["lignes"][0],
            "lignes": run_query(con, sql_l, [numero])["lignes"]}


def decrire_schema(con) -> dict:
    sql = ("SELECT table_schema, table_name, column_name, data_type FROM information_schema.columns "
           "ORDER BY table_schema, table_name, ordinal_position")
    res = run_query(con, sql, max_rows=10_000)
    tables: dict[str, list] = {}
    for r in res["lignes"]:
        tables.setdefault(f"{r['table_schema']}.{r['table_name']}", []).append(
            f"{r['column_name']} {r['data_type']}")
    sql_s = "SELECT DISTINCT statut FROM silver.factures ORDER BY 1"
    statuts = [r["statut"] for r in run_query(con, sql_s)["lignes"]]
    return {
        "sql_executees": [_trace(sql, []), _trace(sql_s, [])],
        "tables": tables,
        "valeurs_statut": statuts,
        "notes": [
            "Montants en DECIMAL (euros, exacts au centime) ; dates en DATE.",
            "silver.factures : une ligne par facture acceptée ; silver.lignes : détail (clé numero_facture).",
            "statut = statut de PAIEMENT (Payée, En retard…) ; statut_qualite = 'valide' ou 'signalee' "
            "(anomalies listées dans la colonne anomalies).",
            "silver.quarantaine : documents rejetés, avec motif ; bronze.documents : texte brut extrait.",
            "gold.* : indicateurs calculés (CA mensuel, encours par fournisseur).",
        ],
    }


def requete_sql(con, sql: str) -> dict:
    try:
        clean = check_select_only(sql)
    except SqlRefusee as exc:
        return {"erreur": f"requête refusée : {exc}",
                "conseil": "cet outil est en lecture seule : écrivez une seule requête SELECT "
                           "(WITH … SELECT autorisé)", "sql_executees": []}
    try:
        res = run_query(con, clean)
    except duckdb.Error as exc:
        conseil = "utilisez decrire_schema pour voir les tables et colonnes disponibles"
        m = re.search(r'Referenced column "(\w+)" not found', str(exc))
        if m:
            conseil = f"la colonne {m.group(1)!r} n'existe pas ; " + conseil
        return _erreur(exc, [_trace(clean, [])], conseil)
    return {"sql_executees": [_trace(clean, [])], **res}


def indicateur_gold(con, indicateur: str) -> dict:
    vues = {"ca_mensuel": "gold.ca_mensuel", "encours_fournisseur": "gold.encours_fournisseur"}
    if indicateur not in vues:
        return {"erreur": f"indicateur inconnu : {indicateur!r}",
                "conseil": f"valeurs possibles : {', '.join(vues)}", "sql_executees": []}
    sql = f"SELECT * FROM {vues[indicateur]}"
    return {"sql_executees": [_trace(sql, [])], **run_query(con, sql)}
