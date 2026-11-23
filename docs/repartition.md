# Répartition du travail

Binôme : **Ahmed** et **sa binôme**. Objectif : contribution équilibrée en
qualité (pas seulement en nombre de tâches), et commits réguliers après chaque
sous-étape.

## Qui fait quoi

| Étape | Sujet | Responsable | Points |
|-------|-------|-------------|--------|
| 1 | Récupération S3 + détection texte/image | Ahmed | 1 |
| 2 | Intégration OCR LightOnOCR-3 | Ahmed | 2 |
| 3 | Couche bronze | Ahmed | 2 |
| 8 | Agent IA (LLM interchangeable) | Ahmed | 2 |
| 4 | Couche silver | Binôme | 3 |
| 5 | Évaluation de la qualité OCR | Binôme | 2 |
| 6 | Entrepôt (stockage / calcul) | Binôme | 1 |
| 7 | Serveur MCP | Binôme | 3 |
| 9 | Industrialisation | Partagé | 2 |
| — | Lancement / doc | Partagé | 1 |
| — | Rapport / démo | Partagé | 1 |

Chacun : ~10 points de responsabilité, un livrable « lourd » chacun
(Ahmed : bronze+agent ; binôme : silver+MCP).

## Le contrat entre les deux moitiés

La frontière est le **schéma de la couche silver**. À définir ensemble très tôt
(tables, colonnes, types) pour que la binôme puisse construire entrepôt + MCP +
agent sur une petite base d'exemple pendant que la partie ingestion se remplit.

## Workflow git

- `main` reste stable.
- Une branche par étape : `etape-1-ingestion`, `etape-8-agent`, …
- Pull Request relue par l'autre avant merge.
- Un commit par sous-étape, message clair, sous l'identité git de chacun.
- Aucun secret commité (tout dans `.env`).
