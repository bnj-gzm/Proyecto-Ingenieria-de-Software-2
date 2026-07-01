import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException


logger = logging.getLogger("dart.content_filter")

PROHIBITED_LANGUAGE_MESSAGE = (
    "El contenido ingresado no es válido."
)


@dataclass(frozen=True)
class ProhibitedTerm:
    term: str
    allow_phrases: tuple[str, ...] = ()


# Lista centralizada y ampliable. Mantener los terminos sin tildes para comparar
# contra texto normalizado.
PROHIBITED_TERMS: tuple[ProhibitedTerm, ...] = (
    ProhibitedTerm("conchatumadre"),
    ProhibitedTerm("ctm"),
    ProhibitedTerm("conchasumadre"),
    ProhibitedTerm("csm"),
    ProhibitedTerm("culiao"),
    ProhibitedTerm("culiado"),
    ProhibitedTerm("ql"),
    ProhibitedTerm("qla"),
    ProhibitedTerm("maraco"),
    ProhibitedTerm("maraca"),
    ProhibitedTerm("maricon"),
    ProhibitedTerm("chucha"),
    ProhibitedTerm("chuchatumadre"),
    ProhibitedTerm("weon"),
    ProhibitedTerm("weona"),
    ProhibitedTerm("hueon"),
    ProhibitedTerm("hueona"),
    ProhibitedTerm("huevon"),
    ProhibitedTerm("huevona"),
    ProhibitedTerm("wn"),
    ProhibitedTerm("wna"),
    ProhibitedTerm("aweonao"),
    ProhibitedTerm("aweonado"),
    ProhibitedTerm("aweona"),
    ProhibitedTerm("saco de weas"),
    ProhibitedTerm("sdw"),
    ProhibitedTerm("sacowea"),
    ProhibitedTerm("saco wea"),
    ProhibitedTerm("pico", allow_phrases=("pico truncado", "pico y pala", "pico de loro")),
    ProhibitedTerm("pene"),
    ProhibitedTerm("tula"),
    ProhibitedTerm("porno"),
    ProhibitedTerm("hentai"),
    ProhibitedTerm("pornografia"),
    ProhibitedTerm("masturbacion"),
    ProhibitedTerm("zorra"),
    ProhibitedTerm("poto"),
    ProhibitedTerm("raja"),
    ProhibitedTerm("tetas"),
    ProhibitedTerm("pelotudo"),
    ProhibitedTerm("aganao"),
    ProhibitedTerm("pajero"),
    ProhibitedTerm("pajera"),
    ProhibitedTerm("sarnoso"),
    ProhibitedTerm("cuma"),
    ProhibitedTerm("flaite"),
    ProhibitedTerm("flite"),
    ProhibitedTerm("perkin"),
    ProhibitedTerm("sapo"),
    ProhibitedTerm("bastardo"),
    ProhibitedTerm("idiota"),
    ProhibitedTerm("idiot"),
    ProhibitedTerm("stupid"),
    ProhibitedTerm("asshole"),
    ProhibitedTerm("fuck"),
    ProhibitedTerm("shit"),
    ProhibitedTerm("bitch"),
    ProhibitedTerm("bastard"),
    ProhibitedTerm("dumb"),
    ProhibitedTerm("moron"),
    ProhibitedTerm("whore"),
    ProhibitedTerm("slut"),
    # Insultos adicionales chilenos/latinoamericanos
    ProhibitedTerm("conchetumadre"),
    ProhibitedTerm("chupapico"),
    ProhibitedTerm("culiaa"),
    ProhibitedTerm("hdp"),
    ProhibitedTerm("hijodeputa"),
    ProhibitedTerm("hijodeperra"),
    ProhibitedTerm("concha"),
    ProhibitedTerm("aweonada"),
    ProhibitedTerm("recula"),
    ProhibitedTerm("qliao"),
    ProhibitedTerm("poto"),
    ProhibitedTerm("mierda"),
    ProhibitedTerm("mierdas"),
    ProhibitedTerm("chupame"),
    ProhibitedTerm("marica"),
    ProhibitedTerm("maricas"),
    ProhibitedTerm("puta"),
    ProhibitedTerm("putas"),
    ProhibitedTerm("putita"),
    ProhibitedTerm("pendejo"),
    ProhibitedTerm("pendeja"),
    ProhibitedTerm("puto"),
    ProhibitedTerm("putos"),
    ProhibitedTerm("cabron"),
    ProhibitedTerm("cabrona"),
    ProhibitedTerm("imbecil"),
    ProhibitedTerm("imbeciles"),
    ProhibitedTerm("huevada"),
    ProhibitedTerm("wea"),
    ProhibitedTerm("weada"),
    # Términos sexuales explícitos
    ProhibitedTerm("porno"),
    ProhibitedTerm("sexo"),
    ProhibitedTerm("follar"),
    ProhibitedTerm("coger"),
    ProhibitedTerm("cogeme"),
    ProhibitedTerm("mamame"),
    ProhibitedTerm("culear"),
    ProhibitedTerm("culiar"),
    # "cono" es vocabulario operacional válido (p. ej. cono de seguridad).
    # No se puede distinguir de "coño" después de eliminar tildes, por lo que
    # ambos se omiten para evitar bloquear ART legítimas.
    ProhibitedTerm("pija"),
    ProhibitedTerm("verga"),
    ProhibitedTerm("vergon"),
    ProhibitedTerm("orgasmo"),
    ProhibitedTerm("eyacula"),
    ProhibitedTerm("desnuda"),
    ProhibitedTerm("nudes"),
    ProhibitedTerm("nude"),
    ProhibitedTerm("xxx"),
    # Variantes inglesas adicionales
    ProhibitedTerm("fucker"),
    ProhibitedTerm("motherfucker"),
    ProhibitedTerm("cock"),
    ProhibitedTerm("dick"),
    ProhibitedTerm("pussy"),
    ProhibitedTerm("cunt"),
    ProhibitedTerm("nigger"),
    ProhibitedTerm("faggot"),
    ProhibitedTerm("retard"),
    ProhibitedTerm("retarded"),
    ProhibitedTerm("jackass"),
    ProhibitedTerm("dumbass"),
    ProhibitedTerm("bullshit"),
    ProhibitedTerm("dipshit"),
    ProhibitedTerm("jerk"),
)

