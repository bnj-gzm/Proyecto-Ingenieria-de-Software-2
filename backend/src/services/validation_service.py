from __future__ import annotations

import re

RUT_RE = re.compile(r"^(\d{7,8})-([\dkK])$")


def normalizar_rut(rut: str) -> str:
    clean = (rut or "").strip().replace(".", "").replace(" ", "").upper()
    if "-" not in clean:
        return clean
    body, dv = clean.split("-", 1)
    return f"{body}-{dv}"


def validar_rut_chileno(rut: str) -> bool:
    normalized = normalizar_rut(rut)
    match = RUT_RE.fullmatch(normalized)
    if not match:
        return False
    body, provided_dv = match.groups()
    factor = 2
    total = 0
    for digit in reversed(body):
        total += int(digit) * factor
        factor = 2 if factor == 7 else factor + 1
    remainder = 11 - (total % 11)
    if remainder == 11:
        expected_dv = "0"
    elif remainder == 10:
        expected_dv = "K"
    else:
        expected_dv = str(remainder)
    return provided_dv.upper() == expected_dv


def normalizar_telefono_chile(telefono: str) -> str:
    raw = (telefono or "").strip()
    if not raw:
        return ""
    compact = re.sub(r"[\s().-]", "", raw)
    if compact in {"+569", "569", "9", "+56", "56"}:
        return ""
    if compact.startswith("00956"):
        compact = "+" + compact[2:]
    if compact.startswith("56"):
        compact = "+" + compact
    if compact.startswith("9") and len(compact) == 9:
        compact = "+56" + compact
    return compact


def validar_telefono_chile(telefono: str) -> bool:
    normalized = normalizar_telefono_chile(telefono)
    if not normalized:
        return True
    return re.fullmatch(r"\+569\d{8}", normalized) is not None
