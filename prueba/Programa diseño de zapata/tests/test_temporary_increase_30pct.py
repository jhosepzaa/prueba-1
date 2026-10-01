"""Incremento del 30 % de la presión admisible — E.060 §15.2.4, paridad entre tipologías.

QUÉ DICE LA FUENTE
==================
E.060 §15.2.4, literal: «Se podrá considerar un incremento del 30% en el valor de la presión
admisible del suelo para los estados de cargas en los que intervengan cargas temporales,
tales como sismo o viento».

Dos cosas del texto gobiernan la implementación:

1. **«se podrá»** — es potestativo. Por eso `allow_temporary_increase_30pct` es una
   declaración del proyectista y está apagada por defecto. El motor no lo aplica solo.
2. **«la presión admisible del suelo»** — el artículo habla del SUELO, no de una tipología.
   Aplicarlo en la aislada y no en la combinada era una inconsistencia del motor, no una
   distinción de la norma. Este archivo la cierra y la fija.

QUÉ FIJA
========
1. una sola implementación (`depth_solver.effective_qadm`) y un solo factor;
2. apagado por defecto: sin habilitarlo no cambia ningún número en ninguna tipología;
3. habilitado, se aplica en las tres y solo a combinaciones con sismo o viento;
4. la traza lo dice, citando §15.2.4 y no el capítulo entero;
5. no toca la estabilidad ni el diseño factorizado: es presión ADMISIBLE del suelo.
"""

from __future__ import annotations

import io
import pathlib

import pytest

from engine.codes.peru.e060_concrete import E060ConcreteCode
from engine.domain.column import Column
from engine.domain.column_placement import ColumnPlacement
from engine.domain.combined_layout import ColumnOnFooting, CombinedFootingLayout
from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.domain.materials import MaterialConcrete, MaterialSteel
from engine.domain.soil import PressureBasis, SoilProfile
from engine.foundation.combined_solver import solve_combined_footing
from engine.foundation.depth_solver import TEMPORARY_INCREASE_FACTOR, effective_qadm
from engine.reinforcement.face_reinforcement import TopCoverDeclaration
from engine.soil.contact_pressure import FullContactModel

CODE = E060ConcreteCode()
TAPA = TopCoverDeclaration(case="contacto_suelo_barras_pequenas")
MAT = dict(concrete=MaterialConcrete(fc_MPa=21.0), steel=MaterialSteel(fy_MPa=420.0))
COL = Column(shape="cuadrada", bx_m=0.50, by_m=0.50)
B, L, H = 8.0, 3.60, 0.80


def _suelo(*, incremento: bool, q=250.0):
    return SoilProfile(
        qadm_kPa=q, pressure_basis=PressureBasis.BRUTA, gamma_kNm3=18.0, Df_m=1.50,
        allow_temporary_increase_30pct=incremento,
    )


def _cargas(*, sismo=False, viento=False, P=900.0) -> LoadCaseSet:
    return LoadCaseSet(
        service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=P,
                                 includes_seismic_loads=sismo, includes_wind_loads=viento)],
        factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=1.4 * P,
                                  includes_seismic_loads=sismo, includes_wind_loads=viento)],
    )


def _layout(cargas, posiciones=(1.0, 7.0)) -> CombinedFootingLayout:
    if not isinstance(cargas, list):
        cargas = [cargas] * len(posiciones)
    return CombinedFootingLayout(
        B_m=B, L_m=L,
        columns=[
            ColumnOnFooting(label=f"C{i + 1}",
                            placement=ColumnPlacement(column=COL, offset_x_m=x - B / 2.0),
                            loads=cs)
            for i, (x, cs) in enumerate(zip(posiciones, cargas))
        ],
    )


def _combinada(cargas, *, incremento: bool, q=250.0):
    return solve_combined_footing(
        _layout(cargas), H, soil=_suelo(incremento=incremento, q=q), code=CODE,
        contact_model=FullContactModel(), top_cover=TAPA, **MAT,
    )


def _hip(r) -> str:
    return " ".join(r.trace.by_id("contact_pressure").hypotheses)


# =========================================================================
# 1. Una sola implementación
# =========================================================================


def test_el_factor_esta_declarado_una_sola_vez_en_el_motor():
    con_factor = [
        p for p in pathlib.Path("engine").rglob("*.py")
        if "TEMPORARY_INCREASE_FACTOR =" in p.read_text(encoding="utf-8")
    ]
    assert [p.name for p in con_factor] == ["depth_solver.py"]
    assert TEMPORARY_INCREASE_FACTOR == 1.30


def test_la_combinada_no_reimplementa_el_incremento():
    fuente = io.open("engine/foundation/combined_solver.py", encoding="utf-8").read()
    assert "effective_qadm(soil, temporal, hip)" in fuente
    assert "1.30" not in fuente and "1.3 *" not in fuente


