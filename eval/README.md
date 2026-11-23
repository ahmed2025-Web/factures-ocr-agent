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

*(à compléter après exécution sur le jeu réel : voir `resultats_ocr.md`)*
