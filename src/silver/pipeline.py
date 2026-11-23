"""Étape 4 — couche silver : données propres, typées, contrôlées (binôme).

À faire :
  - transformer le texte brut (bronze) en tables : factures + lignes de facture ;
  - typer correctement (dates, montants — pas de float pour les euros) ;
  - contrôles qualité + table de quarantaine (rejets avec motif).

Critères : aucune facture valide perdue, aucun doublon, chaque facture a un
statut qualité, chaque rejet un motif, montants incohérents détectés.
"""


def build_silver() -> None:
    raise NotImplementedError("TODO étape 4 (binôme) : parsing robuste + typage + contrôles")