_LEET_TRANSLATION = str.maketrans(
    {
        "0": "o",
        "3": "e",
        "4": "a",
        "5": "s",
        "7": "t",
    }
)

_SPACES_RE = re.compile(r"\s+")


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_text(text: str) -> str:
    return _normalize_text_with_one(text, "i")


def _normalize_text_with_one(text: str, one_replacement: str) -> str:
    if text is None:
        return ""
    value = _strip_accents(str(text)).lower()
    value = value.translate(_LEET_TRANSLATION)
    value = value.replace("1", one_replacement)
    value = re.sub(r"[!|]", "i", value)
    value = re.sub(r"([a-z])\1+", r"\1", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return _SPACES_RE.sub(" ", value).strip()


def _normalized_variants(text: str) -> set[str]:
    return {_normalize_text_with_one(text, "i"), _normalize_text_with_one(text, "l")}


def _matches_term(normalized: str, term: ProhibitedTerm) -> bool:
    normalized_term = normalize_text(term.term)
    candidate = normalized
    for phrase in term.allow_phrases:
        candidate = candidate.replace(normalize_text(phrase), " ")
    compact_term = normalized_term.replace(" ", "")
    obfuscated_pattern = r"\s*".join(re.escape(char) for char in compact_term)
    return bool(re.search(rf"(?<![a-z0-9]){obfuscated_pattern}(?![a-z0-9])", candidate))


def find_prohibited_terms(text: str) -> list[str]:
    if not text:
        return []
    normalized_variants = _normalized_variants(text)
    found: list[str] = []
    for term in PROHIBITED_TERMS:
        if any(_matches_term(normalized, term) for normalized in normalized_variants):
            found.append(term.term)
    return found


def contains_prohibited_language(text: str) -> bool:
    return bool(find_prohibited_terms(text))


def validate_clean_text(text: str, field_name: str, user: str = "") -> None:
    found = find_prohibited_terms(text)
    if not found:
        return
    logger.warning("CONTENT_BLOCKED field=%s user=%s", field_name, user or "anonymous")
    raise HTTPException(
        status_code=400,
        detail=f"El contenido del campo '{field_name}' no es válido.",
    )


def validate_clean_fields(fields: dict[str, Any], user: str = "") -> None:
    for field_name, value in fields.items():
        values = value if isinstance(value, list) else [value]
        for item in values:
            validate_clean_text("" if item is None else str(item), field_name, user)
