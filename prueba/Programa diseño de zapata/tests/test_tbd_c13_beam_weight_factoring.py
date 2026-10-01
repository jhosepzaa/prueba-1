"""TBD-C13 — factor de carga muerta del peso propio de la viga en modo directo.

CERRADO con la decisión A′ (2026-09-18): el factor es un DATO DEL PROYECTISTA, sin valor
por defecto. Declarado, se aplica a las combinaciones FACTORIZADAS y se traza. Sin
declarar, el peso entra sin amplificar y la entrada `beam_self_weight_mode` queda **NO
VERIFICADA** —sin `open_tbd`, porque falta un dato y no un criterio normativo
(`CLAUDE.md` §6)—. Es la misma regla que el proyecto usa con μ.

Estos tests fijan:
  1. sin el dato, el peso NO se factoriza y la entrada se degrada;
  2. con el dato, se aplica solo a las factorizadas y el servicio conserva el peso real;
  3. el modo por casos sigue resolviéndolo por composición, sin este dato;
  4. la limitación está registrada y neutralizada por la entrada que la hace visible.

Ver `docs/tbd_c13_factorizacion_peso_viga.md`.
"""

from __future__ import annotations

import pytest

from engine.analysis.connected_statics import (
    BEAM_SELF_WEIGHT_FACTOR_DECLARED,
    BEAM_SELF_WEIGHT_FACTORING_PENDING,
)
from engine.codes.peru.e060_concrete import E060ConcreteCode
from engine.domain.connected_layout import (
    AnalysisModel,
    BeamSelfWeightMode,
    BeamSupportMode,
    ConnectingBeamSpec,
    CoupleTransferMode,
)
from engine.foundation.connected_solver import solve_connected_footing
from engine.results.limitations import limitation_by_id
from engine.results.status import CheckStatus
from engine.soil.contact_pressure import KernCheckModel
from tests.freeze.cases import CONNECTED_CASES, GEO_REF, SOIL_CONN_250, _conn_layout

POR_NOMBRE = {c.name: c for c in CONNECTED_CASES}


def _resolver(caso):
    return solve_connected_footing(
        caso.build_layout(), caso.geometry, soil=caso.soil, concrete=caso.concrete,
        steel=caso.steel, code=E060ConcreteCode(), contact_model=KernCheckModel(),
        depth_params=caso.depth_params,
    )


def _sistema(factor=None, z_b=0.30):
    """HV-2: sin relleno sobre el vano ni falta de contacto, de modo que lo único abierto
    sobre el peso de la viga es TBD-C13 y su efecto se ve aislado."""
    from tests.freeze.cases import CONCRETE_21, STEEL_420

    lay = _conn_layout(modelo=AnalysisModel.ARTICULADO,
                       modo=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION,
                       P_ext=850.0, P_int=1100.0, peso=BeamSelfWeightMode.EXPLICITO, z_b=z_b)
    if factor is not None:
        lay = lay.model_copy(update={
            "beam": lay.beam.model_copy(update={"self_weight_dead_load_factor": factor})
        })
    return solve_connected_footing(
        lay, GEO_REF, soil=SOIL_CONN_250, concrete=CONCRETE_21, steel=STEEL_420,
        code=E060ConcreteCode(), contact_model=KernCheckModel(),
        depth_params=POR_NOMBRE["Z8_peso_propio_de_viga_explicito"].depth_params)


# =========================================================================
# 1. Sin el dato: no se factoriza y la entrada se degrada
# =========================================================================


def test_sin_el_dato_el_peso_de_la_viga_no_se_factoriza():
    for nombre in ("Z8_peso_propio_de_viga_explicito",
                   "Z15_par_puro_con_peso_propio_de_viga_explicito"):
        r = _resolver(POR_NOMBRE[nombre])
        pesos = {d.combo_type: d.beam_self_weight_kN for d in r.statics}
        assert pesos["SERVICIO"] == pesos["FACTORIZADA"] > 0.0, nombre


def test_el_pendiente_solo_aparece_en_combinaciones_factorizadas_con_peso():
    r = _resolver(POR_NOMBRE["Z8_peso_propio_de_viga_explicito"])
    for d in r.statics:
        tiene = BEAM_SELF_WEIGHT_FACTORING_PENDING in d.hypotheses
        assert tiene is (d.combo_type == "FACTORIZADA"), d.combo_name

    e = r.trace.by_id("beam_self_weight_mode", scope="sistema")
    assert BEAM_SELF_WEIGHT_FACTORING_PENDING in e.hypotheses


def test_sin_peso_explicito_no_hay_pendiente():
    r = _resolver(POR_NOMBRE["Z1_articulado_equilibrio"])
    assert all(BEAM_SELF_WEIGHT_FACTORING_PENDING not in d.hypotheses for d in r.statics)
    e = r.trace.by_id("beam_self_weight_mode", scope="sistema")
    assert BEAM_SELF_WEIGHT_FACTORING_PENDING not in e.hypotheses


def test_sin_el_dato_la_entrada_queda_no_verificada_y_sin_open_tbd():
    """ACTUALIZADO en la decisión A′. Antes la entrada seguía en INFO: el pendiente podía
    producir un falso PASS y nada lo hacía visible en el estado. Ahora se degrada.

    Sin `open_tbd`: falta un DATO del proyectista, no un criterio normativo que el motor no
    tenga (`CLAUDE.md` §6). Es la misma distinción que con μ y con los FS."""
    r = _sistema()
    e = r.trace.by_id("beam_self_weight_mode", scope="sistema")
    assert BEAM_SELF_WEIGHT_FACTORING_PENDING in e.hypotheses
    assert e.status is CheckStatus.NOT_VERIFIED
    assert e.open_tbd is None
    assert "TBD-C13" not in r.open_tbds
    assert any("falta el factor de carga muerta" in m for m in r.discard_reasons)


