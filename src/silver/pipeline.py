"""Étape 4 — couche silver : données propres, typées, contrôlées.

    bronze (data/bronze/*.json) ──parse──► contrôles ──► dédoublonnage ──►
        data/silver/factures.parquet
        data/silver/lignes.parquet
        data/silver/quarantaine.parquet

La silver est reconstruite ENTIÈREMENT à chaque exécution à partir de la bronze :
c'est rapide (quelques centaines de factures), déterministe, et la bronze reste
la seule source de vérité. Les fichiers sont écrits à côté puis renommés, pour
qu'un lecteur (entrepôt, MCP, DBeaver) ne voie jamais un fichier à moitié écrit.

Critères de l'étape :
  - aucune facture valide perdue : tout document de la bronze finit soit dans
    `factures`, soit dans `quarantaine` (le bilan le vérifie) ;
  - aucun doublon : un numéro de facture n'apparaît qu'une fois dans `factures` ;
  - chaque facture a un statut qualité, chaque rejet un motif ;
  - les montants incohérents sont signalés (voir checks.py).

Usage :
    python -m src.silver.pipeline
"""

import os
import glob
import json
import datetime

from .parser import parse_invoice
from .checks import motif_rejet, anomalies

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BRONZE_DIR = os.environ.get("BRONZE_DIR", os.path.join(ROOT, "data", "bronze"))
SILVER_DIR = os.environ.get("SILVER_DIR", os.path.join(ROOT, "data", "silver"))

# Ordre de préférence quand deux documents portent le même numéro : le texte
# natif est plus fiable que l'OCR.
_METHOD_RANK = {"pdf_text": 0, "ocr": 1}

DDL = {
    "factures": """
        numero_facture VARCHAR, fournisseur VARCHAR, fournisseur_siret VARCHAR,
        fournisseur_tva VARCHAR, client VARCHAR, client_siret VARCHAR,
        date_emission DATE, date_echeance DATE, categorie VARCHAR, statut VARCHAR,
        mode_paiement VARCHAR, iban VARCHAR,
        total_ht DECIMAL(14,2), total_tva DECIMAL(14,2), total_ttc DECIMAL(14,2),
        nb_lignes INTEGER, statut_qualite VARCHAR, anomalies VARCHAR,
        source_key VARCHAR, source_sha256 VARCHAR, extraction_method VARCHAR,
        bronze_ingested_at TIMESTAMP, silver_processed_at TIMESTAMP""",
    "lignes": """
        numero_facture VARCHAR, num_ligne INTEGER, designation VARCHAR,
        quantite DECIMAL(14,3), prix_unitaire_ht DECIMAL(14,2),
        taux_tva DECIMAL(5,2), total_ht DECIMAL(14,2)""",
    "quarantaine": """
        source_key VARCHAR, source_sha256 VARCHAR, numero_facture VARCHAR,
        motif VARCHAR, details VARCHAR, extraction_method VARCHAR,
        silver_processed_at TIMESTAMP""",
}


def load_bronze(bronze_dir: str = BRONZE_DIR) -> list[dict]:
    """Enregistrements bronze 'ok', triés par nom (ordre stable = sortie stable)."""
    records = []
    for path in sorted(glob.glob(os.path.join(bronze_dir, "*.json"))):
        try:
            with open(path, encoding="utf-8") as fh:
                rec = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        if rec.get("status") == "ok":
            records.append(rec)
    return records


