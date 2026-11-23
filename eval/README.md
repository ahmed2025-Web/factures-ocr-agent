# Évaluation de la qualité de l'OCR (étape 5)

## Méthode

1. **Vérité terrain** (`verite_terrain.csv`, versionnée) :
   - `natif_rasterise` : les PDF *natifs* ont un texte exact. On le lit avec
     pypdf + le parseur silver, et on ne garde une ligne que si elle est complète
     et cohérente (HT + TVA = TTC). On fait ensuite passer **ces mêmes PDF**
     par l'OCR, rendus en image comme un scan. Avantage : vérité exacte, sans
     saisie, sur autant de factures qu'on veut.
   - `manuel` : quelques **vrais scans**, relus et saisis à la main sur le PDF
     (même colonnes). Un vrai scan est plus dur qu'un rendu propre (bruit,
     inclinaison, compression) : ces lignes vérifient que la mesure « natif
     rastérisé » n'est pas trop optimiste.
2. **Mesure** : chaque facture est rendue à plusieurs résolutions (DPI), passée
   à LightOnOCR-3, puis lue par **le même parseur que la silver**. On compare
   chaque champ à la vérité terrain, **strictement** (un centime d'écart = faux).
3. **Précision par champ** = champs justes / factures évaluées, avec un
   **intervalle de confiance à 95 %** (Wilson) pour savoir si l'écart entre deux
   réglages est significatif.

## Commandes

```bash
python3 -m src.eval.ocr_eval build-truth --limit 30      # vérité terrain depuis data/raw
python3 -m src.eval.ocr_eval run --dpi 100 200 300       # compare 3 résolutions
python3 -m src.eval.ocr_eval silver                      # la silver vs la vérité terrain
```

Les sorties OCR sont en cache (`data/eval/ocr_cache/`) : relancer la commande
redonne le même tableau sans rappeler le modèle. Résultats :
`resultats_ocr.md` (tableau + liste des erreurs) et `resultats_ocr.csv`.

## Taille d'échantillon

Avec *n* factures, l'intervalle de confiance d'une précision de 90 % vaut
environ : n = 10 → 60–98 %, n = 30 → 74–97 %, n = 100 → 83–95 %. En dessous de
~30 factures, on ne peut pas distinguer deux réglages proches : on vise donc
au moins 30 factures pour la comparaison des résolutions.

## Résultats et analyse

Exécution du 23/11/2026, modèle `lightonocr-3-1b-test`, 20 factures
(15 PDF natifs rastérisés + 5 vrais scans vérifiés à la main), 3 résolutions.
Tableau complet et liste des erreurs : [`resultats_ocr.md`](resultats_ocr.md).

| | 60 DPI | 100 DPI | 200 DPI |
|---|---|---|---|
| précision tous champs | 96,1 % | **100 %** | **100 %** |
| `iban` | 70 % | 100 % | 100 % |
| `nb_lignes` | 85 % | 100 % | 100 % |
| `client` | 90 % | 100 % | 100 % |
| montants, dates, numéro, SIRET | 100 % | 100 % | 100 % |
| temps OCR moyen / facture | 4,4 s | 4,9 s | 5,9 s |

**Analyse**

- À partir de 100 DPI, la chaîne OCR + parseur est exacte sur tous les champs
  de l'échantillon. 200 DPI (réglage de la bronze) n'apporte rien de mesurable
  ici mais coûte ~20 % de temps en plus ; on le garde par prudence pour les
  vrais scans, plus bruités que des rendus propres.
- **Champs les plus fragiles : les longues suites de caractères sans contexte.**
  À 60 DPI, l'IBAN est faux 6 fois sur 20 (`8`→`6`, `5`→`S`, `9`→`0`) : 27
  caractères, aucun mot pour « deviner », et un seul caractère faux suffit.
  Les noms propres (« Diallo » → « Delo ») suivent. Les montants, eux, restent
  justes : gros caractères, format répétitif.
- `nb_lignes` faux à 60 DPI : l'OCR découpe mal le tableau (une ligne en trop).
  Les contrôles silver (`somme_lignes_neq_ht`, `ligne_qte_x_pu_neq_total`)
  détectent ce genre d'erreur ; de même un IBAN mal lu échoue à la clé mod 97
  (`iban_invalide`) : la silver *signale* ces factures au lieu de les accepter
  silencieusement.
- **Limites** : 20 factures, donc l'intervalle de confiance à 100 % est
  84–100 % ; il faudrait ~100 factures pour garantir > 96 %. Les factures du
  jeu viennent d'un même gabarit : un fournisseur à la mise en page différente
  serait plus difficile, pour l'OCR comme pour le parseur.

**Sur le jeu complet (100 factures, silver)** : 0 rejet, 1 facture signalée,
`V-2025-0001`, dont le scan affiche lui-même « Total TTC 99 999,99 € » pour
148,26 € HT : une anomalie volontaire du jeu, lue correctement par l'OCR et
détectée par le contrôle `ht_plus_tva_neq_ttc` sans être « corrigée ».