# =========================================================================
# 2. Con el dato: se aplica, y solo donde corresponde
# =========================================================================


def test_con_el_dato_se_aplica_solo_a_las_factorizadas():
    """El servicio lleva el peso REAL; la factorizada, el peso por el factor declarado."""
    f = 1.4
    pesos = {d.combo_type: d.beam_self_weight_kN for d in _sistema(factor=f).statics}
    sin = {d.combo_type: d.beam_self_weight_kN for d in _sistema().statics}
    assert pesos["SERVICIO"] == pytest.approx(sin["SERVICIO"], rel=1e-15)
    assert pesos["FACTORIZADA"] == pytest.approx(f * sin["FACTORIZADA"], rel=1e-12)
    assert pesos["FACTORIZADA"] > pesos["SERVICIO"]


def test_con_el_dato_la_entrada_deja_de_estar_degradada_y_lo_dice():
    r = _sistema(factor=1.4)
    e = r.trace.by_id("beam_self_weight_mode", scope="sistema")
    assert e.status is CheckStatus.INFO
    assert BEAM_SELF_WEIGHT_FACTORING_PENDING not in e.hypotheses
    assert BEAM_SELF_WEIGHT_FACTOR_DECLARED.format(f=1.4) in e.hypotheses
    assert not any("falta el factor de carga muerta" in m for m in r.discard_reasons)


@pytest.mark.parametrize("f", [0.9, 1.0, 1.25, 1.4])
def test_el_factor_declarado_escala_el_peso_sin_tocar_la_geometria(f):
    """Reconstrucción: el desglose geométrico es el mismo, multiplicado por el factor."""
    base = _sistema().statics
    con = _sistema(factor=f).statics
    for d0, d1 in zip(base, con):
        b0, b1 = d0.beam_self_weight_breakdown, d1.beam_self_weight_breakdown
        esperado = f if d0.combo_type == "FACTORIZADA" else 1.0
        assert b1.span_kN == pytest.approx(esperado * b0.span_kN, rel=1e-12)
        assert b1.exterior_increment_kN == pytest.approx(esperado * b0.exterior_increment_kN, rel=1e-12)
        assert b1.interior_increment_kN == pytest.approx(esperado * b0.interior_increment_kN, rel=1e-12)
        assert b1.load_factor == pytest.approx(esperado)
        # La geometría no se mueve: es la misma viga.
        assert b1.s_span_m == b0.s_span_m and b1.soffit_above_base_m == b0.soffit_above_base_m


def test_un_factor_menor_que_uno_reduce_el_peso_factorizado():
    """E.060 §9.2 admite 0,9·CM. El motor no elige el factor: aplica el declarado, aunque
    reduzca el peso, porque es lo desfavorable para despegue y volcamiento."""
    pesos = {d.combo_type: d.beam_self_weight_kN for d in _sistema(factor=0.9).statics}
    sin = {d.combo_type: d.beam_self_weight_kN for d in _sistema().statics}
    assert pesos["FACTORIZADA"] < sin["FACTORIZADA"]


# =========================================================================
# 3. El dato no tiene valor por defecto y no se admite donde no aplica
# =========================================================================


def test_no_hay_factor_por_defecto():
    """Si apareciera un valor por defecto, el motor estaría suponiendo un factor de carga
    que la norma no fija para todas las combinaciones."""
    campo = ConnectingBeamSpec.model_fields["self_weight_dead_load_factor"]
    assert campo.default is None


def test_el_factor_no_se_admite_sin_peso_explicito():
    """Igual que z_b: un dato que no intervendría en ningún cálculo no se acepta en
    silencio."""
    with pytest.raises(ValueError, match="solo se declara con peso propio EXPLICITO"):
        ConnectingBeamSpec(
            b_m=0.30, h_m=0.60, d_m=0.54,
            support_mode=BeamSupportMode.SIN_APOYO,
            self_weight_mode=BeamSelfWeightMode.DESPRECIADO,
            self_weight_dead_load_factor=1.4,
        )


def test_el_factor_no_puede_ser_negativo():
    with pytest.raises(ValueError):
        ConnectingBeamSpec(
            b_m=0.30, h_m=0.60, d_m=0.54,
            support_mode=BeamSupportMode.SIN_APOYO,
            self_weight_mode=BeamSelfWeightMode.EXPLICITO,
            soffit_above_base_m=0.30,
            self_weight_dead_load_factor=-1.0,
        )


# =========================================================================
# 4. El modo por casos no necesita el dato, y la limitación queda registrada
# =========================================================================


def test_el_modo_por_casos_sigue_resolviendolo_por_composicion():
    """Fase 10B: ahí el factor sale de los casos CM y este dato no interviene. El test
    comprueba que la salida del modo por casos no depende de él."""
    import inspect

    import engine.analysis.connected_statics as m

    fuente = inspect.getsource(m.factored_beam_weight)
    assert "dead_load_factor" in fuente
    assert "combo_ext.composition is None" in fuente, "El dato solo actúa en modo directo"


def test_la_limitacion_esta_registrada_y_neutralizada():
    """El catálogo ya no tiene el hueco: una limitación capaz de producir un falso PASS
    tiene que nombrar la verificación que la hace visible."""
    lim = limitation_by_id("connected_beam_weight_factoring")
    assert lim.can_cause_false_pass is True
    assert lim.enforced_by == "beam_self_weight_mode"
    assert "TBD-C13" in lim.description
