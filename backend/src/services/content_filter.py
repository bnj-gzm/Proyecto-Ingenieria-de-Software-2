import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException


logger = logging.getLogger("dart.content_filter")

PROHIBITED_LANGUAGE_MESSAGE = (
    "El campo contiene lenguaje no permitido. Por favor corrige el texto antes de continuar."
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
    ProhibitedTerm("pico", allow_phrases=("pico truncado", "pico y pala", "pico de loro")),
    ProhibitedTerm("tula"),
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

_COMPACT_SEPARATORS_RE = re.compile(r"[^a-z0-9]+")
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
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return _SPACES_RE.sub(" ", value).strip()


def _compact_text(text: str) -> str:
    return _COMPACT_SEPARATORS_RE.sub("", normalize_text(text))


def _normalized_variants(text: str) -> set[str]:
    return {_normalize_text_with_one(text, "i"), _normalize_text_with_one(text, "l")}


def _matches_term(normalized: str, compact: str, term: ProhibitedTerm) -> bool:
    normalized_term = normalize_text(term.term)
    compact_term = _compact_text(term.term)
    if term.allow_phrases and any(normalize_text(phrase) in normalized for phrase in term.allow_phrases):
        return False
    if " " in normalized_term:
        return normalized_term in normalized or compact_term in compact
    if re.search(rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])", normalized):
        return True
    return compact_term in compact


def find_prohibited_terms(text: str) -> list[str]:
    if not text:
        return []
    normalized_variants = _normalized_variants(text)
    compact_variants = {_COMPACT_SEPARATORS_RE.sub("", item) for item in normalized_variants}
    found: list[str] = []
    for term in PROHIBITED_TERMS:
        if any(
            _matches_term(normalized, compact, term)
            for normalized in normalized_variants
            for compact in compact_variants
        ):
            found.append(term.term)
    return found


def contains_prohibited_language(text: str) -> bool:
    return bool(find_prohibited_terms(text))


def validate_clean_text(text: str, field_name: str, user: str = "") -> None:
    found = find_prohibited_terms(text)
    if not found:
        return
    logger.warning("CONTENT_BLOCKED field=%s user=%s", field_name, user or "anonymous")
    raise HTTPException(status_code=400, detail=PROHIBITED_LANGUAGE_MESSAGE)


def validate_clean_fields(fields: dict[str, Any], user: str = "") -> None:
    for field_name, value in fields.items():
        values = value if isinstance(value, list) else [value]
        for item in values:
            validate_clean_text("" if item is None else str(item), field_name, user)
