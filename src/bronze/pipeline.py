"""Étape 3 — couche bronze : données brutes extraites, avec traçabilité.

À faire :
  - pour chaque PDF, stocker le texte extrait + les métadonnées utiles ;
  - PDF avec couche texte : pas d'OCR ; les autres : OCR ;
  - traitement INCRÉMENTAL : relancer ne doit pas retraiter un fichier déjà ingéré.

Critères de validation :
  - deux exécutions de suite : la 2e n'ajoute rien et ne fait aucun appel OCR ;
  - si l'OCR est indisponible : pas de crash, l'erreur est tracée, le fichier
    sera retraité plus tard.

Règle d'or : on ne modifie ni ne supprime JAMAIS les données bronze.
"""


def ingest(pdf_path: str) -> None:
    """Ingère un PDF dans la couche bronze s'il n'y est pas déjà (idempotent)."""
    raise NotImplementedError("TODO étape 3 : ingestion bronze incrémentale + traçabilité")
