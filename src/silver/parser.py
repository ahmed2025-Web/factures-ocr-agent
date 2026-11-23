"""Étape 4 — parseur : texte brut d'une facture (bronze) → champs structurés.

Le même parseur traite les deux formes de texte de la bronze :
  - sortie OCR (LightOnOCR-3) : markdown, libellés en **gras**, lignes de détail
    dans un <table> HTML (voir docs/exemple-sortie-ocr.md) ;
  - texte natif (pypdf) : texte brut, une ligne par ligne visuelle, le tableau
    aplati en « désignation qté prix tva total », symbole € parfois mal décodé.

Pour être robuste à ces variations, on ne dépend pas de la mise en page :
  1. on « aplatit » le texte (sans markdown, sans accents, en minuscules) pour
     chercher les libellés (« numéro de facture », « date d'échéance »…) ;
  2. on lit la valeur qui suit le libellé sur la même ligne ;
  3. on convertit avec les fonctions de normalize.py, qui renvoient None
     plutôt que de deviner.

Le parseur ne décide PAS si la facture est bonne : il lit. Les contrôles sont
dans checks.py.
"""

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

from . import normalize as nz


@dataclass
class Ligne:
    designation: str | None
    quantite: object  # Decimal | None
    prix_unitaire_ht: object
    taux_tva: object
    total_ht: object


@dataclass
class FactureLue:
    numero_facture: str | None = None
    fournisseur: str | None = None
    fournisseur_siret: str | None = None
    fournisseur_tva: str | None = None
    client: str | None = None
    client_siret: str | None = None
    date_emission: object = None
    date_echeance: object = None
    categorie: str | None = None
    statut: str | None = None
    mode_paiement: str | None = None
    iban: str | None = None
    total_ht: object = None
    total_tva: object = None
    total_ttc: object = None
    lignes: list = field(default_factory=list)


# --- Libellés -------------------------------------------------------------------
# Chaque champ peut être écrit de plusieurs façons. Les motifs portent sur le
# texte sans accents et en minuscules ; la valeur est capturée sur la même ligne.
_SEP = r"\s*[:：]?\s*"
LABELS = {
    "numero_facture": [r"num[eé]ro de facture", r"facture n[°o]", r"n[°o] de facture", r"invoice (?:no|number)"],
    "date_emission": [r"date d'?\s?emission", r"date de facture", r"date facture", r"emise le", r"date"],
    "date_echeance": [r"date d'?\s?echeance", r"echeance", r"a payer avant le"],
    "categorie": [r"categorie"],
    "statut": [r"statut"],
    "mode_paiement": [r"mode de (?:paiement|reglement)", r"moyen de paiement"],
    "iban": [r"iban"],
    "client": [r"client"],
    "client_siret": [r"siret client", r"siret du client"],
    "fournisseur_siret": [r"siret"],
    "fournisseur_tva": [r"tva intra(?:com(?:munautaire)?)?\.?", r"n[°o] tva"],
}


def _flatten(line: str) -> str:
    """Ligne comparable : sans markdown, sans accents, en minuscules, espaces simples."""
    line = re.sub(r"[*_`#>|]+", " ", line)
    line = re.sub(r"<[^>]+>", " ", line)
    line = nz.strip_accents(line).lower().replace("’", "'")
    return re.sub(r"\s+", " ", line).strip()


def _lines(text: str) -> list[tuple[str, str]]:
    """Liste de (ligne aplatie, ligne d'origine nettoyée), sans les lignes vides."""
    out = []
    for raw in text.splitlines():
        flat = _flatten(raw)
        if flat:
            out.append((flat, nz.clean_text(raw) or ""))
    return out


def _value_after(lines, patterns, exclude=()) -> str | None:
    """Première valeur trouvée après un des libellés (motifs essayés dans l'ordre).

    On renvoie la valeur prise dans la ligne D'ORIGINE (avec accents et
    majuscules), à la position où se termine le libellé dans la ligne aplatie.
    """
    for pattern in patterns:
        rx = re.compile(r"^(?:" + pattern + r")" + _SEP + r"(.*)$")
        for flat, orig in lines:
            if any(flat.startswith(e) for e in exclude):
                continue
            m = rx.match(flat)
            if not m or not m.group(1).strip():
                continue
            value = _same_span(orig, len(flat) - len(m.group(1)))
            if value:
                return value
    return None


