"""Auditoría normativa: ninguna cita del motor puede estar inventada (2026-09-19).

QUÉ COMPRUEBA — Y QUÉ NO
========================
`CLAUDE.md` §1: «No inventar artículos, coeficientes, ecuaciones, factores ni criterios
normativos.» Este archivo lo comprueba de forma MECÁNICA: recorre todas las referencias
normativas que el motor emite —el `code_reference` de cada entrada de traza de las cuatro
tipologías, más el registro de limitaciones—, extrae cada designación citada (artículo,
sección o ecuación) y la busca en el texto extraído de la fuente correspondiente de
`docs/normativa/texto/`.

**Lo que atrapa:** una designación que no existe, un número mal tecleado, una sección de
una norma atribuida a otra, o una cita que sobrevive a un cambio de edición de la fuente.

**Lo que NO atrapa:** que el artículo citado diga lo que el motor afirma. Eso es lectura, no
búsqueda, y se contrasta artículo por artículo en `docs/normativa/contraste_e060_motor.md`
(A1–A8, B1–B11) y en los documentos de fase. Un test verde aquí significa «la cita existe»,
nunca «la cita es correcta».

Resultado de la primera pasada: **65 designaciones distintas, todas localizadas**.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import pytest

from engine.results.limitations import LIMITATION_REGISTRY
from tests.freeze.cases import BEAM_CASES, CASES, COMBINED_CASES, CONNECTED_CASES
from tests.freeze.test_freeze_connected import _solve as _solve_conectada
from tests.freeze.test_freeze_isolated import _evaluate, _solve_beam, _solve_combined

TEXTOS = Path(__file__).resolve().parents[1] / "docs" / "normativa" / "texto"

# Solo las fuentes admitidas (CLAUDE.md §8). `e060 actualizada.txt` NO está aquí a
# propósito: contiene E.030 (2025), no E.060.
FUENTES = {
    "E.060": "e.060-concreto-armado-sencico.txt",
    "E.050": "Norma E.050 Suelos y cimentaciones (1).txt",
    "E.030": "E.030 Diseño sismorresistente (2026).txt",
    "E.020": "Norma E.020 Cargas.txt",
}

_SECCION = re.compile(r"§\s*(\d+(?:\.\d+)*)")
_ARTICULO = re.compile(r"art\.?\s*(\d+(?:\.\d+)*)", re.IGNORECASE)
_ECUACION = re.compile(r"\((?:ec\.?\s*)?(\d{1,2}-\d{1,2})\)|ec\.?\s*(\d{1,2}-\d{1,2})")


def _fuente(norma: str) -> str:
    ruta = TEXTOS / FUENTES[norma]
    if not ruta.exists():
        pytest.skip(f"Falta el texto extraído de {norma}: {ruta}")
    return ruta.read_text(encoding="utf-8", errors="replace")


def _referencias() -> set[tuple[str | None, str]]:
    """(code_name, code_reference) de todo lo que el motor publica."""
    salida: set[tuple[str | None, str]] = set()

    def recoger(entradas) -> None:
        for e in entradas:
            salida.add((getattr(e, "code_name", None), e.code_reference))

    for c in CASES:
        recoger(_evaluate(c).trace.entries)
    for c in COMBINED_CASES:
        recoger(_solve_combined(c).trace.entries)
    for c in CONNECTED_CASES:
        if not c.expects_rejection:
            recoger(_solve_conectada(c).trace.entries)
    for c in BEAM_CASES:
        recoger(_solve_beam(c)[1].entries)
    for limitacion in LIMITATION_REGISTRY:
        salida.add((None, limitacion.code_reference))
    return salida


def _citas_por_norma() -> dict[str, set[tuple[str, str]]]:
    """{norma: {(tipo, designación)}}.

    Una referencia puede mezclar normas —«E.050 art. 17.1; E.020 art. 20.1»—, de modo que
    se trocea por la mención de la norma. Cuando el texto no la nombra, rige el `code_name`
    de la entrada: es lo que el informe presenta como norma de esa verificación."""
    citas: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for code_name, ref in _referencias():
        norma = code_name if code_name in FUENTES else None
        for tramo in re.split(r"(E\.0[2356]0)", ref):
            if tramo in FUENTES:
                norma = tramo
                continue
            if norma is None:
                continue
            for m in _SECCION.finditer(tramo):
                citas[norma].add(("§", m.group(1)))
            for m in _ARTICULO.finditer(tramo):
                citas[norma].add(("art.", m.group(1)))
            for m in _ECUACION.finditer(tramo):
                citas[norma].add(("ec.", m.group(1) or m.group(2)))
    return citas


def _existe(texto: str, tipo: str, designacion: str) -> bool:
    if tipo == "ec.":
        # E.060 numera sus ecuaciones entre paréntesis en el cuerpo: «(11-45)».
        return f"({designacion})" in texto
    # Secciones y artículos encabezan su párrafo.
    if re.search(rf"(?m)^\s*{re.escape(designacion)}[\s.]", texto):
        return True
    if re.search(rf"(?m)^\s*{re.escape(designacion)}\.", texto):
        return True
    raiz = designacion.split(".")[0]
    return bool(re.search(rf"(?m)^\s*Art[íi]culo\s+{re.escape(raiz)}", texto))


@pytest.fixture(scope="module")
def citas() -> dict[str, set[tuple[str, str]]]:
    return _citas_por_norma()


@pytest.mark.parametrize("norma", sorted(FUENTES))
def test_toda_designacion_citada_existe_en_la_fuente(norma, citas):
    texto = _fuente(norma)
    ausentes = sorted(
        (tipo, num) for tipo, num in citas.get(norma, set()) if not _existe(texto, tipo, num)
    )
    assert not ausentes, (
        f"{norma}: el motor cita designaciones que no aparecen en "
        f"docs/normativa/texto/{FUENTES[norma]}: {ausentes}. "
        f"O la cita está mal, o la fuente cambió de edición. No se inventa ninguna."
    )


def test_se_citan_las_cuatro_normas_y_ninguna_mas(citas):
    """Si apareciera una quinta norma, sería una fuente no admitida (CLAUDE.md §8)."""
    assert set(citas) <= set(FUENTES), sorted(set(citas) - set(FUENTES))
    assert set(citas) == set(FUENTES), (
        f"Dejó de citarse alguna norma: {sorted(set(FUENTES) - set(citas))}"
    )


def test_la_auditoria_cubre_un_volumen_razonable_de_citas(citas):
    """Una regresión que vaciara `code_reference` dejaría este archivo verde sin haber
    comprobado nada. Se fija el orden de magnitud medido el 2026-09-19."""
    total = sum(len(v) for v in citas.values())
    assert total >= 60, f"Solo se auditaron {total} designaciones; se esperaban ~65"


def test_e060_actualizada_no_se_usa_como_fuente():
    """`e060 actualizada.pdf` contiene E.030 (2025), no E.060 (CLAUDE.md §8). El archivo
    puede seguir en el repositorio, pero no como fuente de ninguna cita."""
    assert "e060 actualizada.txt" not in FUENTES.values()