def test_el_operador_se_reconstruye_a_mano():
    """φ del artículo: qadm × 1,30 solo si hay carga temporal y el usuario lo habilitó."""
    suelo = _suelo(incremento=True, q=200.0)
    for sismo, viento, esperado in ((False, False, 200.0), (True, False, 260.0),
                                    (False, True, 260.0), (True, True, 260.0)):
        combo = _cargas(sismo=sismo, viento=viento).service[0]
        assert effective_qadm(suelo, combo, []) == pytest.approx(esperado)
    # Apagado, nunca se aplica.
    apagado = _suelo(incremento=False, q=200.0)
    assert effective_qadm(apagado, _cargas(sismo=True).service[0], []) == pytest.approx(200.0)


# =========================================================================
# 2. Apagado por defecto: no cambia nada
# =========================================================================


def test_esta_apagado_por_defecto():
    """«Se podrá»: es potestativo, no una exigencia. El motor no lo aplica por su cuenta."""
    campo = SoilProfile.model_fields["allow_temporary_increase_30pct"]
    assert campo.default is False
    r = _combinada(_cargas(sismo=True), incremento=False)
    assert "Incremento del 30%" not in _hip(r)


def test_sin_carga_temporal_no_se_aplica_aunque_este_habilitado():
    con = _combinada(_cargas(), incremento=True)
    assert "Incremento del 30%" not in _hip(con)


# =========================================================================
# 3. Habilitado: paridad entre tipologías
# =========================================================================


def test_la_combinada_aplica_el_incremento_igual_que_la_aislada():
    """LA INCONSISTENCIA QUE CIERRA ESTE ARCHIVO: la combinada ignoraba el incremento y
    juzgaba la presión contra el qadm sin amplificar. El artículo no distingue tipologías."""
    q = 80.0  # qmax = 94,3 kPa: falla contra 80 y cumple contra 1,3 x 80 = 104
    sin = _combinada(_cargas(sismo=True), incremento=False, q=q)
    con = _combinada(_cargas(sismo=True), incremento=True, q=q)

    assert con.contact_pressure.qmax_kPa == pytest.approx(sin.contact_pressure.qmax_kPa, rel=1e-15), (
        "El incremento afecta a la presión ADMISIBLE, no a la calculada"
    )
    e_con = con.trace.by_id("contact_pressure")
    e_sin = sin.trace.by_id("contact_pressure")
    assert e_sin.status.discards and not e_con.status.discards, (
        "Con el incremento habilitado la misma geometría deja de fallar por presión"
    )
    assert "Incremento del 30%" in _hip(con)


def test_la_traza_cita_el_articulo_exacto():
    """§15.2 es el capítulo entero; el incremento está en §15.2.4."""
    texto = _hip(_combinada(_cargas(viento=True), incremento=True, q=80.0))
    assert "E.060 §15.2.4" in texto
    assert "sísmicas/viento" in texto


def test_basta_que_una_columna_declare_la_carga_temporal():
    """«estados de cargas en los que intervengan cargas temporales»: el estado de carga es
    de la combinación, no de una columna suelta."""
    q = 80.0
    # El sismo lo declara la SEGUNDA columna: si el motor se quedara con la primera, no lo
    # vería. Lo detectó una mutación deliberada.
    for mixto in ([_cargas(sismo=True), _cargas(sismo=False)],
                  [_cargas(sismo=False), _cargas(sismo=True)]):
        con = _combinada(mixto, incremento=True, q=q)
        assert "Incremento del 30%" in _hip(con)
        assert not con.trace.by_id("contact_pressure").status.discards
    # Y con ninguna columna sísmica no se aplica.
    ninguna = _combinada([_cargas(sismo=False), _cargas(sismo=False)], incremento=True, q=q)
    assert "Incremento del 30%" not in _hip(ninguna)


def test_el_motivo_de_descarte_cita_el_qadm_realmente_usado():
    """Si el motivo dijera el qadm sin amplificar, el número no cuadraría con el criterio."""
    q = 60.0  # falla incluso con el incremento
    r = _combinada(_cargas(sismo=True), incremento=True, q=q)
    motivo = next(m for m in r.discard_reasons if "Presión de contacto" in m)
    assert f"qadm={q * TEMPORARY_INCREASE_FACTOR:.1f} kPa" in motivo


# =========================================================================
# 4. Lo que el incremento NO toca
# =========================================================================


def test_no_toca_la_estabilidad_ni_el_diseno_factorizado():
    q = 80.0
    sin = _combinada(_cargas(sismo=True), incremento=False, q=q)
    con = _combinada(_cargas(sismo=True), incremento=True, q=q)
    assert con.diagram.M_max_positive_kNm == pytest.approx(sin.diagram.M_max_positive_kNm, rel=1e-15)
    assert con.bottom_face.As_design_m2 == pytest.approx(sin.bottom_face.As_design_m2, rel=1e-15)
    assert con.shear_longitudinal.Vu_kN == pytest.approx(sin.shear_longitudinal.Vu_kN, rel=1e-15)
    assert [p.ratio for p in con.punching] == [pytest.approx(p.ratio, rel=1e-15) for p in sin.punching]
