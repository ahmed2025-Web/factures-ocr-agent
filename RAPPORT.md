# Rapport — De la facture scannée à l'agent IA

Ahmed Amine EL AMRI et Salma EL ANNABY — novembre 2026

La chaîne lit les 100 factures du bucket S3 (50 natives, 50 scannées), les range en
couches bronze et silver, les rend interrogeables en SQL, et un agent répond en
français en passant uniquement par un serveur MCP en lecture seule.

## 1. Architecture

```
 Bucket S3 ──► Détection ──► Extraction ─────────► Bronze ─────► Silver ─────► Entrepôt ──► Serveur MCP ──► Agent
 100 PDF       texte/image   pypdf (natif)         JSON brut     Parquet typé   DuckDB       6 outils        LLM au choix
               (pypdf)       LightOnOCR-3 (scan)   + SHA-256     + quarantaine  vues seules  lecture seule   ou Claude Code
                                                                     │
                                                                     └──► Évaluation OCR (vérité terrain)
```

| Membre | Étapes |
|---|---|
| Ahmed | 1 récupération S3, 2 OCR, 3 bronze, 8 agent |
| Salma | 4 silver, 5 évaluation OCR, 6 entrepôt, 7 serveur MCP |
| Ensemble | 9 industrialisation, documentation, rapport |

Lancement : voir [docs/SETUP.md](docs/SETUP.md) (installation, `.env`, une commande par étape).

## 2. Choix techniques

| Brique | Choix | Pourquoi |
|---|---|---|
| Langage | Python 3.12 | Un seul langage pour S3, PDF, OCR, SQL et MCP |
| Détection | pypdf (≥ 20 caractères extraits = texte) | Décision sur le contenu, pas sur le nom du fichier |
| OCR | LightOnOCR-3 (API compatible OpenAI), 200 DPI | Imposé ; isolé dans `ocr_image()`, changer de moteur = une fonction |
| Bronze | un JSON par document | Brut, immuable, traçable, lisible en SQL |
| Silver | Parquet, montants en `DECIMAL(14,2)` | Types conservés ; un float ne représente pas 0,10 exactement |
| Entrepôt | DuckDB, vues sur les fichiers | Stockage et calcul séparés, aucune copie, aucun serveur |
| MCP | SDK officiel Python (FastMCP), stdio | Marche avec Claude Desktop, Claude Code et notre agent |
| Agent | SDK `openai` + `LLM_PROVIDER` / `LLM_MODEL` | Même API chez Hyperfluid, Groq, Ollama : on change la config, pas le code |
| Secrets | `.env` ignoré par git | Aucun identifiant dans le dépôt |

## 3. Bronze et silver

- **Bronze** : 100 documents, 50 OCRisés en 7 min 52 s. 2 scans en erreur 503 (service
  partagé saturé), tracés sans arrêter le pipeline ; à la relance, 98 fichiers sautés sans
  appel OCR et les 2 retraités. Un fichier « déjà vu » = même nom **et** même empreinte.
- **Silver** : **100 factures acceptées, 271 lignes, 0 rejet, 1 signalée**.
  - *Rejet* (table `quarantaine` + motif) : numéro, date ou totaux illisibles, doublon.
  - *Signalement* (`statut_qualite = 'signalee'` + codes) : HT + TVA ≠ TTC, somme des
    lignes ≠ HT, quantité × prix ≠ total, échéance avant émission, IBAN invalide…
  - On ne corrige jamais un montant : ce serait inventer une valeur.
- La facture signalée, `V-2025-0001`, affiche sur le scan lui-même « Total TTC 99 999,99 € »
  pour 148,26 € HT : anomalie volontaire du jeu, bien lue et bien détectée.

## 4. Évaluation de l'OCR

Vérité terrain de 20 factures : 15 PDF natifs (texte exact) rendus en image puis OCRisés,
et 5 vrais scans relus à la main (saisie contrôlée : clé IBAN, HT + TVA = TTC). Comparaison
stricte champ par champ (`python -m src.eval.ocr_eval run --dpi 60 100 200`).

| Champ | 60 DPI | 100 DPI | 200 DPI |
|---|---|---|---|
| iban | 70 % | 100 % | 100 % |
| nb_lignes | 85 % | 100 % | 100 % |
| client | 90 % | 100 % | 100 % |
| autres champs (numéro, dates, montants, SIRET…) | 100 % | 100 % | 100 % |
| **tous champs** | **96,1 %** | **100 %** | **100 %** |
| temps OCR / facture | 4,4 s | 4,9 s | 5,9 s |

- Champs fragiles : les longues suites sans contexte. L'IBAN (27 caractères) casse le
  premier à basse résolution (`8`→`6`, `5`→`S`) ; puis les noms propres (« Diallo » → « Delo »).
- Les montants restent justes même à 60 DPI.
- 100 DPI suffit ici ; 200 DPI gardé en bronze par prudence (scans réels plus bruités).
- Limite : 20 factures → intervalle de confiance 84–100 % (Wilson) ; il en faudrait ~100.
  Détails : [eval/README.md](eval/README.md).

