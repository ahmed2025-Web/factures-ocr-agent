# Démarrer sur le projet

Guide pour installer le projet et obtenir les accès nécessaires. Valable pour
un nouvel arrivant (Salma, un correcteur, etc.).

## 1. Installer

```bash
git clone git@github.com:ahmed2025-Web/factures-ocr-agent.git
cd factures-ocr-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> À refaire à chaque nouveau terminal : `cd` dans le dossier + `source .venv/bin/activate`.
> Tu es prêt quand tu vois `(.venv)` devant ton prompt.

## 2. Configurer les secrets

Les clés et identifiants ne sont **jamais** dans le dépôt. On les met dans un
fichier `.env` local (ignoré par git) :

```bash
cp .env.example .env
```

Puis on remplit `.env`. Voici **où récupérer chaque valeur** :

### Identifiants S3 — pour l'étape 1 (récupérer les factures)
`S3_ACCESS_KEY` et `S3_SECRET_KEY` sont **fournis par l'enseignant**.
L'URL (`S3_ENDPOINT_URL`) et le bucket (`factures`) sont déjà pré-remplis.

### Clé API OCR — pour les étapes 2 et 5 (OCR + évaluation)
Chacun crée **sa propre clé** dans la console Hyperfluid :

1. Console Hyperfluid → menu de gauche **AI Gateway** → onglet **API Keys**.
2. Bouton vert **« Create API Key »**, donne un nom (ex. `salma-ocr`), scope `model:*`.
3. **Copie le token `sk-hf-...` tout de suite** : il n'est affiché qu'une seule
   fois. Colle-le dans `.env` après `OCR_API_KEY=`.

L'URL du point d'accès (`OCR_API_URL`) et le nom du modèle (`OCR_MODEL`) sont
déjà dans `.env.example`. Si besoin, on les retrouve sur la page du modèle
`lightonocr-3-1b-test` → onglet **Endpoint**.

### Clé LLM de l'agent — pour l'étape 8
Par défaut l'agent utilise Groq (gratuit). Crée une clé sur
<https://console.groq.com> et mets-la dans `GROQ_API_KEY`. Le fournisseur se
change avec `LLM_PROVIDER` (ex. `groq` ou `ollama`).

## 3. Lancer (par étape)

```bash
# Étape 1 — télécharger les factures et les classer texte/image
python3 -m src.ingestion.fetch

# Étape 2 — OCR d'une page de facture (texte + temps de traitement)
python3 -m src.ocr.client ~/Téléchargements/une_facture_scan.pdf
# option : --dpi 300 pour tester une autre résolution
```

```bash
# Étape 3 — couche bronze (texte natif ou OCR, incrémental)
python3 -m src.bronze.pipeline

# Étape 4 — couche silver : data/silver/{factures,lignes,quarantaine}.parquet
python3 -m src.silver.pipeline
# affiche le bilan : factures acceptées, signalées (avec anomalies), quarantaine (avec motif)
```

```bash
# Étape 5 — évaluation de l'OCR (voir eval/README.md)
python3 -m src.eval.ocr_eval build-truth --limit 30
python3 -m src.eval.ocr_eval run --dpi 100 200 300
```

Schéma des tables et règles qualité : [docs/schema-silver.md](schema-silver.md).

Tests : `python3 -m pytest`

## Besoin d'un exemple de sortie OCR ?

Pour voir le format que produit l'OCR (utile pour l'étape 4 silver) sans avoir à
tout lancer : voir [docs/exemple-sortie-ocr.md](exemple-sortie-ocr.md). On peut
aussi en regénérer un avec `python3 -m src.ocr.client une_facture_scan.pdf`.
