"""Étape 4 — contrôles qualité d'une facture lue.

Deux niveaux (voir docs/schema-silver.md) :
  - rejet : la facture est inexploitable → quarantaine, avec un motif ;
  - signalement : la facture est gardée mais porte des codes d'anomalie.

Aucun contrôle ne modifie les valeurs lues : on constate, on ne corrige pas.
"""

from decimal import Decimal

from . import normalize as nz
from .parser import FactureLue

TOLERANCE = Decimal("0.01")  # un centime par contrôle (arrondis)

# Sans ces champs, la facture ne peut ni être identifiée ni comptée.
CHAMPS_OBLIGATOIRES = ("numero_facture", "date_emission", "total_ht", "total_tva", "total_ttc")
CHAMPS_SECONDAIRES = ("fournisseur", "client", "statut", "date_echeance")


def motif_rejet(f: FactureLue) -> tuple[str, str] | None:
    """Retourne (motif, détails) si la facture doit être rejetée, sinon None."""
    manquants = [c for c in CHAMPS_OBLIGATOIRES if getattr(f, c) is None]
    if manquants:
        return "champ_obligatoire_manquant", "illisible(s) : " + ", ".join(manquants)
    return None


def anomalies(f: FactureLue) -> list[str]:
    """Codes d'anomalie d'une facture acceptée (liste vide = facture valide)."""
    codes = []

    if abs(f.total_ht + f.total_tva - f.total_ttc) > TOLERANCE:
        codes.append("ht_plus_tva_neq_ttc")

    if not f.lignes:
        codes.append("aucune_ligne")
    else:
        totaux = [l.total_ht for l in f.lignes]
        if None not in totaux:
            tol = TOLERANCE * len(totaux)
            if abs(sum(totaux) - f.total_ht) > tol:
                codes.append("somme_lignes_neq_ht")
            taux = [l.taux_tva for l in f.lignes]
            if None not in taux:
                tva = sum(t * r / 100 for t, r in zip(totaux, taux))
                if abs(tva - f.total_tva) > tol:
                    codes.append("tva_calculee_neq_tva")
        for l in f.lignes:
            if None in (l.quantite, l.prix_unitaire_ht, l.total_ht):
                codes.append("ligne_illisible")
                break
            if abs(l.quantite * l.prix_unitaire_ht - l.total_ht) > TOLERANCE:
                codes.append("ligne_qte_x_pu_neq_total")
                break

    if f.date_echeance and f.date_emission and f.date_echeance < f.date_emission:
        codes.append("echeance_avant_emission")

    if min(f.total_ht, f.total_tva, f.total_ttc) < 0:
        codes.append("montant_negatif")

    for siret in (f.fournisseur_siret, f.client_siret):
        if siret is not None and (len(siret) != 14 or not nz.luhn_ok(siret)):
            codes.append("siret_invalide")
            break

    if f.iban is not None and not nz.iban_ok(f.iban):
        codes.append("iban_invalide")

    if any(getattr(f, c) is None for c in CHAMPS_SECONDAIRES):
        codes.append("champ_secondaire_manquant")

    return codes
