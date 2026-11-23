# Résultats de l'évaluation OCR (produit par la commande `python -m src.eval.ocr_eval run`)

Vérité terrain : `eval/verite_terrain.csv` — 2026-11-23 17:07

| Champ | 60 DPI | 100 DPI | 200 DPI |
|---|---|---|---|
| `numero_facture` | 100 % (20/20, IC95 84–100) | 100 % (20/20, IC95 84–100) | 100 % (20/20, IC95 84–100) |
| `fournisseur` | 100 % (20/20, IC95 84–100) | 100 % (20/20, IC95 84–100) | 100 % (20/20, IC95 84–100) |
| `client` | 90 % (18/20, IC95 70–97) | 100 % (20/20, IC95 84–100) | 100 % (20/20, IC95 84–100) |
| `date_emission` | 100 % (20/20, IC95 84–100) | 100 % (20/20, IC95 84–100) | 100 % (20/20, IC95 84–100) |
| `date_echeance` | 100 % (20/20, IC95 84–100) | 100 % (20/20, IC95 84–100) | 100 % (20/20, IC95 84–100) |
| `statut` | 100 % (20/20, IC95 84–100) | 100 % (20/20, IC95 84–100) | 100 % (20/20, IC95 84–100) |
| `categorie` | 100 % (20/20, IC95 84–100) | 100 % (20/20, IC95 84–100) | 100 % (20/20, IC95 84–100) |
| `fournisseur_siret` | 100 % (20/20, IC95 84–100) | 100 % (20/20, IC95 84–100) | 100 % (20/20, IC95 84–100) |
| `client_siret` | 100 % (20/20, IC95 84–100) | 100 % (20/20, IC95 84–100) | 100 % (20/20, IC95 84–100) |
| `iban` | 70 % (14/20, IC95 48–85) | 100 % (20/20, IC95 84–100) | 100 % (20/20, IC95 84–100) |
| `total_ht` | 100 % (20/20, IC95 84–100) | 100 % (20/20, IC95 84–100) | 100 % (20/20, IC95 84–100) |
| `total_tva` | 100 % (20/20, IC95 84–100) | 100 % (20/20, IC95 84–100) | 100 % (20/20, IC95 84–100) |
| `total_ttc` | 100 % (20/20, IC95 84–100) | 100 % (20/20, IC95 84–100) | 100 % (20/20, IC95 84–100) |
| `nb_lignes` | 85 % (17/20, IC95 64–95) | 100 % (20/20, IC95 84–100) | 100 % (20/20, IC95 84–100) |
| **tous champs** | **96.1 %** | **100.0 %** | **100.0 %** |
| temps OCR moyen / facture | 4.4 s | 4.9 s | 5.9 s |

## Erreurs détaillées

| Réglage | Fichier | Champ | Attendu | Lu |
|---|---|---|---|---|
| 60 | facture_A-2025-0001_texte.pdf | `iban` | FR1578820812191361939909169 | FR1576820812191361939909169 |
| 60 | facture_A-2026-0002_texte.pdf | `nb_lignes` | 2 | 3 |
| 60 | facture_A-2026-0006_texte.pdf | `nb_lignes` | 2 | 3 |
| 60 | facture_A-2026-0008_texte.pdf | `iban` | FR1578820812191361939909169 | FR1576820812191361939909169 |
| 60 | facture_A-2026-0011_texte.pdf | `nb_lignes` | 2 | 3 |
| 60 | facture_BS-2025-0002_scan.pdf | `client` | Diallo Barbe S.A.R.L. | Delo Barbe S.A.R.L. |
| 60 | facture_BS-2025-0003_texte.pdf | `iban` | FR4545053315869232260256342 | FR4546053315869232260256342 |
| 60 | facture_BS-2026-0004_texte.pdf | `iban` | FR4545053315869232260256342 | FR4546053315869232260256342 |
| 60 | facture_C-2025-0002_texte.pdf | `client` | Martineau | Martinneau |
| 60 | facture_C-2025-0015_texte.pdf | `iban` | FR5476483503056413953767242 | FRS476483503056413053767242 |
| 60 | facture_C-2026-0001_texte.pdf | `iban` | FR5476483503056413953767242 | FRS476483503056413053767242 |
