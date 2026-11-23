# factures-ocr-agent

Chaîne de bout en bout : **facture PDF → OCR → bronze → silver → entrepôt → serveur MCP → agent IA**.

Projet réalisé à deux. Voir la répartition dans [`docs/repartition.md`](docs/repartition.md).

## Architecture

```
PDF (bucket S3) ──► extraction / OCR ──► bronze ──► silver ──► entrepôt ──► serveur MCP ──► agent IA
```

| Couche | Rôle |
|--------|------|
| **bronze** | données brutes extraites, telles quelles, avec traçabilité (jamais modifiées) |
| **silver** | données propres, typées, contrôlées (+ quarantaine des rejets) |

## Organisation du code

```
src/
├── ingestion/    étape 1 — récupération S3 + détection texte/image
├── ocr/          étape 2 — client du modèle LightOnOCR-3
├── bronze/       étape 3 — couche bronze (incrémentale, traçable)
├── silver/       étape 4 — couche silver (typage, contrôles, quarantaine)
├── eval/         étape 5 — évaluation de la qualité de l'OCR
├── warehouse/    étape 6 — entrepôt (stockage / calcul séparés)
├── mcp_server/   étape 7 — serveur MCP (outils de lecture seule)
└── agent/        étape 8 — agent IA (LLM interchangeable par config)
docs/             rapport, répartition, notes
data/             zone d'arrivée locale (ignorée par git)
```

## Installation

Guide détaillé (dont **où créer les clés API**) : [docs/SETUP.md](docs/SETUP.md).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # puis renseigner les secrets (jamais commités)
```

> ⚠️ Les identifiants S3 et la clé API Hyperfluid ne doivent **jamais** apparaître
> dans le dépôt. Ils vivent uniquement dans `.env` (ignoré par git).

## Lancer (par étape)

Les commandes détaillées seront ajoutées au fur et à mesure dans chaque dossier
de `src/`. Chaque étape se valide indépendamment avant de passer à la suivante.

## Choix techniques

À documenter dans le rapport : chaque brique (stockage, OCR, entrepôt, MCP,
framework d'agent, LLM) est un choix libre qui doit être justifié.
