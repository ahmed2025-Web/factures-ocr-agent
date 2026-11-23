# Schéma de la couche silver (étape 4)

C'est le **contrat** entre le pipeline (bronze → silver), l'entrepôt (étape 6),
le serveur MCP (étape 7) et l'agent (étape 8). Toute modification se discute à
deux avant d'être mergée.

Stockage : un fichier Parquet par table dans `data/silver/` (ou un préfixe S3,
voir `SILVER_URI`). La silver est **reconstruite entièrement** à partir de la
bronze à chaque exécution : elle est déterministe et la bronze reste la seule
source de vérité.

## Pourquoi `DECIMAL` et pas `FLOAT` pour les euros

Un flottant binaire ne représente pas exactement `0,10` : `0.1 + 0.2 = 0.30000000000000004`.
Sur des sommes de factures, ces erreurs s'accumulent et rendent les contrôles
d'égalité (`HT + TVA = TTC`) faux. On utilise `Decimal` en Python et
`DECIMAL(14,2)` en SQL : arithmétique exacte au centime.

## Table `factures` — une ligne par facture acceptée

| Colonne | Type | Description |
|---|---|---|
| `numero_facture` | VARCHAR (clé) | ex. `A-2025-0003` — unique dans la table |
| `fournisseur` | VARCHAR | raison sociale de l'émetteur |
| `fournisseur_siret` | VARCHAR | 14 chiffres (texte : zéros de tête possibles) |
| `fournisseur_tva` | VARCHAR | n° TVA intracommunautaire |
| `client` | VARCHAR | raison sociale du client |
| `client_siret` | VARCHAR | 14 chiffres |
| `date_emission` | DATE | |
| `date_echeance` | DATE | |
| `categorie` | VARCHAR | ex. `Conseil` |
| `statut` | VARCHAR | statut de paiement : `Payée`, `En retard`, `Envoyée`… |
| `mode_paiement` | VARCHAR | |
| `iban` | VARCHAR | sans espaces |
| `total_ht` | DECIMAL(14,2) | tel que lu sur la facture |
| `total_tva` | DECIMAL(14,2) | tel que lu sur la facture |
| `total_ttc` | DECIMAL(14,2) | tel que lu sur la facture |
| `nb_lignes` | INTEGER | nombre de lignes de détail lues |
| `statut_qualite` | VARCHAR | `valide` ou `signalee` |
| `anomalies` | VARCHAR | codes d'anomalies séparés par `;` (vide si `valide`) |
| `source_key` | VARCHAR | nom du PDF d'origine (lien vers la bronze) |
| `source_sha256` | VARCHAR | empreinte du PDF d'origine |
| `extraction_method` | VARCHAR | `pdf_text` ou `ocr` |
| `bronze_ingested_at` | TIMESTAMP | date d'entrée en bronze |
| `silver_processed_at` | TIMESTAMP | date de construction de la silver |

## Table `lignes` — une ligne par ligne de facture

| Colonne | Type | Description |
|---|---|---|
| `numero_facture` | VARCHAR | référence `factures.numero_facture` |
| `num_ligne` | INTEGER | position dans la facture (1, 2, …) |
| `designation` | VARCHAR | |
| `quantite` | DECIMAL(14,3) | |
| `prix_unitaire_ht` | DECIMAL(14,2) | |
| `taux_tva` | DECIMAL(5,2) | en %, ex. `20.00` |
| `total_ht` | DECIMAL(14,2) | |

## Table `quarantaine` — documents écartés

| Colonne | Type | Description |
|---|---|---|
| `source_key` | VARCHAR | PDF d'origine |
| `source_sha256` | VARCHAR | |
| `numero_facture` | VARCHAR | si on a pu le lire, sinon NULL |
| `motif` | VARCHAR | code court, ex. `champ_obligatoire_manquant`, `doublon` |
| `details` | VARCHAR | explication lisible |
| `extraction_method` | VARCHAR | |
| `silver_processed_at` | TIMESTAMP | |

## Rejetée ou signalée ?

- **Rejetée** (→ `quarantaine`) : le document est inexploitable comme facture :
  champ obligatoire illisible (numéro, date d'émission, totaux), date ou montant
  impossible à interpréter, ou **doublon** d'une facture déjà acceptée. Une
  facture rejetée n'apparaît pas dans `factures`, donc pas dans les chiffres.
- **Signalée** (`statut_qualite = 'signalee'`) : la facture est lisible et
  gardée, mais un contrôle a échoué (montants incohérents, échéance avant
  émission, SIRET invalide…). Elle reste dans les chiffres, avec ses codes
  d'anomalie, pour qu'un humain la vérifie.

On ne **corrige jamais** automatiquement un montant : si l'OCR a mal lu
`7 567,26` en `7 567,28`, « corriger » reviendrait à inventer une valeur et à
masquer le problème. On signale, et la valeur lue reste traçable jusqu'au PDF.

## Codes d'anomalie (facture signalée)

| Code | Contrôle |
|---|---|
| `ht_plus_tva_neq_ttc` | `total_ht + total_tva ≠ total_ttc` |
| `somme_lignes_neq_ht` | somme des `lignes.total_ht ≠ total_ht` |
| `tva_calculee_neq_tva` | somme des `total_ht × taux_tva` des lignes ≠ `total_tva` |
| `ligne_qte_x_pu_neq_total` | pour au moins une ligne, `quantite × prix_unitaire_ht ≠ total_ht` |
| `aucune_ligne` | aucune ligne de détail lue |
| `echeance_avant_emission` | `date_echeance < date_emission` |
| `montant_negatif` | un total est négatif |
| `siret_invalide` | SIRET fournisseur ou client hors format / clé de Luhn fausse |
| `iban_invalide` | IBAN dont la clé de contrôle (mod 97) est fausse |
| `champ_secondaire_manquant` | fournisseur, client, statut ou échéance non lu |

Tolérance des contrôles de montants : 0,01 € par ligne (arrondis au centime).
