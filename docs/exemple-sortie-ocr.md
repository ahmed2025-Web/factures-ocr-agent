# Exemple de sortie OCR (étape 2)

Voici ce que renvoie le modèle LightOnOCR-3 sur une facture scannée. C'est le
**format brut** que l'étape 4 (silver) devra parser : du markdown, avec les
lignes de facture dans une balise `<table>` HTML.

Commande utilisée :

```bash
python3 -m src.ocr.client facture_A-2025-0003_scan.pdf
# 200 DPI, temps de traitement ~9 s pour cette page
```

## Besoin de regénérer un exemple ?

Il suffit de lancer la commande ci-dessus sur n'importe quelle facture (voir
`docs/SETUP.md` pour obtenir une clé API OCR et un PDF). On peut aussi
sauvegarder la sortie dans un fichier :

```bash
python3 -m src.ocr.client une_facture_scan.pdf > sortie.md
```

## Sortie obtenue

````markdown
# FACTURE

**Aubry**  
96, avenue de Meyer  
24403 Boyer  
SIRET : 77360260298050  
TVA intracom. : FR09773602602  

---

**Numéro de facture** : A-2025-0003  
**Date d'émission** : 29/04/2025  
**Date d'échéance** : 13/06/2025  
**Catégorie** : Conseil  
**Statut** : En retard  

---

**Facturé à** :  
Client : Dumas  
4, chemin Roger Muller  
97345 Clerc  
SIRET client : 16073375486850  

---

<table>
  <thead>
    <tr>
      <th>Désignation</th>
      <th>Qté</th>
      <th>Prix unitaire HT</th>
      <th>TVA</th>
      <th>Total HT</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>Formation DuckDB et Parquet</td>
      <td>5</td>
      <td>1 261,21 €</td>
      <td>20 %</td>
      <td>6 306,05 €</td>
    </tr>
  </tbody>
</table>

---

**Total HT** 6 306,05 €  
**TVA 20 %** 1 261,21 €  
**Total TVA** 1 261,21 €  
**Total TTC** 7 567,26 €  

---

**Mode de paiement** : Chèque  
**IBAN** : FR1578820812191361939909169  
En cas de retard de paiement, une indemnité forfaitaire de 40 € pour frais de recouvrement sera exigée (art. L441-10 du Code de commerce).
````

## Ce que l'étape 4 (silver) doit en extraire

- **une ligne de facture** (table factures) : numéro `A-2025-0003`, fournisseur
  `Aubry`, client `Dumas`, dates d'émission/échéance, statut `En retard`,
  catégorie `Conseil`, total HT / TVA / TTC ;
- **les lignes de détail** (table lignes) : désignation, quantité, prix
  unitaire HT, taux TVA, total HT — ici une seule ligne.

Points d'attention pour le parseur : montants en format français (`6 306,05 €`,
espace comme séparateur de milliers, virgule décimale), et le détail est en HTML
alors que le reste est en markdown.
