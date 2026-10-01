"""Fase 6 — el motor contra las referencias externas del registro de benchmarks.

Además de comprobar cada valor, estos tests protegen el propio informe de validación
(`docs/fase6_validacion.md`): si un valor del motor se sale de la tolerancia, el informe
generado no puede afirmar que reproduce la referencia, porque este test falla antes.
"""

from __future__ import annotations

import pytest

from tests.validation.benchmarks import ALL_BENCHMARKS, Benchmark
from tests.validation.render_report import render_markdown

IDS = [b.id for b in ALL_BENCHMARKS]


@pytest.mark.parametrize("bench", ALL_BENCHMARKS, ids=IDS)
def test_benchmark(bench: Benchmark):
    valor = bench.engine_value()
    if bench.documented_difference:
        # La diferencia documentada tiene que SEGUIR existiendo tal como se documentó: si
        # desaparece, alguien cambió la convención y hay que revisar la documentación.
        assert abs(valor - bench.expected_engine_value) <= bench.expected_engine_tolerance, (
            f"{bench.id}: el motor da {valor:.4f} y se documentó {bench.expected_engine_value}"
        )
        assert abs(valor - bench.reference) > bench.tolerance_abs, (
            f"{bench.id}: la diferencia documentada ya no existe; actualice el registro"
        )
    else:
        assert abs(valor - bench.reference) <= bench.tolerance_abs, (
            f"{bench.id} ({bench.source}): motor {valor:.4f} {bench.unit} frente a "
            f"referencia {bench.reference} ± {bench.tolerance_abs}"
        )


def test_los_ids_son_unicos_y_cada_uno_cita_su_origen():
    assert len(IDS) == len(set(IDS))
    for b in ALL_BENCHMARKS:
        assert b.source and b.origin_test.startswith("tests/")
        if b.documented_difference:
            assert b.expected_engine_value is not None


def test_el_informe_refleja_el_estado_real():
    md = render_markdown()
    assert "| P1-Mu-cara |" in md and "diferencia documentada" in md
    for b in ALL_BENCHMARKS:
        assert f"| {b.id} |" in md
