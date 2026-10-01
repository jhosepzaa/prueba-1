"""CONGELAMIENTO NUMÉRICO DE LA ZAPATA AISLADA -- Fase 1A.

Requisito que protege este archivo:

    EL CASO ACTUAL DE ZAPATA AISLADA NO DEBE CAMBIAR DE RESULTADO COMO
    CONSECUENCIA DE LA GENERALIZACIÓN.

Los 446 tests existentes verifican propiedades, umbrales y valores calculados a
mano. Ninguno impide que una generalización desplace un valor intermedio -- el
reparto entre franjas, la barra seleccionada, el h que gana -- sin violar
ninguna aserción. Este archivo cierra ese hueco fijando la salida completa.

REGENERAR LA LÍNEA BASE
-----------------------
Solo cuando un cambio de resultado sea DELIBERADO y esté justificado:

    FREEZE_REGEN=1 py -m pytest tests/freeze -q

El diff de `baseline.json` en el control de versiones es entonces la evidencia
de qué cambió exactamente. Regenerar sin revisar ese diff anula el propósito del
archivo.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from engine.codes.peru.e060_concrete import E060ConcreteCode
from engine.foundation.depth_solver import evaluate_candidate, solve_depth
from engine.beam.beam_trace import build_beam_trace
from engine.beam.connecting_beam import SeismicContext, design_connecting_beam
from engine.foundation.combined_solver import solve_combined_footing
from engine.soil.contact_pressure import KernCheckModel
from tests.freeze.cases import (
    BEAM_CASES,
    CASES,
    COMBINED_CASES,
    SWEEP_CASES,
    BeamFreezeCase,
    CombinedFreezeCase,
    FreezeCase,
)
from tests.freeze.snapshot import diff_snapshots, dumps, snapshot_candidate

BASELINE = Path(__file__).parent / "baseline.json"
REGEN = os.environ.get("FREEZE_REGEN") == "1"

CODE = E060ConcreteCode()
CONTACT_MODEL = KernCheckModel()


def _evaluate(case: FreezeCase):
    return evaluate_candidate(
        B_m=case.B_m, L_m=case.L_m, h_m=case.h_m,
        column=case.column, soil=case.soil,
        concrete=case.concrete, steel=case.steel,
        load_case_set=case.load_case_set, code=CODE,
        contact_model=CONTACT_MODEL, depth_params=case.depth_params,
        placement=case.placement,
        **case.extra,
    )


def _solve(case: FreezeCase):
    return solve_depth(
        B_m=case.B_m, L_m=case.L_m,
        column=case.column, soil=case.soil,
        concrete=case.concrete, steel=case.steel,
        load_case_set=case.load_case_set, code=CODE,
        contact_model=CONTACT_MODEL, depth_params=case.depth_params,
        placement=case.placement,
        **case.extra,
    )


def _solve_combined(case: CombinedFreezeCase):
    return solve_combined_footing(
        case.layout, case.h_m, soil=case.soil,
        concrete=case.concrete, steel=case.steel, code=CODE,
        contact_model=CONTACT_MODEL, top_cover=case.top_cover,
    )


def _solve_beam(case: BeamFreezeCase):
    """La viga produce resultado y traza por separado, de modo que se devuelven ambos."""
    resultado = design_connecting_beam(
        b_m=case.b_m, h_m=case.h_m, d_m=case.d_m, clear_span_m=case.clear_span_m,
        Mu_negative_kNm=case.Mu_negative_kNm, Mu_positive_kNm=case.Mu_positive_kNm,
        Vu_kN=case.Vu_kN, fc_MPa=case.fc_MPa, fy_MPa=case.fy_MPa,
        longitudinal_db_mm=case.longitudinal_db_mm, sum_Pu_kN=case.sum_Pu_kN,
        seismic=SeismicContext(
            soil_profile=case.soil_profile, seismic_zone=case.seismic_zone,
            qadm_kPa=case.qadm_kPa,
            part_of_lateral_force_system=case.part_of_lateral_force_system,
            lateral_system=case.lateral_system,
        ),
    )
    return resultado, build_beam_trace(resultado)


def _build_all() -> dict[str, dict]:
    actual: dict[str, dict] = {}
    for case in BEAM_CASES:
        resultado, trace = _solve_beam(case)
        actual[case.name] = snapshot_candidate(resultado, trace=trace)
    for case in COMBINED_CASES:
        actual[case.name] = snapshot_candidate(_solve_combined(case))
    for case in CASES:
        actual[case.name] = snapshot_candidate(_evaluate(case))
    for case in SWEEP_CASES:
        result = _solve(case)
        chosen = result.accepted or result.last_evaluated
        snap = snapshot_candidate(chosen) if chosen is not None else {"numeros": {}, "estados": {},
                                                                     "referencias": {}, "trazas_en_fallo": []}
        snap["barrido"] = _sweep_summary(result)
        actual[case.name] = snap
    return actual


def _sweep_summary(result) -> dict:
    """Resumen del barrido: qué h se eligió y qué h se descartaron, con su estado.
    Es la decisión del solver, distinta de los números de un candidato aislado."""
    return {
        "h_evaluados": [round(t.h_m, 6) for t in result.trials],
        "estados": [t.overall_status.value for t in result.trials],
        "n_descartes": [len(t.discard_reasons) for t in result.trials],
        "hubo_aceptado": result.accepted is not None,
        "h_aceptado": round(result.accepted.h_m, 6) if result.accepted else None,
        "podado_temprano": result.pruned_early,
    }


@pytest.fixture(scope="module")
def actual() -> dict[str, dict]:
    return _build_all()


@pytest.fixture(scope="module")
def esperado() -> dict[str, dict]:
    if not BASELINE.exists():
        pytest.skip("No existe baseline.json; ejecutar con FREEZE_REGEN=1 para crearla.")
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def test_regenerar_linea_base(actual):
    """No es una verificación: es el mecanismo de regeneración, activado por
    variable de entorno. Con FREEZE_REGEN sin definir, no hace nada."""
    if not REGEN:
        pytest.skip("Regeneración desactivada (definir FREEZE_REGEN=1 para regenerar).")
    BASELINE.write_text(dumps(actual), encoding="utf-8")


def test_la_linea_base_cubre_todos_los_casos(actual, esperado):
    faltan = sorted(set(actual) - set(esperado))
    sobran = sorted(set(esperado) - set(actual))
    assert not faltan, f"Casos sin línea base: {faltan}. Regenerar con FREEZE_REGEN=1."
    assert not sobran, f"Línea base con casos que ya no existen: {sobran}."


_TODOS = (
    [c.name for c in CASES + SWEEP_CASES]
    + [c.name for c in COMBINED_CASES]
    + [c.name for c in BEAM_CASES]
)


@pytest.mark.parametrize("nombre", _TODOS)
def test_numeros_congelados(nombre, actual, esperado):
    """CONTRATO DURO. Un fallo aquí es una regresión hasta que se demuestre lo
    contrario: algún valor de ingeniería de una zapata aislada se movió."""
    lineas = diff_snapshots(esperado[nombre], actual[nombre], "numeros")
    assert not lineas, (
        f"El resultado numérico de '{nombre}' cambió.\n"
        f"Mecanismo que protege este caso: {_mecanismo(nombre)}\n"
        + "\n".join(lineas)
    )


@pytest.mark.parametrize("nombre", _TODOS)
def test_estados_congelados(nombre, actual, esperado):
    """CONTRATO DURO. Protege además la regla de que un WARNING no se convierta
    en PASS por haberse implementado otra cosa."""
    lineas = diff_snapshots(esperado[nombre], actual[nombre], "estados")
    assert not lineas, (
        f"Un estado de verificación de '{nombre}' cambió.\n"
        f"Mecanismo que protege este caso: {_mecanismo(nombre)}\n"
        + "\n".join(lineas)
    )


@pytest.mark.parametrize("nombre", _TODOS)
def test_trazas_en_fallo_congeladas(nombre, actual, esperado):
    lineas = diff_snapshots(esperado[nombre], actual[nombre], "trazas_en_fallo")
    assert not lineas, f"Cambió el conjunto de verificaciones en fallo de '{nombre}':\n" + "\n".join(lineas)


@pytest.mark.parametrize("nombre", _TODOS)
def test_referencias_normativas_congeladas(nombre, actual, esperado):
    """CONTRATO BLANDO. Cambiar una cita puede ser una CORRECCIÓN legítima; por
    eso el mensaje pide revisarla en vez de darla por errónea."""
    lineas = diff_snapshots(esperado[nombre], actual[nombre], "referencias")
    assert not lineas, (
        f"Cambió una referencia normativa en '{nombre}'. Si la corrección es "
        f"deliberada, revísala una por una y regenera con FREEZE_REGEN=1:\n"
        + "\n".join(lineas)
    )


@pytest.mark.parametrize("nombre", [c.name for c in SWEEP_CASES])
def test_decision_del_barrido_congelada(nombre, actual, esperado):
    """El h elegido y los h descartados son una DECISIÓN del motor, no un cálculo:
    merece contrato propio."""
    lineas = diff_snapshots(esperado[nombre], actual[nombre], "barrido")
    assert not lineas, f"Cambió la decisión del barrido de profundidad en '{nombre}':\n" + "\n".join(lineas)


def _mecanismo(nombre: str) -> str:
    for case in list(CASES) + list(SWEEP_CASES) + list(COMBINED_CASES):
        if case.name == nombre:
            return case.mechanism
    return "(desconocido)"
