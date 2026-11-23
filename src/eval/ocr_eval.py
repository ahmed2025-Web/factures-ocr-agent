"""Étape 5 — mesurer la qualité de l'OCR, champ par champ.

Pour chaque facture de la vérité terrain (eval/verite_terrain.csv) et chaque
réglage testé (résolution du rendu, en DPI) :
    PDF ──rendu image (N DPI)──► OCR LightOnOCR-3 ──parseur silver──► valeurs
puis on compare chaque champ à la vérité terrain.

On utilise exactement le même parseur que la couche silver : on mesure donc la
qualité de la chaîne « OCR + parsing » telle qu'elle alimente la silver. La
commande `--silver` compare en plus la table silver elle-même à la vérité terrain.

Les sorties OCR sont mises en cache (data/eval/ocr_cache/) : relancer la
commande redonne le même tableau sans rappeler le modèle (reproductible, et
pas de coût). `--no-cache` force de nouveaux appels.

Usage :
    python -m src.eval.ocr_eval build-truth [--limit 20]   # vérité terrain depuis les PDF natifs
    python -m src.eval.ocr_eval run --dpi 100 200 [--sample 20] [--no-cache]
    python -m src.eval.ocr_eval silver                     # silver vs vérité terrain

Sorties : tableau dans le terminal + eval/resultats_ocr.md + eval/resultats_ocr.csv
"""

import os
import sys
import csv
import math
import time
import hashlib
import argparse
from decimal import Decimal, InvalidOperation

from ..ingestion.fetch import LANDING_DIR
from .truth import FIELDS, ROOT, load_truth, fields_of, build_from_native

CACHE_DIR = os.path.join(ROOT, "data", "eval", "ocr_cache")
RESULTS_MD = os.path.join(ROOT, "eval", "resultats_ocr.md")
RESULTS_CSV = os.path.join(ROOT, "eval", "resultats_ocr.csv")