def _same_span(orig: str, flat_offset: int) -> str | None:
    """Retrouve la valeur dans la ligne d'origine.

    La ligne aplatie a perdu accents/markdown mais garde (à peu près) le même
    découpage en mots : on saute autant de mots que le libellé en contenait.
    """
    flat = _flatten(orig)
    n_words = len(flat[:flat_offset].split())
    words = nz.clean_text(orig).split()
    return nz.clean_text(" ".join(words[n_words:]))


# --- En-tête --------------------------------------------------------------------
def _parse_header(lines, f: FactureLue) -> None:
    get = lambda key, exclude=(): _value_after(lines, LABELS[key], exclude)

    numero = get("numero_facture")
    if numero:
        m = re.search(r"[A-Z0-9][A-Z0-9\-_/.]*\d", numero.upper())
        f.numero_facture = m.group(0) if m else None

    f.date_emission = nz.parse_date(get("date_emission", exclude=("date d'echeance", "date d echeance")))
    f.date_echeance = nz.parse_date(get("date_echeance"))
    f.categorie = get("categorie")
    f.statut = get("statut")
    f.mode_paiement = get("mode_paiement")
    f.iban = nz.compact(get("iban"))
    f.client_siret = nz.digits_only(get("client_siret"))
    f.fournisseur_siret = nz.digits_only(get("fournisseur_siret", exclude=("siret client", "siret du client")))
    tva = get("fournisseur_tva")
    f.fournisseur_tva = nz.compact(tva.split(":")[-1]) if tva else None

    client = get("client", exclude=("client siret",))
    f.client = None if client is None or client.lower().startswith("siret") else client
    f.fournisseur = _fournisseur(lines)


def _fournisseur(lines) -> str | None:
    """Le fournisseur est le premier bloc de texte sous le titre « FACTURE ».

    On prend la première ligne qui n'est ni le titre, ni un libellé connu, ni une
    adresse (commence par un chiffre).
    """
    started = False
    for flat, orig in lines:
        if not started:
            if re.fullmatch(r"(facture|invoice)( .*)?", flat) and len(flat) < 40:
                started = True
            continue
        if re.fullmatch(r"[-=_ ]+", flat) or flat[0].isdigit() or ":" in orig:
            continue
        return orig
    return None


# --- Totaux ---------------------------------------------------------------------
def _parse_totals(lines, f: FactureLue) -> None:
    """Lit « Total HT », « Total TVA » et « Total TTC » (les derniers rencontrés).

    On prend la dernière occurrence : l'en-tête du tableau contient aussi
    « Total HT » (titre de colonne), sans montant.
    """
    for flat, orig in lines:
        if re.match(r"^(montant |total )?t\.?t\.?c\.?\b|^(total|net) a payer", flat) or flat.startswith("total ttc"):
            f.total_ttc = _keep(_last_money(orig), f.total_ttc)
        elif flat.startswith("total tva") or flat.startswith("montant tva"):
            f.total_tva = _keep(_last_money(orig), f.total_tva)
        elif flat.startswith("total ht") or flat.startswith("montant ht"):
            f.total_ht = _keep(_last_money(orig), f.total_ht)
        elif re.match(r"^tva \d", flat) and f.total_tva is None:
            # Une ligne « TVA 20 % 1 261,21 € » (une seule ligne de TVA)
            f.total_tva = _last_money(orig, skip_percent=True)


def _keep(new, old):
    """Garde la nouvelle valeur si elle existe (attention : Decimal('0.00') est « faux »)."""
    return new if new is not None else old


_MONEY_RE = re.compile(r"-?\d{1,3}(?:[    .]\d{3})*(?:[.,]\d{1,2})|-?\d+(?:[.,]\d{1,2})?")


def _last_money(text: str, skip_percent: bool = False):
    """Dernier montant d'une ligne (ex. « Total HT 6 306,05 € » → 6306.05)."""
    if skip_percent:
        text = re.sub(r"\d+(?:[.,]\d+)?\s*%", " ", text)
    found = _MONEY_RE.findall(text)
    return nz.parse_money(found[-1]) if found else None


# --- Lignes de détail -------------------------------------------------------------
class _TableParser(HTMLParser):
    """Récupère les lignes (<tr>) d'un tableau HTML sous forme de listes de cellules."""

    def __init__(self):
        super().__init__()
        self.rows, self._row, self._cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self._row.append(nz.clean_text("".join(self._cell)) or "")
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


