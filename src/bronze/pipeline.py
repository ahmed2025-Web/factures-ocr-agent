"""Étape 3 — couche bronze : données brutes extraites, avec traçabilité.

Pour chaque PDF :
  - s'il a une couche texte → on extrait le texte directement (pas d'OCR) ;
  - sinon → on l'OCRise page par page.
On stocke le texte brut + des métadonnées de traçabilité, en un enregistrement
JSON par facture dans data/bronze/.

Propriétés demandées :
  - INCRÉMENTAL : un fichier déjà ingéré (même contenu) est sauté, sans appel OCR.
  - ROBUSTE : si l'OCR est indisponible, le pipeline ne plante pas ; l'erreur est
    tracée et le fichier sera retraité au prochain passage.
  - IMMUABLE : on ne modifie ni ne supprime jamais un enregistrement bronze.

Usage :
    python -m src.bronze.pipeline                 # ingère data/raw/
    python -m src.bronze.pipeline --dpi 300
"""

import os
import sys
import json
import hashlib
import datetime

from ..ingestion.fetch import has_text_layer, LANDING_DIR
from ..ocr.client import ocr_pdf_page, DEFAULT_DPI

BRONZE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "bronze")
ERROR_LOG = os.path.join(BRONZE_DIR, "_errors.log")


def _sha256(path: str) -> str:
    """Empreinte du contenu du fichier (sert à reconnaître un fichier déjà vu)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _record_path(source_key: str) -> str:
    stem = os.path.splitext(os.path.basename(source_key))[0]
    return os.path.join(BRONZE_DIR, stem + ".json")


def is_ingested(source_key: str, sha: str) -> bool:
    """Vrai si une facture de même nom ET même contenu est déjà en bronze."""
    path = _record_path(source_key)
    if not os.path.isfile(path):
        return False
    try:
        with open(path, encoding="utf-8") as f:
            record = json.load(f)
    except (OSError, json.JSONDecodeError):
        return False
    return record.get("source_sha256") == sha and record.get("status") == "ok"


def _extract_native_text(pdf_path: str) -> tuple[str, int]:
    """Texte d'un PDF natif (toutes les pages) + nombre de pages."""
    from pypdf import PdfReader

    reader = PdfReader(pdf_path)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return text, len(reader.pages)


def _extract_ocr_text(pdf_path: str, dpi: int) -> tuple[str, int, float]:
    """Texte d'un PDF scanné via OCR (toutes les pages) + nb pages + temps total."""
    from pypdf import PdfReader

    n_pages = len(PdfReader(pdf_path).pages)
    parts, total_time = [], 0.0
    for i in range(n_pages):
        text, elapsed = ocr_pdf_page(pdf_path, page_index=i, dpi=dpi)
        parts.append(text)
        total_time += elapsed
    return "\n\n".join(parts), n_pages, total_time


def _trace_error(source_key: str, message: str) -> None:
    """Écrit l'erreur dans un log ; aucun enregistrement 'ok' → fichier retraité."""
    os.makedirs(BRONZE_DIR, exist_ok=True)
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    with open(ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(f"{stamp}\t{source_key}\t{message}\n")


def ingest(pdf_path: str, dpi: int = DEFAULT_DPI) -> str:
    """Ingère un PDF dans la couche bronze s'il n'y est pas déjà.

    Retourne : 'skipped', 'ingested' ou 'error'.
    """
    os.makedirs(BRONZE_DIR, exist_ok=True)
    source_key = os.path.basename(pdf_path)
    sha = _sha256(pdf_path)

    if is_ingested(source_key, sha):
        return "skipped"  # déjà vu, même contenu → aucun retraitement, aucun OCR

    try:
        if has_text_layer(pdf_path):
            text, n_pages = _extract_native_text(pdf_path)
            method, ocr_meta = "pdf_text", {}
        else:
            text, n_pages, ocr_time = _extract_ocr_text(pdf_path, dpi)
            method = "ocr"
            ocr_meta = {"ocr_model": os.environ.get("OCR_MODEL", "lightonocr-3-1b-test"),
                        "ocr_dpi": dpi, "ocr_seconds": round(ocr_time, 2)}
    except (Exception, SystemExit) as exc:  # OCR indisponible, PDF illisible, clé manquante…
        _trace_error(source_key, f"{type(exc).__name__}: {exc}")
        return "error"

    record = {
        "source_key": source_key,
        "source_sha256": sha,
        "kind": "texte" if method == "pdf_text" else "image",
        "extraction_method": method,
        "page_count": n_pages,
        "char_count": len(text),
        "ingested_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "status": "ok",
        "text": text,
        **ocr_meta,
    }
    # Écriture atomique : on écrit à côté puis on renomme, pour ne jamais laisser
    # un enregistrement bronze à moitié écrit.
    final = _record_path(source_key)
    tmp = final + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    os.replace(tmp, final)
    return "ingested"


def run(src_dir: str = LANDING_DIR, dpi: int = DEFAULT_DPI) -> dict:
    """Ingère tous les PDF d'un dossier. Retourne un petit bilan."""
    if not os.path.isdir(src_dir):
        print(f"Aucun dossier source : {src_dir}. Lancez d'abord l'étape 1.")
        return {}

    counts = {"ingested": 0, "skipped": 0, "error": 0}
    for name in sorted(f for f in os.listdir(src_dir) if f.lower().endswith(".pdf")):
        result = ingest(os.path.join(src_dir, name), dpi=dpi)
        counts[result] += 1
        print(f"{name:45} {result}")
    print("-" * 60)
    print(f"Bilan : {counts['ingested']} ingérées, {counts['skipped']} déjà vues, "
          f"{counts['error']} en erreur.")
    if counts["error"]:
        print(f"Erreurs tracées dans {ERROR_LOG} (fichiers à retraiter).")
    return counts


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    dpi = DEFAULT_DPI
    for i, a in enumerate(sys.argv):
        if a == "--dpi" and i + 1 < len(sys.argv):
            dpi = int(sys.argv[i + 1])
    run(dpi=dpi)


if __name__ == "__main__":
    main()