def transform(records: list[dict], now: datetime.datetime | None = None) -> dict:
    """Bronze → {'factures': [...], 'lignes': [...], 'quarantaine': [...]} (dicts).

    Fonction pure (pas d'E/S) : c'est elle que testent les tests unitaires.
    """
    now = now or datetime.datetime.now().replace(microsecond=0)
    quarantaine, candidates = [], []

    for rec in records:
        f = parse_invoice(rec.get("text", ""))
        base = {
            "source_key": rec.get("source_key"),
            "source_sha256": rec.get("source_sha256"),
            "extraction_method": rec.get("extraction_method"),
            "silver_processed_at": now,
        }
        rejet = motif_rejet(f)
        if rejet:
            quarantaine.append({**base, "numero_facture": f.numero_facture,
                                "motif": rejet[0], "details": rejet[1]})
            continue
        candidates.append((f, anomalies(f), rec, base))

    # Dédoublonnage : un seul document par numéro de facture.
    def preference(item):
        f, codes, rec, _ = item
        return (_METHOD_RANK.get(rec.get("extraction_method"), 9), len(codes),
                rec.get("ingested_at") or "", rec.get("source_key") or "")

    by_numero: dict[str, list] = {}
    for item in candidates:
        by_numero.setdefault(item[0].numero_facture, []).append(item)

    factures, lignes = [], []
    for numero in sorted(by_numero):
        kept, *others = sorted(by_numero[numero], key=preference)
        for f, _, _, base in others:
            quarantaine.append({**base, "numero_facture": numero, "motif": "doublon",
                                "details": f"même numéro que {kept[3]['source_key']} (conservé)"})

        f, codes, rec, base = kept
        factures.append({
            "numero_facture": numero,
            "fournisseur": f.fournisseur, "fournisseur_siret": f.fournisseur_siret,
            "fournisseur_tva": f.fournisseur_tva,
            "client": f.client, "client_siret": f.client_siret,
            "date_emission": f.date_emission, "date_echeance": f.date_echeance,
            "categorie": f.categorie, "statut": f.statut,
            "mode_paiement": f.mode_paiement, "iban": f.iban,
            "total_ht": f.total_ht, "total_tva": f.total_tva, "total_ttc": f.total_ttc,
            "nb_lignes": len(f.lignes),
            "statut_qualite": "signalee" if codes else "valide",
            "anomalies": ";".join(codes),
            "source_key": base["source_key"], "source_sha256": base["source_sha256"],
            "extraction_method": base["extraction_method"],
            "bronze_ingested_at": _ts(rec.get("ingested_at")),
            "silver_processed_at": now,
        })
        for i, l in enumerate(f.lignes, start=1):
            lignes.append({"numero_facture": numero, "num_ligne": i,
                           "designation": l.designation, "quantite": l.quantite,
                           "prix_unitaire_ht": l.prix_unitaire_ht,
                           "taux_tva": l.taux_tva, "total_ht": l.total_ht})

    quarantaine.sort(key=lambda q: (q["source_key"] or "", q["motif"]))
    return {"factures": factures, "lignes": lignes, "quarantaine": quarantaine}


def _ts(value: str | None):
    try:
        return datetime.datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def write_parquet(tables: dict, silver_dir: str = SILVER_DIR) -> None:
    """Écrit chaque table en Parquet, avec les types SQL du schéma (DECIMAL, DATE…)."""
    import duckdb

    os.makedirs(silver_dir, exist_ok=True)
    con = duckdb.connect()
    for name, ddl in DDL.items():
        cols = [c.split()[0] for c in ddl.replace("\n", " ").split(",")]
        con.execute(f"CREATE TABLE {name} ({ddl})")
        rows = [[r.get(c) for c in cols] for r in tables[name]]
        if rows:
            con.executemany(f"INSERT INTO {name} VALUES ({', '.join('?' * len(cols))})", rows)
        final = os.path.join(silver_dir, f"{name}.parquet")
        tmp = final + ".tmp"
        con.execute(f"COPY {name} TO '{tmp}' (FORMAT parquet)")
        os.replace(tmp, final)  # remplacement atomique
    con.close()


def run(bronze_dir: str = BRONZE_DIR, silver_dir: str = SILVER_DIR) -> dict:
    records = load_bronze(bronze_dir)
    if not records:
        print(f"Aucun enregistrement bronze dans {bronze_dir}. Lancez d'abord l'étape 3.")
        return {}
    tables = transform(records)
    write_parquet(tables, silver_dir)

    fac, q = tables["factures"], tables["quarantaine"]
    signalees = [f for f in fac if f["statut_qualite"] == "signalee"]
    print(f"Bronze : {len(records)} document(s)")
    print(f"Silver : {len(fac)} facture(s) dont {len(signalees)} signalée(s), "
          f"{len(tables['lignes'])} ligne(s) de détail")
    print(f"Quarantaine : {len(q)} document(s)")
    for item in q:
        print(f"  - {item['source_key']:40} {item['motif']:28} {item['details']}")
    if signalees:
        print("Factures signalées :")
        for f in signalees:
            print(f"  - {f['numero_facture']:15} {f['source_key']:40} {f['anomalies']}")
    # Contrôle « aucune facture perdue » : chaque document est quelque part.
    assert len(fac) + len(q) == len(records), "document perdu entre bronze et silver"
    print(f"Fichiers écrits dans {silver_dir}")
    return tables


def build_silver() -> dict:
    return run()


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    run()


if __name__ == "__main__":
    main()
