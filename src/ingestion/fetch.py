"""Étape 1 — récupérer les factures et détecter texte / image.

À faire :
  - télécharger les nouvelles factures du bucket S3 vers une zone d'arrivée (data/);
  - pour chaque PDF, dire s'il a une couche texte exploitable ou s'il faut l'OCR.

Critères de validation :
  - une commande récupère les nouvelles factures du bucket ;
  - on sait dire, pour chaque fichier, s'il est « texte » ou « image ».

Note : ne pas se fier au nom de fichier (`_texte` / `_scan`) pour décider —
le détecter réellement (ex. présence de texte extractible dans le PDF).
"""


def download_new_invoices(dest_dir: str) -> list[str]:
    """Télécharge les factures du bucket S3 absentes de dest_dir. Retourne les chemins."""
    raise NotImplementedError("TODO étape 1 : téléchargement S3 incrémental")


def has_text_layer(pdf_path: str) -> bool:
    """True si le PDF contient une couche texte exploitable (pas besoin d'OCR)."""
    raise NotImplementedError("TODO étape 1 : détection couche texte vs image")
