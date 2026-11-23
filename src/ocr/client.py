"""Étape 2 — appeler le modèle d'OCR LightOnOCR-3.

À faire :
  - envoyer une page de facture au modèle et récupérer le texte reconnu ;
  - mesurer le temps de traitement par page ;
  - étudier le format de sortie (texte, rendu des tableaux).

Le code ne doit pas dépendre d'un fournisseur d'OCR précis : garder une
interface simple (`ocr_page`) qu'on pourra réimplémenter avec un autre moteur.
"""


def ocr_page(image_bytes: bytes) -> str:
    """Envoie une image de page au modèle OCR et retourne le texte reconnu."""
    raise NotImplementedError("TODO étape 2 : appel API LightOnOCR-3 (URL + clé dans .env)")