# --- Comparaison d'un champ ---------------------------------------------------------
def same(field: str, expected: str, got: str) -> bool:
    """Égalité stricte, après normalisation minimale (espaces, format numérique).

    Volontairement stricte : un montant faux d'un centime est FAUX, et un nom
    mal orthographié aussi. On ne compte pas « presque juste ».
    """
    expected, got = (expected or "").strip(), (got or "").strip()
    if field.startswith("total_") or field == "nb_lignes":
        try:
            return Decimal(expected) == Decimal(got)
        except InvalidOperation:
            return expected == got
    return " ".join(expected.split()) == " ".join(got.split())


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalle de confiance à 95 % (Wilson) d'une proportion k/n.

    Sert à répondre à « quelle taille d'échantillon pour que la mesure ait un
    sens ? » : avec 10 factures, 90 % de réussite veut dire « entre 60 et 98 % ».
    """
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


# --- OCR avec cache ------------------------------------------------------------------
def ocr_text(pdf_path: str, dpi: int, use_cache: bool = True) -> tuple[str, float]:
    """Texte OCR de toutes les pages d'un PDF rendu à `dpi`. Retourne (texte, secondes).

    Clé de cache = empreinte du PDF + DPI + modèle : changer l'un des trois
    relance l'OCR.
    """
    from pypdf import PdfReader
    from ..ocr.client import ocr_pdf_page

    with open(pdf_path, "rb") as fh:
        sha = hashlib.sha256(fh.read()).hexdigest()[:16]
    model = os.environ.get("OCR_MODEL", "lightonocr-3-1b-test")
    cache = os.path.join(CACHE_DIR, f"{sha}_{dpi}dpi_{model}.md")
    timing = cache + ".time"
    if use_cache and os.path.isfile(cache):
        with open(cache, encoding="utf-8") as fh:
            text = fh.read()
        seconds = float(open(timing).read()) if os.path.isfile(timing) else 0.0
        return text, seconds

    parts, total = [], 0.0
    for i in range(len(PdfReader(pdf_path).pages)):
        text, elapsed = ocr_pdf_page(pdf_path, page_index=i, dpi=dpi)
        parts.append(text)
        total += elapsed
    text = "\n\n".join(parts)
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cache, "w", encoding="utf-8") as fh:
        fh.write(text)
    with open(timing, "w") as fh:
        fh.write(f"{total:.3f}")
    return text, total


# --- Évaluation -------------------------------------------------------------------
def evaluate(dpis: list[int], sample: int | None = None, use_cache: bool = True,
             raw_dir: str = LANDING_DIR) -> dict:
    """Retourne {dpi: {"fields": {champ: (justes, total)}, "seconds": [...], "errors": [...]}}."""
    truth = load_truth()
    if not truth:
        raise SystemExit("Vérité terrain vide : lancez d'abord `python -m src.eval.ocr_eval build-truth`.")
    truth = truth[:sample] if sample else truth

    results = {}
    for dpi in dpis:
        fields = {f: [0, 0] for f in FIELDS}
        seconds, errors, failed = [], [], 0
        for row in truth:
            pdf = os.path.join(raw_dir, row["source_key"])
            if not os.path.isfile(pdf):
                print(f"  PDF absent, ignoré : {row['source_key']}")
                continue
            try:
                text, elapsed = ocr_text(pdf, dpi, use_cache)
            except Exception as exc:  # OCR indisponible : on note, on continue
                failed += 1
                print(f"  OCR en échec ({dpi} DPI) {row['source_key']} : {exc}")
                continue
            seconds.append(elapsed)
            got = fields_of(text)
            for f in FIELDS:
                fields[f][1] += 1
                if same(f, row.get(f, ""), got[f]):
                    fields[f][0] += 1
                else:
                    errors.append((row["source_key"], f, row.get(f, ""), got[f]))
        results[dpi] = {"fields": fields, "seconds": seconds, "errors": errors, "failed": failed}
        print(f"  {dpi} DPI : {len(seconds)} facture(s) évaluée(s), {failed} échec(s) OCR")
    return results


def evaluate_silver() -> dict:
    """Compare la table silver `factures` à la vérité terrain (même numéro de source)."""
    import duckdb
    from ..silver.pipeline import SILVER_DIR

    path = os.path.join(SILVER_DIR, "factures.parquet")
    if not os.path.isfile(path):
        raise SystemExit("Silver absente : lancez `python -m src.silver.pipeline`.")
    con = duckdb.connect()
    cols = ", ".join(FIELDS)
    silver = {r[0]: dict(zip(FIELDS, r[1:])) for r in con.execute(
        f"SELECT source_key, {cols} FROM read_parquet(?)", [path]).fetchall()}
    fields = {f: [0, 0] for f in FIELDS}
    errors = []
    for row in load_truth():
        got = silver.get(row["source_key"])
        if got is None:
            continue
        for f in FIELDS:
            fields[f][1] += 1
            value = "" if got[f] is None else str(got[f])
            if same(f, row.get(f, ""), value):
                fields[f][0] += 1
            else:
                errors.append((row["source_key"], f, row.get(f, ""), value))
    return {"silver": {"fields": fields, "seconds": [], "errors": errors, "failed": 0}}


# --- Restitution ------------------------------------------------------------------
def report(results: dict) -> str:
    """Tableau markdown : précision par champ et par réglage, + temps moyen par facture."""
    settings = list(results)
    label = lambda s: f"{s} DPI" if isinstance(s, int) else str(s)
    head = "| Champ | " + " | ".join(label(s) for s in settings) + " |"
    sep = "|---|" + "---|" * len(settings)
    lines = [head, sep]
    for f in FIELDS:
        cells = []
        for s in settings:
            k, n = results[s]["fields"][f]
            lo, hi = wilson(k, n)
            cells.append(f"{100 * k / n:.0f} % ({k}/{n}, IC95 {100 * lo:.0f}–{100 * hi:.0f})" if n else "—")
        lines.append(f"| `{f}` | " + " | ".join(cells) + " |")

    total = []
    for s in settings:
        k = sum(v[0] for v in results[s]["fields"].values())
        n = sum(v[1] for v in results[s]["fields"].values())
        total.append(f"**{100 * k / n:.1f} %**" if n else "—")
    lines.append("| **tous champs** | " + " | ".join(total) + " |")

    if any(results[s]["seconds"] for s in settings):
        t = [f"{sum(results[s]['seconds']) / len(results[s]['seconds']):.1f} s"
             if results[s]["seconds"] else "—" for s in settings]
        lines.append("| temps OCR moyen / facture | " + " | ".join(t) + " |")
    return "\n".join(lines)


def write_outputs(results: dict) -> None:
    os.makedirs(os.path.dirname(RESULTS_MD), exist_ok=True)
    table = report(results)
    with open(RESULTS_MD, "w", encoding="utf-8") as fh:
        fh.write("# Résultats de l'évaluation OCR (généré par `python -m src.eval.ocr_eval`)\n\n")
        fh.write(f"Vérité terrain : `eval/verite_terrain.csv` — {time.strftime('%Y-%m-%d %H:%M')}\n\n")
        fh.write(table + "\n\n## Erreurs détaillées\n\n| Réglage | Fichier | Champ | Attendu | Lu |\n|---|---|---|---|---|\n")
        for s, r in results.items():
            for src, f, exp, got in r["errors"]:
                fh.write(f"| {s} | {src} | `{f}` | {exp} | {got or '*(vide)*'} |\n")
    with open(RESULTS_CSV, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["reglage", "champ", "justes", "total", "precision"])
        for s, r in results.items():
            for f, (k, n) in r["fields"].items():
                w.writerow([s, f, k, n, f"{k / n:.4f}" if n else ""])
    print("\n" + table)
    print(f"\nDétail des erreurs : {RESULTS_MD}")


def main(argv: list[str] | None = None) -> None:
    from dotenv import load_dotenv

    load_dotenv()
    ap = argparse.ArgumentParser(prog="python -m src.eval.ocr_eval")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build-truth", help="vérité terrain depuis les PDF natifs de data/raw")
    b.add_argument("--limit", type=int)
    r = sub.add_parser("run", help="évaluer l'OCR à plusieurs résolutions")
    r.add_argument("--dpi", type=int, nargs="+", default=[100, 200])
    r.add_argument("--sample", type=int)
    r.add_argument("--no-cache", action="store_true")
    sub.add_parser("silver", help="comparer la table silver à la vérité terrain")
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])

    if args.cmd == "build-truth":
        n = build_from_native(limit=args.limit)
        print(f"{n} facture(s) ajoutée(s) à la vérité terrain.")
    elif args.cmd == "run":
        write_outputs(evaluate(args.dpi, args.sample, not args.no_cache))
    else:
        write_outputs(evaluate_silver())


if __name__ == "__main__":
    main()
