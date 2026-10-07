"""Preparación del texto antes de sintetizarlo.

Un motor de voz lee mal "el 35% de los 1,200 mdp del art. 4o.".
Aquí se traduce todo eso a español hablado:

    "el treinta y cinco por ciento de los mil doscientos millones de pesos
     del artículo cuarto"

También:
  * expande abreviaturas y siglas frecuentes en la prensa mexicana,
  * normaliza fechas, cifras, porcentajes y monedas,
  * añade pausas entre párrafos,
  * corta el artículo en fragmentos que quepan en una petición al proveedor.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

from num2words import num2words

# ---------------------------------------------------------------------------
# Abreviaturas
# ---------------------------------------------------------------------------
ABBREVIATIONS: dict[str, str] = {
    r"\bDr\.": "doctor",
    r"\bDra\.": "doctora",
    r"\bLic\.": "licenciado",
    r"\bIng\.": "ingeniero",
    r"\bMtro\.": "maestro",
    r"\bMtra\.": "maestra",
    r"\bSr\.": "señor",
    r"\bSra\.": "señora",
    r"\bSrta\.": "señorita",
    r"\bGral\.": "general",
    r"\bpres\.": "presidente",
    r"\bav\.": "avenida",
    r"\bcol\.": "colonia",
    r"\bnúm\.": "número",
    r"\bno\.": "número",
    r"\bart\.": "artículo",
    r"\barts\.": "artículos",
    r"\bpág\.": "página",
    r"\bpp\.": "páginas",
    r"\betc\.": "etcétera",
    r"\bp\.\s*ej\.": "por ejemplo",
    r"\bvs\.": "contra",
    r"\bapdo\.": "apartado",
    r"\bEE\.?\s?UU\.?": "Estados Unidos",
    r"\bEUA\b": "Estados Unidos",
    r"\bUSA\b": "Estados Unidos",
    r"\bmdp\b": "millones de pesos",
    r"\bmdd\b": "millones de dólares",
    r"\bmmdp\b": "miles de millones de pesos",
    r"\bmmdd\b": "miles de millones de dólares",
    r"\bs\.?\s?XX\b": "siglo veinte",
    r"\bs\.?\s?XXI\b": "siglo veintiuno",
    r"\bd\.\s?C\.": "después de Cristo",
    r"\ba\.\s?C\.": "antes de Cristo",
}

# Siglas que conviene decir completas (política y gobierno de México)
ACRONYMS: dict[str, str] = {
    "SHCP": "Secretaría de Hacienda y Crédito Público",
    "SRE": "Secretaría de Relaciones Exteriores",
    "SEP": "Secretaría de Educación Pública",
    "SSA": "Secretaría de Salud",
    "SEDENA": "Sedena",
    "CNDH": "Comisión Nacional de los Derechos Humanos",
    "SCJN": "Suprema Corte de Justicia de la Nación",
    "INEGI": "Inegi",
    "CFE": "Comisión Federal de Electricidad",
    "IMSS": "Instituto Mexicano del Seguro Social",
    "ISSSTE": "Issste",
    "FGR": "Fiscalía General de la República",
    "PGR": "Procuraduría General de la República",
    "PIB": "producto interno bruto",
    "TLCAN": "Tratado de Libre Comercio de América del Norte",
    "TMEC": "Te-Mec",
    "UNAM": "Unam",
    "IPN": "I-Pe-Ene",
    "ONU": "Onu",
    "OEA": "O-E-A",
    "OTAN": "Otan",
    "FMI": "Fondo Monetario Internacional",
    "BID": "Banco Interamericano de Desarrollo",
    "INE": "I-Ene-E",
    "TEPJF": "Tribunal Electoral del Poder Judicial de la Federación",
    "CDMX": "Ciudad de México",
    "AMLO": "A-M-L-O",
    "PRI": "P-R-I",
    "PAN": "P-A-N",
    "PRD": "P-R-D",
    "PT": "P-T",
    "PVEM": "Partido Verde",
    "MC": "Movimiento Ciudadano",
}

MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

VOWELS = set("AEIOUÁÉÍÓÚ")


# ---------------------------------------------------------------------------
# Números
# ---------------------------------------------------------------------------
def _spell_number(value: str) -> str:
    """Convierte '1,234' o '3.5' en palabras."""
    cleaned = value.replace(",", "")
    try:
        if "." in cleaned:
            entero, decimal = cleaned.split(".", 1)
            palabras = num2words(int(entero), lang="es")
            decimales = " ".join(num2words(int(d), lang="es") for d in decimal)
            return f"{palabras} punto {decimales}"
        return num2words(int(cleaned), lang="es")
    except (ValueError, OverflowError, IndexError):
        return value


def _replace_dates(text: str) -> str:
    def repl(match: re.Match) -> str:
        day, month, year = match.groups()
        try:
            month_name = MESES[int(month) - 1]
        except (ValueError, IndexError):
            return match.group(0)
        year_text = _spell_number(year) if len(year) == 4 else year
        return f"{_spell_number(day)} de {month_name} de {year_text}"

    return re.sub(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b", repl, text)


def _replace_money(text: str) -> str:
    text = re.sub(
        r"\$\s?([\d,]+(?:\.\d+)?)\s*(mdp|mdd|millones|mil millones)?",
        lambda m: f"{_spell_number(m.group(1))} {m.group(2) or 'pesos'}".replace(
            "mdp", "millones de pesos"
        ).replace("mdd", "millones de dólares"),
        text,
    )
    text = re.sub(r"([\d,]+(?:\.\d+)?)\s?(?:USD|US\$)", lambda m: f"{_spell_number(m.group(1))} dólares", text)
    return text


def _replace_percentages(text: str) -> str:
    return re.sub(
        r"([\d,]+(?:\.\d+)?)\s?%",
        lambda m: f"{_spell_number(m.group(1))} por ciento",
        text,
    )


def _replace_plain_numbers(text: str) -> str:
    """Números sueltos. Se ignoran los pegados a letras (p. ej. 'Covid19')."""
    def repl(match: re.Match) -> str:
        raw = match.group(0)
        digits = raw.replace(",", "").replace(".", "")
        if len(digits) > 12:
            return raw
        return _spell_number(raw)

    return re.sub(r"(?<![\w/.-])\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\w-])|(?<![\w/.-])\d+(?:\.\d+)?(?![\w%-])", repl, text)


def _expand_acronyms(text: str) -> str:
    def repl(match: re.Match) -> str:
        token = match.group(0)
        if token in ACRONYMS:
            return ACRONYMS[token]
        # Sin vocales -> se deletrea (PJF, PGJ...)
        if not (set(token) & VOWELS):
            return "-".join(token)
        return token

    return re.sub(r"\b[A-ZÁÉÍÓÚÑ]{2,6}\b", repl, text)


def _expand_abbreviations(text: str) -> str:
    for pattern, replacement in ABBREVIATIONS.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE if pattern.islower() else 0)
    return text


def _tidy(text: str) -> str:
    text = text.replace("—", ", ").replace("–", ", ").replace("«", '"').replace("»", '"')
    text = re.sub(r"\.{3,}", "…", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def normalize_for_speech(text: str) -> str:
    """Pasa un párrafo por toda la cadena de limpieza."""
    text = _tidy(text)
    text = _expand_abbreviations(text)
    text = _expand_acronyms(text)
    text = _replace_dates(text)
    text = _replace_money(text)
    text = _replace_percentages(text)
    text = _replace_plain_numbers(text)
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Introducción hablada
# ---------------------------------------------------------------------------
def build_intro(title: str, author: str | None, outlet: str | None,
                published_at: dt.datetime | None) -> str:
    partes = [normalize_for_speech(title).rstrip(".") + "."]
    if author:
        partes.append(f"Por {author}.")
    if outlet:
        partes.append(f"{outlet}.")
    if published_at:
        fecha = published_at
        partes.append(
            f"{num2words(fecha.day, lang='es')} de {MESES[fecha.month - 1]} "
            f"de {num2words(fecha.year, lang='es')}."
        )
    return " ".join(partes)


# ---------------------------------------------------------------------------
# Troceado
# ---------------------------------------------------------------------------
@dataclass
class Chunk:
    """Un fragmento que se sintetiza en una sola petición."""

    text: str
    #: índices de los párrafos del artículo que contiene (-1 = introducción)
    paragraph_indices: list[int] = field(default_factory=list)


def _split_long_paragraph(text: str, limit: int) -> list[str]:
    """Parte un párrafo enorme por frases, sin pasarse del límite."""
    sentences = re.split(r"(?<=[.!?…])\s+", text)
    pieces, current = [], ""
    for sentence in sentences:
        if len(current) + len(sentence) + 1 <= limit:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                pieces.append(current)
            if len(sentence) <= limit:
                current = sentence
            else:  # frase kilométrica: corte duro
                for i in range(0, len(sentence), limit):
                    pieces.append(sentence[i:i + limit])
                current = ""
    if current:
        pieces.append(current)
    return pieces


def build_chunks(
    paragraphs: list[str],
    *,
    intro: str | None = None,
    max_chars: int = 3500,
) -> list[Chunk]:
    """Agrupa párrafos en fragmentos de como mucho `max_chars` caracteres.

    Se respetan los límites de párrafo para que la sincronía texto↔audio
    sea exacta: cada fragmento sabe qué párrafos contiene.
    """
    chunks: list[Chunk] = []
    if intro:
        chunks.append(Chunk(text=intro, paragraph_indices=[-1]))

    current_text = ""
    current_idx: list[int] = []

    for index, raw in enumerate(paragraphs):
        spoken = normalize_for_speech(raw)
        if not spoken:
            continue
        if not spoken.endswith((".", "!", "?", "…", ":", '"')):
            spoken += "."

        if len(spoken) > max_chars:
            if current_text:
                chunks.append(Chunk(text=current_text, paragraph_indices=current_idx))
                current_text, current_idx = "", []
            for piece in _split_long_paragraph(spoken, max_chars):
                chunks.append(Chunk(text=piece, paragraph_indices=[index]))
            continue

        candidate = f"{current_text}\n\n{spoken}" if current_text else spoken
        if len(candidate) <= max_chars:
            current_text = candidate
            current_idx.append(index)
        else:
            chunks.append(Chunk(text=current_text, paragraph_indices=current_idx))
            current_text, current_idx = spoken, [index]

    if current_text:
        chunks.append(Chunk(text=current_text, paragraph_indices=current_idx))

    return chunks