# Colonnes attendues, reconnues par leur titre (texte aplati).
_COLUMNS = {
    "designation": r"designation|description|libelle|article|prestation",
    "quantite": r"qte|quantite|qty",
    "prix_unitaire_ht": r"prix|p\.?u",
    "taux_tva": r"tva|taux",
    "total_ht": r"total|montant",
}


def _map_columns(header: list[str]) -> dict:
    mapping = {}
    for i, title in enumerate(header):
        flat = _flatten(title)
        for key, rx in _COLUMNS.items():
            if key not in mapping and re.search(rx, flat):
                mapping[key] = i
                break
    return mapping


def _rows_to_lignes(rows: list[list[str]]) -> list[Ligne]:
    if not rows:
        return []
    mapping = _map_columns(rows[0])
    if len(mapping) < 4:  # pas d'en-tête reconnu : ordre par défaut
        mapping = dict(zip(_COLUMNS, range(5)))
        body = rows
    else:
        body = rows[1:]
    lignes = []
    for cells in body:
        cell = lambda k: cells[mapping[k]] if k in mapping and mapping[k] < len(cells) else None
        if not any(cells) or _flatten(cell("designation") or "").startswith("total"):
            continue
        lignes.append(Ligne(
            designation=nz.clean_text(cell("designation")),
            quantite=nz.parse_amount(cell("quantite")),
            prix_unitaire_ht=nz.parse_money(cell("prix_unitaire_ht")),
            taux_tva=nz.parse_rate(cell("taux_tva")),
            total_ht=nz.parse_money(cell("total_ht")),
        ))
    return lignes


def _html_tables(text: str) -> list[Ligne]:
    lignes = []
    for table in re.findall(r"<table.*?</table>", text, flags=re.S | re.I):
        p = _TableParser()
        p.feed(table)
        lignes += _rows_to_lignes(p.rows)
    return lignes


def _markdown_tables(text: str) -> list[Ligne]:
    """Tableaux markdown « | a | b | » (au cas où l'OCR n'utilise pas le HTML)."""
    rows = []
    for raw in text.splitlines():
        s = raw.strip()
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue  # ligne de séparation |---|---|
            rows.append(cells)
    return _rows_to_lignes(rows)


# Une ligne de tableau aplatie par pypdf :
#   « Formation DuckDB et Parquet 5 1 261,21 € 20 % 6 306,05 € »
# Le symbole monétaire est optionnel (et parfois mal décodé, d'où [^\d\s]?).
_AMT = r"\d{1,3}(?:[   ]\d{3})*(?:[.,]\d{2})"
_PLAIN_ROW = re.compile(
    r"^(?P<designation>.+?)\s+(?P<quantite>\d+(?:[.,]\d+)?)\s+"
    r"(?P<pu>" + _AMT + r")\s*[^\d\s]?\s+"
    r"(?P<tva>\d+(?:[.,]\d+)?)\s*%\s+"
    r"(?P<total>" + _AMT + r")\s*[^\d\s]?\s*$"
)


def _plain_rows(text: str) -> list[Ligne]:
    lignes = []
    for raw in text.splitlines():
        line = nz.clean_text(raw) or ""
        m = _PLAIN_ROW.match(line)
        if not m or _flatten(m.group("designation")).startswith(("total", "tva")):
            continue
        lignes.append(Ligne(
            designation=m.group("designation"),
            quantite=nz.parse_amount(m.group("quantite")),
            prix_unitaire_ht=nz.parse_money(m.group("pu")),
            taux_tva=nz.parse_rate(m.group("tva")),
            total_ht=nz.parse_money(m.group("total")),
        ))
    return lignes


def _parse_lignes(text: str) -> list[Ligne]:
    """Essaie HTML, puis markdown, puis texte brut : le premier qui trouve gagne."""
    return _html_tables(text) or _markdown_tables(text) or _plain_rows(text)


# --- Point d'entrée -------------------------------------------------------------
def parse_invoice(text: str) -> FactureLue:
    """Lit une facture à partir de son texte brut (OCR ou natif)."""
    f = FactureLue()
    if not text or not text.strip():
        return f
    # Le tableau HTML est lu à part ; on l'enlève pour la lecture de l'en-tête.
    header_text = re.sub(r"<table.*?</table>", "\n", text, flags=re.S | re.I)
    lines = _lines(header_text)
    _parse_header(lines, f)
    _parse_totals(lines, f)
    f.lignes = _parse_lignes(text)
    return f
