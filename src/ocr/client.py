"""Étape 2 — appeler le modèle d'OCR LightOnOCR-3.

Le modèle est servi derrière une API **compatible OpenAI** (`/v1/chat/completions`).
En *mode transcription* (celui qu'on veut pour l'OCR), on envoie l'image seule,
sans prompt : le modèle renvoie tout le texte de la page en markdown.

On fait donc, pour une page de facture :
    PDF ──(rendu image)──► image PNG ──(API OCR)──► texte markdown

Le temps de traitement par page est mesuré et renvoyé.

Config (dans .env) :
    OCR_API_URL   adresse du point d'accès (base ou URL complète)
    OCR_API_KEY   clé d'API Hyperfluid
    OCR_MODEL     nom du modèle (défaut : lightonai/LightOnOCR-3-1B)

La résolution de rendu (DPI) est un réglage à tester (voir étape 5) : plus haut =
plus lisible mais plus lent et plus lourd.

Pour ne pas dépendre de ce fournisseur précis, tout passe par la fonction
`ocr_image` : en changer revient à réécrire cette seule fonction.
"""

import os
import sys
import base64
import time

import requests

DEFAULT_MODEL = "lightonai/LightOnOCR-3-1B"
DEFAULT_DPI = 200
TIMEOUT_S = 120


def _endpoint() -> str:
    """Construit l'URL /v1/chat/completions à partir de OCR_API_URL."""
    url = (os.environ.get("OCR_API_URL") or "").rstrip("/")
    if not url:
        raise SystemExit("OCR_API_URL manquant : renseignez-le dans votre .env.")
    if url.endswith("/chat/completions"):
        return url
    if url.endswith("/v1"):
        return url + "/chat/completions"
    return url + "/v1/chat/completions"


def render_page(pdf_path: str, page_index: int = 0, dpi: int = DEFAULT_DPI) -> bytes:
    """Rend une page de PDF en image PNG (bytes), à la résolution demandée."""
    import fitz  # PyMuPDF

    with fitz.open(pdf_path) as doc:
        page = doc[page_index]
        pix = page.get_pixmap(dpi=dpi)
        return pix.tobytes("png")


def ocr_image(image_png: bytes) -> tuple[str, float]:
    """Envoie une image PNG au modèle OCR. Retourne (texte, durée_en_secondes).

    Mode transcription : on n'envoie que l'image, sans texte de prompt.
    """
    api_key = os.environ.get("OCR_API_KEY")
    if not api_key:
        raise SystemExit("OCR_API_KEY manquant : renseignez-le dans votre .env.")

    data_uri = "data:image/png;base64," + base64.b64encode(image_png).decode()
    payload = {
        "model": os.environ.get("OCR_MODEL", DEFAULT_MODEL),
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            }
        ],
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    start = time.perf_counter()
    response = requests.post(_endpoint(), json=payload, headers=headers, timeout=TIMEOUT_S)
    response.raise_for_status()
    elapsed = time.perf_counter() - start

    text = response.json()["choices"][0]["message"]["content"]
    return text, elapsed


def ocr_pdf_page(pdf_path: str, page_index: int = 0, dpi: int = DEFAULT_DPI) -> tuple[str, float]:
    """Rend une page de PDF puis l'envoie à l'OCR. Retourne (texte, durée)."""
    image_png = render_page(pdf_path, page_index=page_index, dpi=dpi)
    return ocr_image(image_png)


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit("Usage : python -m src.ocr.client <fichier.pdf> [--dpi N] [--page N]")

    pdf_path = args[0]
    dpi = _int_opt("--dpi", DEFAULT_DPI)
    page = _int_opt("--page", 0)

    text, elapsed = ocr_pdf_page(pdf_path, page_index=page, dpi=dpi)
    print(f"--- OCR de {os.path.basename(pdf_path)} (page {page}, {dpi} DPI) ---")
    print(text)
    print(f"\n[temps de traitement : {elapsed:.2f} s]")


def _int_opt(flag: str, default: int) -> int:
    """Lit une option entière de la forme --flag=valeur ou --flag valeur."""
    argv = sys.argv
    for i, a in enumerate(argv):
        if a == flag and i + 1 < len(argv):
            return int(argv[i + 1])
        if a.startswith(flag + "="):
            return int(a.split("=", 1)[1])
    return default


if __name__ == "__main__":
    main()