## 5. Entrepôt, MCP et agent

- **Entrepôt** : vues DuckDB (`bronze.documents`, `silver.factures`, `silver.lignes`,
  `silver.quarantaine`, `gold.*`) sur les fichiers. Les programmes ouvrent une connexion en
  mémoire (pas de verrou) ; DBeaver ouvre `data/entrepot.duckdb` en lecture seule. Les vues
  se régénèrent depuis `DATA_ROOT` (dossier local ou `s3://`) : chemins valides partout.
- **Serveur MCP** : 6 outils (`lister_factures`, `compter_et_totaliser`, `detail_facture`,
  `decrire_schema`, `requete_sql`, `indicateur_gold`), chacun renvoie le SQL exécuté.
  Sécurité : base `read_only`, accès fichiers coupé, configuration verrouillée, SQL libre
  limité à un seul `SELECT`, filtres paramétrés. Sans ce dernier verrou, `COPY … TO`
  pouvait écraser la silver. `tests/test_mcp.py` appelle chaque outil et rejoue 17 attaques.
  Démo Claude Code : [docs/mcp.md](docs/mcp.md).
- **Agent avec deux LLM** (même code, seule la config change : `LLM_MODEL`,
  `HYPERFLUID_LLM_URL`). Mêmes 3 questions enchaînées, conversations complètes dans
  [docs/agent/](docs/agent/) :

| Question | Vérité (SQL) | gemma-4-12b | granite-4-2-8b |
|---|---|---|---|
| TTC des factures en retard en 2025 | 106 886,43 € | 106 886,43 € (`compter_et_totaliser`) | 106 886,43 € (`compter_et_totaliser`) |
| Plus gros encours non payé | Aubry, 128 685,11 € | Aubry, 128 685,11 € (`indicateur_gold`) | Aubry, 128 685,11 € (`indicateur_gold`) |
| « Et ce fournisseur, en 2026 ? » | 7 factures | 7 (`compter_et_totaliser`) | 7 (`lister_factures`) |
| Durée des 3 questions | | 9 s | 11 s |

Observations : les deux modèles donnent des chiffres exacts et gardent le fil (« ce
fournisseur » = Aubry). gemma choisit l'outil le plus direct ; granite liste les 7 factures
pour les compter (deux requêtes au lieu d'une). Les
chiffres viennent toujours des outils, jamais du modèle. Dans Claude Code, le modèle a en
revanche *supposé* une erreur d'OCR sur `V-2025-0001` : les chiffres sont fiables,
l'explication reste une hypothèse.

## 6. Industrialisation (priorités)

1. **Débit de l'OCR** (seule étape lente, ~5 s/page) : file de tâches + plusieurs workers,
   retry avec attente croissante (erreurs 503 dès 100 factures). L'incrémental par empreinte
   rend les relances sans risque.
2. **Orchestration** : bronze → silver → vues déclenchés à chaque dépôt dans le bucket
   (Airflow, Dagster, ou tâche planifiée).
3. **Conteneurs sans état** : données dans S3 (`DATA_ROOT=s3://…`), DuckDB les lit sur place.
4. **Secrets et accès** : coffre (Vault), une clé S3 par service (lecture seule pour le MCP),
   MCP en HTTP authentifié pour plusieurs utilisateurs, journal des appels avec leur SQL.
5. **Supervision** : taux de quarantaine et de signalement, temps et erreurs OCR ; une hausse
   du taux de quarantaine = nouveau gabarit de fournisseur à traiter.
6. **Tests en CI** (32 tests, < 5 s) et évaluation OCR rejouée chaque mois.

Coûts : l'OCR domine ; on n'OCRise jamais un PDF natif ni un fichier déjà vu, et 100 DPI
économiserait ~20 % de temps OCR. Déjà en place : incrémental, reprise sur erreur,
`DATA_ROOT` S3, tests automatisés, clé S3 en lecture seule.

## 7. Difficultés et limites

| Difficulté | Solution |
|---|---|
| Vrais PDF natifs : valeur sous le libellé, une cellule par ligne (aucun total lu au début) | lecture de la ligne suivante, machine à états, tests sur une vraie facture |
| OCR : totaux parfois dans un 2e tableau HTML | tableaux convertis en lignes avant lecture |
| SIRET fictifs (0/30 clients valides en Luhn) : toutes les factures signalées | contrôle du format seulement |
| `COPY … TO` passait la base en lecture seule | un seul `SELECT` autorisé |
| Service OCR partagé lent, erreurs 503 | erreurs tracées, relance, cache pour l'évaluation |

Limites : échantillon d'évaluation de 20 factures (5 vrais scans), un seul gabarit de
facture, silver reconstruite entièrement à chaque passage. Pistes : comparer LightOnOCR-3 à
LightOnOCR-2 (disponible sur la plateforme), générateur de factures avec anomalies, CI.
