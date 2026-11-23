"""Étape 4 — conversion des valeurs lues (texte) en types propres.

Fonctions pures, sans dépendance : faciles à tester une par une.

Montants : on renvoie des `Decimal` (jamais de float, voir docs/schema-silver.md).
Le texte OCR et le texte d'un PDF natif n'écrivent pas les nombres pareil :
    "6 306,05 €"   (OCR, espace insécable possible)
    "6 306,05 ·"   (PDF natif : le symbole € est parfois mal décodé)
    "6306.05"      (format anglo-saxon)
Les parseurs ci-dessous acceptent toutes ces formes, et renvoient None plutôt
que de deviner quand la valeur est ambiguë ou illisible.
"""

import re
import datetime
import unicodedata
from decimal import Decimal, InvalidOperation

# Tous les espaces « exotiques » qu'on rencontre dans les nombres français.
_SPACES = "     "

_NUMBER_RE = re.compile(r"-?\d[\d" + _SPACES + r".,']*")

MOIS = {
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12,
}


def strip_accents(text: str) -> str:
    """'Échéance' → 'Echeance' (sert à comparer des libellés sans souci d'accents)."""
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def clean_text(value: str | None) -> str | None:
    """Retire le markdown (**gras**), les espaces en trop ; None si vide."""
    if value is None:
        return None
    value = re.sub(r"[*_`]+", "", value)
    value = re.sub(r"<[^>]+>", " ", value)          # balises HTML résiduelles
    value = re.sub(r"\s+", " ", value).strip(" :\t-–|")
    return value or None


def parse_amount(text: str | None) -> Decimal | None:
    """'1 261,21 €' → Decimal('1261.21'). None si illisible.

    Règle du séparateur décimal :
      - s'il y a à la fois '.' et ',' : le DERNIER des deux est le séparateur décimal ;
      - s'il n'y a qu'une ',' : décimale (usage français) ;
      - s'il n'y a qu'un '.' suivi d'exactement 3 chiffres (« 1.234 ») : milliers ;
        sinon décimale.
    """
    if text is None:
        return None
    match = _NUMBER_RE.search(text)
    if not match:
        return None
    raw = match.group(0).strip(_SPACES + ".,'")
    raw = re.sub("[" + _SPACES + "']", "", raw)
    negative = raw.startswith("-")
    raw = raw.lstrip("-")
    if not raw:
        return None

    last_dot, last_comma = raw.rfind("."), raw.rfind(",")
    if last_dot >= 0 and last_comma >= 0:
        dec = "." if last_dot > last_comma else ","
        thousands = "," if dec == "." else "."
        raw = raw.replace(thousands, "").replace(dec, ".")
    elif last_comma >= 0:
        if raw.count(",") > 1:  # « 1,234,567 » : virgules de milliers
            raw = raw.replace(",", "")
        else:
            raw = raw.replace(",", ".")
    elif last_dot >= 0:
        parts = raw.split(".")
        if len(parts) > 2 or len(parts[-1]) == 3:
            raw = raw.replace(".", "")  # « 1.234 » ou « 1.234.567 » : milliers

    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    return -value if negative else value


def parse_money(text: str | None) -> Decimal | None:
    """Comme parse_amount, mais arrondi au centime (DECIMAL(14,2))."""
    value = parse_amount(text)
    return None if value is None else value.quantize(Decimal("0.01"))


def parse_rate(text: str | None) -> Decimal | None:
    """'20 %' → Decimal('20.00') ; '5,5%' → Decimal('5.50')."""
    value = parse_amount(text)
    return None if value is None else value.quantize(Decimal("0.01"))


def parse_date(text: str | None) -> datetime.date | None:
    """Accepte 29/04/2025, 29-04-2025, 29.04.2025, 2025-04-29, 29 avril 2025."""
    if not text:
        return None
    t = strip_accents(text).lower()

    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t)
    if m:
        y, mo, d = (int(g) for g in m.groups())
        return _safe_date(y, mo, d)

    m = re.search(r"\b(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{2,4})\b", t)
    if m:
        d, mo, y = (int(g) for g in m.groups())
        if y < 100:
            y += 2000
        return _safe_date(y, mo, d)

    m = re.search(r"\b(\d{1,2})(?:er)?\s+([a-z]+)\s+(\d{4})\b", t)
    if m and m.group(2) in MOIS:
        return _safe_date(int(m.group(3)), MOIS[m.group(2)], int(m.group(1)))
    return None


def _safe_date(y: int, mo: int, d: int) -> datetime.date | None:
    try:
        return datetime.date(y, mo, d)
    except ValueError:  # 31/02, mois 13… : on ne devine pas
        return None


def digits_only(text: str | None) -> str | None:
    """'773 602 602 98050' → '77360260298050'."""
    if not text:
        return None
    d = re.sub(r"\D", "", text)
    return d or None


def compact(text: str | None) -> str | None:
    """Retire tous les espaces (IBAN, n° TVA)."""
    if not text:
        return None
    t = re.sub(r"\s+", "", text).upper()
    return t or None


def luhn_ok(number: str | None) -> bool:
    """Clé de Luhn, utilisée par les SIREN/SIRET."""
    if not number or not number.isdigit():
        return False
    total = 0
    for i, ch in enumerate(reversed(number)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def iban_ok(iban: str | None) -> bool:
    """Contrôle ISO 13616 : déplacer les 4 premiers caractères, convertir, mod 97 == 1."""
    if not iban or not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", iban):
        return False
    moved = iban[4:] + iban[:4]
    digits = "".join(str(int(c, 36)) for c in moved)
    return int(digits) % 97 == 1
