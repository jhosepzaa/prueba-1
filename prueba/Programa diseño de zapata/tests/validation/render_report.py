"""Genera `docs/fase6_validacion.md` a partir de valores del motor calculados al momento.

Uso:  py -3 -m tests.validation.render_report

El informe no se escribe a mano: cada fila se calcula ahora mismo. Lo protege
`test_validation_benchmarks.py`, que falla si algún valor se sale de su tolerancia.
"""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path

from tests.validation.benchmarks import (
    ARAGON_P1_BENCHMARKS,
    ARAGON_P2_BENCHMARKS,
    COMBINED_BENCHMARKS,
    GOLDEN_BENCHMARKS,
    Benchmark,
)

DESTINO = Path(__file__).resolve().parents[2] / "docs" / "fase6_validacion.md"


def _fila(b: Benchmark) -> tuple[str, bool]:
    v = b.engine_value()
    dif = v - b.reference
    rel = abs(dif) / abs(b.reference) * 100 if b.reference else 0.0
    if b.documented_difference:
        estado = "diferencia documentada"
        ok = abs(v - b.expected_engine_value) <= b.expected_engine_tolerance
    else:
        ok = abs(dif) <= b.tolerance_abs
        estado = "reproduce" if ok else "**FUERA DE TOLERANCIA**"
    fila = (
        f"| {b.id} | {b.quantity} | {b.reference:g} | {v:.4f} | {dif:+.4f} | {rel:.3f} % | "
        f"± {b.tolerance_abs:g} {b.unit} | {estado} |"
    )
    return fila, ok


def _tabla(titulo: str, fuente: str, origen: str, bs: list[Benchmark]) -> tuple[str, int, int]:
    filas, n_ok = [], 0
    for b in bs:
        f, ok = _fila(b)
        filas.append(f)
        n_ok += ok
    cab = (
        f"## {titulo}\n\nFuente: {fuente}. Test de origen: `{origen}`.\n\n"
        "| Id | Magnitud | Referencia | Motor | Diferencia | Dif. rel. | Tolerancia | Estado |\n"
        "|---|---|---|---|---|---|---|---|\n"
    )
    notas = "".join(
        f"\n- **{b.id}** — {b.documented_difference}" for b in bs if b.documented_difference
    )
    return cab + "\n".join(filas) + ("\n" + notas if notas else "") + "\n", n_ok, len(bs)


def _seccion_bibliografica() -> tuple[str, int, int]:
    """Casos del arnés preexistente `reference_cases.py` (aislada, Aragón 3.4.1), con la
    MISMA comparación relativa y las mismas tolerancias que su test."""
    from tests.validation.reference_cases import REFERENCE_CASES
    from tests.validation.test_bibliographic_validation import run_case

    texto, n_ok, n = "", 0, 0
    for case in REFERENCE_CASES:
        filas = []
        for nombre, (libro, motor) in run_case(case).items():
            tol = case.tolerance_overrides.get(nombre, case.tolerance)
            rel = abs(motor - libro) / abs(libro) if libro else abs(motor)
            ok = rel <= tol if libro else abs(motor) < 1e-6
            n += 1
            n_ok += ok
            filas.append(
                f"| {case.id} | {nombre} | {libro:.4g} | {motor:.4f} | {rel * 100:.2f} % | "
                f"{tol * 100:.0f} % | {'reproduce' if ok else '**FUERA DE TOLERANCIA**'} |"
            )
        supuestos = "".join(f"\n- {a}" for a in case.author_assumptions)
        texto += (
            f"## Bibliografía — {case.id}\n\nFuente: {case.source}. Arnés: "
            "`tests/validation/reference_cases.py`.\n\n"
            "| Caso | Magnitud | Libro | Motor | Dif. rel. | Tolerancia | Estado |\n"
            "|---|---|---|---|---|---|---|\n" + "\n".join(filas) + "\n"
            + (f"\nSupuestos del autor declarados:{supuestos}\n" if supuestos else "")
        )
    return texto, n_ok, n


def render_markdown() -> str:
    partes, total_ok, total = [], 0, 0
    for titulo, bs in (
        ("Aragón, problema 1 — conectada, articulado con par puro", ARAGON_P1_BENCHMARKS),
        ("Aragón, problema 2 — conectada, cuerpo rígido", ARAGON_P2_BENCHMARKS),
        ("Aragón §3.5 — zapata combinada", COMBINED_BENCHMARKS),
        ("Golden cases — zapata aislada, cálculo a mano", GOLDEN_BENCHMARKS),
    ):
        texto, ok, n = _tabla(titulo, bs[0].source, bs[0].origin_test, bs)
        partes.append(texto)
        total_ok += ok
        total += n
    texto, ok, n = _seccion_bibliografica()
    partes.append(texto)
    total_ok += ok
    total += n
    cabecera = (
        "# Fase 6 — Validación del motor contra referencias externas\n\n"
        f"Generado por `tests/validation/render_report.py` el {date.today().isoformat()}. "
        "Cada valor del motor se calculó al generar este documento; no hay cifras escritas "
        "a mano.\n\n"
        f"**{total_ok} de {total} comparaciones** dentro de su criterio "
        "(tolerancia contra la referencia, o valor documentado en el caso de una diferencia "
        "explicada).\n\n"
        "Las referencias proceden de fuentes ya incorporadas al proyecto; la tolerancia es la "
        "que ya aceptaba el test de origen. En las tablas de benchmarks el criterio es la "
        "tolerancia absoluta y la diferencia relativa solo orienta; en la sección bibliográfica "
        "el criterio es la tolerancia relativa del arnés, con los ajustes que el propio arnés "
        "justifica en los supuestos del autor.\n\n"
        "Alcance: estos benchmarks validan el reparto de la conectada (P1, P2), la estática de "
        "la viga en el modelo articulado con par puro (P1), la presión de la combinada (§3.5) "
        "y las verificaciones de la zapata aislada (golden cases y §3.4.1). **No hay referencia externa numérica para la viga en cuerpo "
        "rígido**: sus diagramas en los apuntes (figuras 81 y 87–90) son imágenes. Esa parte "
        "se valida por derivación independiente en `tests/test_connected_beam_statics_phase5a.py`.\n"
    )
    return cabecera + "\n" + "\n".join(partes)


def main() -> None:
    io.open(DESTINO, "w", encoding="utf-8").write(render_markdown())
    print(f"escrito {DESTINO}")


if __name__ == "__main__":
    main()
