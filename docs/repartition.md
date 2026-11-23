# Répartition du travail

On est deux sur le projet : Ahmed et Salma. On s'est partagé les étapes pour avoir
à peu près la même charge chacun, et surtout on commite au fur et à mesure (après
chaque étape, pas tout d'un coup à la fin).

## Qui fait quoi

**Ahmed** — la partie qui fabrique la donnée, du PDF brut jusqu'aux tables propres :
- étape 1 : récupération des factures (S3) et détection texte/image
- étape 2 : OCR avec LightOnOCR-3
- étape 3 : couche bronze
- étape 8 : l'agent (avec le LLM qu'on peut changer par config)

**Salma** — la partie qui exploite la donnée et la met au service de l'IA :
- étape 4 : couche silver
- étape 5 : évaluation de la qualité de l'OCR
- étape 6 : l'entrepôt
- étape 7 : le serveur MCP

Le reste (étape 9 industrialisation, la doc de lancement, le rapport et la démo)
on le fait à deux.

On a chacun un gros morceau : la silver pour Salma, l'agent pour Ahmed.

## Là où nos deux parties se rejoignent

La jonction, c'est le schéma de la couche silver (les tables, les colonnes, les
types). On le fixe ensemble dès le début : comme ça Salma peut avancer sur
l'entrepôt, le MCP et l'agent avec quelques factures d'exemple, sans attendre
qu'Ahmed ait fini de remplir tout le pipeline.

## Git

- `main` reste stable.
- Une branche par étape (ex. `etape-1-ingestion`).
- Pull request relue par l'autre avant de merger.
- Chacun commite avec son propre compte GitHub.
- Aucun secret dans le dépôt : tout ce qui est clé ou identifiant va dans `.env`.
