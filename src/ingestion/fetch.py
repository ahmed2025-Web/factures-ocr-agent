"""Étape 1 — récupérer les factures et détecter texte / image.

À faire :
  - télécharger les nouvelles factures du bucket S3 vers une zone d'arrivée (data/);
  - pour chaque PDF, dire s'il a une couche texte exploitable ou s'il faut l'OCR.

Critères de validation :
  - une commande récupère les nouvelles factures du bucket ;
  - on sait dire, pour chaque fichier, s'il est « texte » ou « image ».

Usage :
    python -m src.ingestion.fetch            # télécharge les nouvelles + classe tout
    python -m src.ingestion.fetch --no-download   # classe seulement ce qui est en local

Les identifiants S3 et l'URL du point d'accès viennent de .env (jamais commités).
Note : on ne se fie PAS au nom de fichier (`_texte` / `_scan`) pour décider —
la détection se fait sur le contenu réel du PDF.
"""

import os
import sys

from dotenv import load_dotenv
from pypdf import PdfReader

# Dossier d'arrivée local (ignoré par git).
LANDING_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "raw")

# En dessous de ce nombre de caractères extraits, on considère qu'il n'y a pas
# de vraie couche texte et qu'il faut passer par l'OCR.
MIN_TEXT_CHARS = 20


def _s3_client():
    """Crée un client S3 pointant sur la passerelle Hyperfluid (config dans .env)."""
    import boto3

    endpoint = os.environ.get("S3_ENDPOINT_URL")
    access_key = os.environ.get("S3_ACCESS_KEY")
    secret_key = os.environ.get("S3_SECRET_KEY")
    if not (endpoint and access_key and secret_key):
        raise SystemExit(
            "Identifiants S3 manquants. Renseignez S3_ENDPOINT_URL, S3_ACCESS_KEY "
            "et S3_SECRET_KEY dans votre fichier .env."
        )
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )


def list_invoice_keys() -> list[str]:
    """Liste les clés des factures PDF du bucket (ignore les sous-dossiers)."""
    client = _s3_client()
    bucket = os.environ.get("S3_BUCKET", "factures")
    keys: list[str] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            # On ne garde que les PDF à la racine (pas gold/, silver/…).
            if key.lower().endswith(".pdf") and "/" not in key:
                keys.append(key)
    return keys


def download_new_invoices(dest_dir: str = LANDING_DIR) -> list[str]:
    """Télécharge les factures absentes de dest_dir. Retourne les chemins téléchargés.

    Incrémental : un fichier déjà présent localement, de même taille, n'est pas
    retéléchargé. La clé S3 est unique, elle suffit à reconnaître un fichier.
    """
    client = _s3_client()
    bucket = os.environ.get("S3_BUCKET", "factures")
    os.makedirs(dest_dir, exist_ok=True)

    downloaded: list[str] = []
    for key in list_invoice_keys():
        local_path = os.path.join(dest_dir, key)
        head = client.head_object(Bucket=bucket, Key=key)
        remote_size = head["ContentLength"]
        if os.path.isfile(local_path) and os.path.getsize(local_path) == remote_size:
            continue  # déjà récupéré, on saute
        client.download_file(bucket, key, local_path)
        downloaded.append(local_path)
    return downloaded


def has_text_layer(pdf_path: str) -> bool:
    """True si le PDF contient une couche texte exploitable (pas besoin d'OCR)."""
    try:
        reader = PdfReader(pdf_path)
        text = "".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        # PDF illisible par l'extracteur texte : à traiter comme une image.
        return False
    return len(text.strip()) >= MIN_TEXT_CHARS


def classify(pdf_path: str) -> str:
    """Retourne 'texte' ou 'image' pour un PDF donné."""
    return "texte" if has_text_layer(pdf_path) else "image"


def main() -> None:
    load_dotenv()
    do_download = "--no-download" not in sys.argv

    if do_download:
        new_files = download_new_invoices()
        print(f"{len(new_files)} nouvelle(s) facture(s) téléchargée(s).")
    else:
        print("Téléchargement ignoré (--no-download).")

    # Classe tous les PDF présents dans la zone d'arrivée.
    if not os.path.isdir(LANDING_DIR):
        print("Aucune facture en local. Lancez sans --no-download (et renseignez .env).")
        return

    pdfs = sorted(f for f in os.listdir(LANDING_DIR) if f.lower().endswith(".pdf"))
    counts = {"texte": 0, "image": 0}
    print(f"\n{'Fichier':45} Type")
    print("-" * 55)
    for name in pdfs:
        kind = classify(os.path.join(LANDING_DIR, name))
        counts[kind] += 1
        print(f"{name:45} {kind}")
    print("-" * 55)
    print(f"Total : {len(pdfs)} fichiers — {counts['texte']} texte, {counts['image']} image")


if __name__ == "__main__":
    main()
