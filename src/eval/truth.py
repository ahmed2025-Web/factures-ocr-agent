"""Étape 5 — vérité terrain.

Comment obtenir une vérité terrain fiable sans y passer des heures ?

Idée principale : les PDF **natifs** contiennent le texte exact de la facture.
Si on les « rastérise » (rendu en image, comme un scan), on obtient des images
dont on connaît la vérité exacte, sans saisie manuelle :

    PDF natif ──pypdf──► texte exact ──parseur──► vérité terrain
         └──rendu image──► OCR ──parseur──► valeurs à évaluer

On complète avec des lignes saisies à la main pour de VRAIS scans (relues sur le
PDF), parce qu'un vrai scan est plus difficile qu'un rendu propre (bruit,
inclinaison, compression). Les deux sources sont distinguées par la colonne
`origine` : `natif_rasterise` ou `manuel`.

Fichier : eval/verite_terrain.csv (versionné dans git, contrairement à data/).
"""

import csv
import os

from ..ingestion.fetch import has_text_layer, LANDING_DIR
from ..silver.parser import parse_invoice

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TRUTH_CSV = os.path.join(ROOT, "eval", "verite_terrain.csv")

# Champs évalués (ceux de la table silver `factures` qui viennent du document).
FIELDS = [
    "numero_facture", "fournisseur", "client", "date_emission", "date_echeance",
    "statut", "categorie", "fournisseur_siret", "client_siret", "iban",
    "total_ht", "total_tva", "total_ttc", "nb_lignes",
]
COLUMNS = ["source_key", "origine"] + FIELDS


def fields_of(text: str) -> dict:
    """Valeurs des champs évalués, en texte (format stable pour le CSV)."""
    f = parse_invoice(text)
    out = {}
    for name in FIELDS:
        value = len(f.lignes) if name == "nb_lignes" else getattr(f, name)
        out[name] = "" if value is None else str(value)
    return out


def load_truth(path: str = TRUTH_CSV) -> list[dict]:
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def save_truth(rows: list[dict], path: str = TRUTH_CSV) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for row in sorted(rows, key=lambda r: r["source_key"]):
            writer.writerow({c: row.get(c, "") for c in COLUMNS})


def build_from_native(raw_dir: str = LANDING_DIR, path: str = TRUTH_CSV, limit: int | None = None) -> int:
    """Ajoute à la vérité terrain les PDF natifs de raw_dir (garde les lignes manuelles).

    Une ligne n'est ajoutée que si le parseur a lu tous les champs obligatoires
    ET que les montants sont cohérents (HT + TVA = TTC) : on ne veut pas d'une
    vérité terrain elle-même fausse.
    """
    from pypdf import PdfReader
    from decimal import Decimal

    rows = {r["source_key"]: r for r in load_truth(path)}
    added = 0
    for name in sorted(os.listdir(raw_dir)):
        if limit is not None and added >= limit:
            break
        pdf = os.path.join(raw_dir, name)
        if not name.lower().endswith(".pdf") or name in rows or not has_text_layer(pdf):
            continue
        text = "\n".join(p.extract_text() or "" for p in PdfReader(pdf).pages)
        values = fields_of(text)
        try:
            ok = Decimal(values["total_ht"]) + Decimal(values["total_tva"]) == Decimal(values["total_ttc"])
        except ArithmeticError:
            ok = False
        if not (ok and values["numero_facture"] and values["date_emission"]):
            print(f"  ignoré (lecture incomplète du texte natif) : {name}")
            continue
        rows[name] = {"source_key": name, "origine": "natif_rasterise", **values}
        added += 1
    save_truth(list(rows.values()), path)
    return added
