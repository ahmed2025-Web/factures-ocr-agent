"""Étape 7 — serveur MCP donnant accès à l'entrepôt, en lecture seule.

Transport stdio : le client MCP (Claude Desktop, Claude Code, notre agent)
lance ce programme et dialogue avec lui sur l'entrée/sortie standard.

    python -m src.mcp_server.server

Le LLM choisit ses outils d'après leur NOM et leur DESCRIPTION. On les rédige
donc comme une notice : à quoi sert l'outil, QUAND le préférer à un autre, le
format exact des arguments (dates AAAA-MM-JJ, valeurs de statut…), et ce que
contient la réponse. Les outils spécialisés sont présentés avant le SQL libre,
qui reste le dernier recours.

Toutes les protections (lecture seule, injections, ressources) sont décrites
dans db.py ; la logique des outils est dans tools.py.
"""

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from . import tools
from .db import open_readonly

mcp = FastMCP(
    "factures",
    instructions=(
        "Accès en lecture seule aux factures fournisseurs (couche silver de l'entrepôt). "
        "Pour toute question chiffrée, appelez un outil : ne devinez jamais un montant. "
        "Commencez par decrire_schema si vous ne connaissez pas les données. "
        "Chaque réponse contient 'sql_executees' : citez-les pour justifier vos chiffres."
    ),
)
_con = None
LECTURE = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


def con():
    """Connexion ouverte au premier appel (le serveur démarre même sans données)."""
    global _con
    if _con is None:
        _con = open_readonly()
    return _con


# Filtres communs à lister_factures et compter_et_totaliser.
Fournisseur = Annotated[str | None, Field(description="Nom du fournisseur (émetteur). Recherche partielle, sans tenir compte des majuscules ni des accents.")]
Client = Annotated[str | None, Field(description="Nom du client (destinataire). Recherche partielle.")]
Statut = Annotated[str | None, Field(description="Statut de PAIEMENT exact, ex. 'En retard', 'Payée', 'Envoyée' (voir decrire_schema pour la liste).")]
Categorie = Annotated[str | None, Field(description="Catégorie de dépense, ex. 'Conseil'. Recherche partielle.")]
DateDebut = Annotated[str | None, Field(description="Date d'émission minimale incluse, format AAAA-MM-JJ.")]
DateFin = Annotated[str | None, Field(description="Date d'émission maximale incluse, format AAAA-MM-JJ.")]
Annee = Annotated[int | None, Field(description="Année d'émission, ex. 2025.")]
MontantMin = Annotated[float | None, Field(description="Montant TTC minimal en euros.")]
MontantMax = Annotated[float | None, Field(description="Montant TTC maximal en euros.")]
StatutQualite = Annotated[str | None, Field(description="'valide' ou 'signalee' (facture avec anomalies de contrôle).")]


@mcp.tool(annotations=LECTURE)
def lister_factures(
    fournisseur: Fournisseur = None, client: Client = None, statut: Statut = None,
    categorie: Categorie = None, date_debut: DateDebut = None, date_fin: DateFin = None,
    annee: Annee = None, montant_min: MontantMin = None, montant_max: MontantMax = None,
    statut_qualite: StatutQualite = None,
    limite: Annotated[int, Field(description="Nombre maximum de factures renvoyées (1 à 200).")] = 50,
    tri: Annotated[str, Field(description="Colonne de tri : date_emission, date_echeance, total_ttc, total_ht, fournisseur, client, numero_facture.")] = "date_emission",
    ordre: Annotated[str, Field(description="'desc' (défaut) ou 'asc'.")] = "desc",
) -> dict:
    """Liste des factures (numéro, fournisseur, client, dates, statut, montants) qui
    correspondent aux filtres. À utiliser pour VOIR des factures ; pour un nombre ou
    une somme, préférez compter_et_totaliser (qui ne tronque pas)."""
    return tools.lister_factures(con(), limite=limite, tri=tri, ordre=ordre, **_filtres(locals()))


@mcp.tool(annotations=LECTURE)
def compter_et_totaliser(
    fournisseur: Fournisseur = None, client: Client = None, statut: Statut = None,
    categorie: Categorie = None, date_debut: DateDebut = None, date_fin: DateFin = None,
    annee: Annee = None, montant_min: MontantMin = None, montant_max: MontantMax = None,
    statut_qualite: StatutQualite = None,
    regrouper_par: Annotated[str | None, Field(description="Optionnel : fournisseur, client, statut, categorie, statut_qualite, annee ou mois, pour un total par groupe.")] = None,
) -> dict:
    """Nombre de factures et totaux HT / TVA / TTC (en euros) pour les filtres donnés,
    éventuellement par groupe. C'est l'outil à utiliser pour « combien », « quel
    montant », « total », « par fournisseur »…"""
    return tools.compter_et_totaliser(con(), regrouper_par=regrouper_par, **_filtres(locals()))


@mcp.tool(annotations=LECTURE)
def detail_facture(
    numero_facture: Annotated[str, Field(description="Numéro de la facture, ex. 'A-2025-0003'.")],
) -> dict:
    """Toutes les informations d'UNE facture (fournisseur, client, SIRET, IBAN, dates,
    totaux, statut qualité et anomalies) et ses lignes de détail (désignation,
    quantité, prix unitaire, TVA). Indique aussi si la facture a été mise en quarantaine."""
    return tools.detail_facture(con(), numero_facture)


@mcp.tool(annotations=LECTURE)
def decrire_schema() -> dict:
    """Tables et colonnes de l'entrepôt (bronze, silver, gold) avec leurs types, et les
    valeurs possibles du statut de paiement. À appeler avant d'écrire du SQL libre."""
    return tools.decrire_schema(con())


@mcp.tool(annotations=LECTURE)
def requete_sql(
    sql: Annotated[str, Field(description="UNE requête SELECT (DuckDB). Tables : silver.factures, silver.lignes, silver.quarantaine, bronze.documents, gold.*.")],
) -> dict:
    """Exécute une requête SQL libre EN LECTURE SEULE (SELECT uniquement, 200 lignes
    maximum). Dernier recours, quand aucun autre outil ne répond à la question
    (jointures, calculs particuliers). Toute écriture est refusée."""
    return tools.requete_sql(con(), sql)


@mcp.tool(annotations=LECTURE)
def indicateur_gold(
    indicateur: Annotated[str, Field(description="'ca_mensuel' (factures et montants par mois) ou 'encours_fournisseur' (montant TTC non payé par fournisseur, dont en retard).")],
) -> dict:
    """Indicateurs métier prêts à l'emploi (couche gold) : chiffre d'affaires mensuel
    ou encours non payé par fournisseur."""
    return tools.indicateur_gold(con(), indicateur)


def _filtres(args: dict) -> dict:
    keys = ("fournisseur", "client", "statut", "categorie", "date_debut", "date_fin",
            "annee", "montant_min", "montant_max", "statut_qualite")
    return {k: args[k] for k in keys}


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    mcp.run()  # transport stdio


if __name__ == "__main__":
    main()
