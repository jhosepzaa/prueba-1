"""Fases 9a y 9c — peso propio de la viga por geometría física y par puro con peso (B*).

Todas las referencias de este archivo se escriben A MANO desde la geometría del caso de
referencia, sin llamar al código del motor que calcula lo mismo:

    zapata de lindero  [0,00 ; 2,00] m, h = 0,90     columna exterior 0,50 → a = 0,25
    zapata interior    [5,15 ; 7,35] m, h = 0,90     columna interior 0,50 → s_corte = 6,25
    viga b = 0,35  h = 1,20  γc = 24                 suelo Df = 1,50  γs = 18

    c_e = 0,50 (cara de la columna exterior)   c_i = 6,00 (cara de la columna interior)
    w_v = 0,35·1,20·24 = 10,08 kN/m

HV-1  z_b = 0,00 → z_t = 1,20: sobre cada zapata la viga ocupa 0,90 de concreto (ya
      contado) y 0,30 de relleno → Δw = 0,35·0,30·(24 − 18) = 0,63 kN/m.
HV-2  z_b = 0,30 → z_t = 1,50: 0,60 de concreto y 0,60 de relleno → Δw = 1,26 kN/m.

Ver `docs/fase9ac_peso_propio_viga.md`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.server import app
from engine.analysis.connected_statics import (
    FILL_OVER_SPAN_PENDING,
    beam_self_weight_breakdown,
    distribute_couple,
)
from engine.analysis.connecting_beam_statics import design_extreme, statics_tolerance
from engine.codes.peru.e060_concrete import E060ConcreteCode
from engine.domain.connected_layout import (
    AnalysisModel,
    BeamSelfWeightMode,
    BeamSupportMode,
    ConnectingBeamSpec,
    CoupleTransferMode,
)
from engine.foundation.connected_solver import solve_connected_footing
from engine.results.status import CheckStatus
from engine.soil.contact_pressure import KernCheckModel
from tests.freeze.cases import (
    CONCRETE_21,
    CONNECTED_CASES,
    GEO_REF,
    SOIL_CONN_250,
    STEEL_420,
    _conn_layout,
)

CODE = E060ConcreteCode()
KERN = KernCheckModel()
POR_NOMBRE = {c.name: c for c in CONNECTED_CASES}

# --- Referencias a mano -------------------------------------------------------
W_V = 0.35 * 1.20 * 24.0 * (5.15 - 2.00)          # 31,752 kN
X_V = (2.00 + 5.15) / 2.0                          # 3,575 m
DW_E = {0.0: 0.63 * 1.50, 0.30: 1.26 * 1.50}       # 0,945 / 1,890 kN sobre [0,50 ; 2,00]
DW_I = {0.0: 0.63 * 0.85, 0.30: 1.26 * 0.85}       # 0,5355 / 1,071 kN sobre [5,15 ; 6,00]
X_E, X_I = 1.25, 5.575
S, A, S_CUT, L1, F_I = 6.0, 0.25, 6.25, 2.00, 5.15


def _layout(modelo=AnalysisModel.ARTICULADO, modo=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION,
            z_b=0.0, M_ext=0.0, peso=BeamSelfWeightMode.EXPLICITO):
    return _conn_layout(modelo=modelo, modo=modo, P_ext=850.0, P_int=1100.0, M_ext=M_ext,
                        peso=peso, z_b=z_b if peso is BeamSelfWeightMode.EXPLICITO else None)


def _huellas(lay, geo=GEO_REF):
    return lay.footprints(geo.exterior_B_m, geo.exterior_L_m, geo.exterior_h_m,
                          geo.interior_B_m, geo.interior_L_m, geo.interior_h_m)


def _reparto(lay, combo="S1", geo=GEO_REF):
    todas = lay.exterior.loads.service + lay.exterior.loads.factored
    ce = next(c for c in todas if c.name == combo)
    ci = next(c for c in lay.interior.loads.service + lay.interior.loads.factored if c.name == combo)
    return distribute_couple(lay, _huellas(lay, geo), ce, ci, SOIL_CONN_250, 24.0)


def _resolver(lay, geo=GEO_REF):
    return solve_connected_footing(lay, geo, soil=SOIL_CONN_250, concrete=CONCRETE_21,
                                   steel=STEEL_420, code=CODE, contact_model=KERN,
                                   depth_params=POR_NOMBRE["Z8_peso_propio_de_viga_explicito"].depth_params)


def _estacion(bs, s):
    hallada = [e for e in bs.stations if abs(e.s_m - s) < 1e-9]
    assert len(hallada) == 1, f"no hay estación exacta en s = {s}"
    return hallada[0]


# =========================================================================
# 1. Declaración de la cota vertical
# =========================================================================


def test_explicito_exige_z_b_sin_valor_por_defecto():
    with pytest.raises(ValueError, match="cota vertical"):
        ConnectingBeamSpec(b_m=0.35, h_m=1.20, d_m=1.10, support_mode=BeamSupportMode.SIN_APOYO,
                           self_weight_mode=BeamSelfWeightMode.EXPLICITO)


def test_z_b_por_debajo_de_la_base_es_entrada_invalida():
    with pytest.raises(ValueError, match="ENTRADA_INVALIDA"):
        ConnectingBeamSpec(b_m=0.35, h_m=1.20, d_m=1.10, support_mode=BeamSupportMode.SIN_APOYO,
                           self_weight_mode=BeamSelfWeightMode.EXPLICITO, soffit_above_base_m=-0.10)


@pytest.mark.parametrize("modo", [BeamSelfWeightMode.DESPRECIADO, BeamSelfWeightMode.EN_CARGAS_DE_COLUMNA])
def test_z_b_solo_se_admite_con_explicito(modo):
    with pytest.raises(ValueError, match="solo se declara"):
        ConnectingBeamSpec(b_m=0.35, h_m=1.20, d_m=1.10, support_mode=BeamSupportMode.SIN_APOYO,
                           self_weight_mode=modo, soffit_above_base_m=0.0)


# =========================================================================
# 2. Descomposición física — HV-1 y HV-2
# =========================================================================


@pytest.mark.parametrize("z_b", [0.0, 0.30])
def test_descomposicion_hv(z_b):
    lay = _layout(z_b=z_b)
    bw = beam_self_weight_breakdown(lay, _huellas(lay), SOIL_CONN_250, 24.0)
    assert (bw.s_exterior_face_m, bw.s_span_start_m, bw.s_span_end_m, bw.s_interior_face_m) == \
        pytest.approx((0.50, L1, F_I, 6.00), abs=1e-12)
    assert bw.exterior_increment_kN == pytest.approx(DW_E[z_b], rel=1e-12)
    assert bw.span_kN == pytest.approx(W_V, rel=1e-12)
    assert bw.interior_increment_kN == pytest.approx(DW_I[z_b], rel=1e-12)
    assert (bw.s_exterior_increment_m, bw.s_span_m, bw.s_interior_increment_m) == \
        pytest.approx((X_E, X_V, X_I), abs=1e-12)
    assert bw.exterior_contact and bw.interior_contact
    d = _reparto(lay)
    assert d.beam_self_weight_kN == pytest.approx(DW_E[z_b] + W_V + DW_I[z_b], rel=1e-12)
    assert d.beam_self_weight_kN == pytest.approx({0.0: 33.2325, 0.30: 34.713}[z_b], rel=1e-12)


def test_s_corte_no_es_limite_de_peso():
    """Regresión del defecto de 9a: el tramo [L1, s_corte] daba 42,84 kN. El vano libre
    lo fijan las HUELLAS: alargar la zapata interior acorta W_V sin mover s_corte."""
    lay = _layout()
    d = _reparto(lay)
    assert d.beam_self_weight_kN != pytest.approx(0.35 * 1.20 * 24.0 * (S_CUT - L1))
    geo = GEO_REF.model_copy(update={"interior_B_m": 2.60})   # f_i = 6,25 − 1,30 = 4,95
    d2 = _reparto(lay, geo=geo)
    assert d2.s_cut_m == d.s_cut_m
    assert d2.beam_self_weight_breakdown.span_kN == pytest.approx(10.08 * (4.95 - 2.00), rel=1e-12)


def test_el_relleno_sobre_el_vano_queda_fuera_y_declarado():
    """HV-1 deja 0,30 m de relleno sobre la viga en el vano: no se suma y la entrada
    queda NO VERIFICADA. HV-2 no deja relleno: la entrada queda INFO."""
    r1 = _resolver(_layout(z_b=0.0))
    e1 = r1.trace.by_id("beam_self_weight_mode", scope="sistema")
    assert r1.statics[0].beam_self_weight_breakdown.fill_over_span
    assert e1.status is CheckStatus.NOT_VERIFIED and e1.open_tbd is None
    assert FILL_OVER_SPAN_PENDING in e1.hypotheses
    # El relleno no está en el peso: 33,2325 kN, sin los 0,35·0,30·18·3,15 = 5,954 kN.
    assert r1.statics[0].beam_self_weight_kN == pytest.approx(33.2325, rel=1e-12)

    r2 = _resolver(_layout(z_b=0.30))
    e2 = r2.trace.by_id("beam_self_weight_mode", scope="sistema")
    assert not r2.statics[0].beam_self_weight_breakdown.fill_over_span
    assert FILL_OVER_SPAN_PENDING not in e2.hypotheses
    # ACTUALIZADO en TBD-C13 A': sin relleno la entrada sigue degradada, pero por otro
    # motivo —falta el factor de CM del peso de la viga en modo directo—. Lo que este test
    # fija es que el pendiente del RELLENO desaparece; el de C13 tiene su propio archivo.
    assert all("relleno" not in m for m in r2.discard_reasons)


def test_viga_sin_contacto_con_la_zapata_queda_no_verificada():
    r = _resolver(_layout(z_b=1.00))       # fondo a 1,00 m, zapatas de 0,90 m
    bw = r.statics[0].beam_self_weight_breakdown
    assert not bw.exterior_contact and not bw.interior_contact
    e = r.trace.by_id("beam_self_weight_mode", scope="sistema")
    assert e.status is CheckStatus.NOT_VERIFIED
    assert any("no descansa sobre la zapata" in m for m in r.discard_reasons)


# =========================================================================
# 3. Reparto articulado con EQUILIBRIO — ΔW_i no va al cuerpo de la viga
# =========================================================================


@pytest.mark.parametrize("z_b", [0.0, 0.30])
def test_reparto_articulado_equilibrio_a_mano(z_b):
    d = _reparto(_layout(z_b=z_b))
    # ΣM en s_corte sobre {zapata exterior + viga}: ΔW_i NO está en el cuerpo.
    R = (850.0 * (S_CUT - A) + DW_E[z_b] * (S_CUT - X_E) + W_V * (S_CUT - X_V)) / (S_CUT - L1 / 2)
    assert d.R_ext_kN == pytest.approx(R, rel=1e-12)
    assert d.P_ext_corrected_kN == pytest.approx(R, rel=1e-12)
    assert d.P_int_corrected_kN == pytest.approx(
        1100.0 + 850.0 + DW_E[z_b] + W_V - R + DW_I[z_b], rel=1e-12)
    if z_b == 0.0:
        assert d.R_ext_kN == pytest.approx(988.506971, abs=5e-7)


# =========================================================================
# 4. Conservación de carga
# =========================================================================


@pytest.mark.parametrize("modelo, modo", [
    (AnalysisModel.ARTICULADO, CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION),
    (AnalysisModel.ARTICULADO, CoupleTransferMode.PAR_PURO_EN_ZAPATA),
    (AnalysisModel.CUERPO_RIGIDO, CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION),
])
@pytest.mark.parametrize("z_b", [0.0, 0.30])
@pytest.mark.parametrize("combo", ["S1", "U1"])
def test_conservacion_de_carga(modelo, modo, z_b, combo):
    d = _reparto(_layout(modelo=modelo, modo=modo, z_b=z_b, M_ext=120.0), combo)
    W = DW_E[z_b] + W_V + DW_I[z_b]
    suma = d.P_ext_corrected_kN + d.P_int_corrected_kN - d.P_ext_kN - d.P_int_kN
    if modo is CoupleTransferMode.PAR_PURO_EN_ZAPATA:
        # Falta EXACTAMENTE la rama del par; el peso de la viga llega entero.
        assert suma == pytest.approx(W - d.delta_P_kN, abs=1e-9)
        assert d.expected_residual_kN == -d.delta_P_kN
    else:
        assert suma == pytest.approx(W, abs=1e-9)
    assert d.load_conservation_residual_kN == pytest.approx(0.0, abs=1e-9)
    assert d.closes


# =========================================================================
# 5. PAR_PURO + EXPLICITO — formulación B*
# =========================================================================


@pytest.mark.parametrize("z_b", [0.0, 0.30])
def test_b_estrella_a_mano(z_b):
    d = _reparto(_layout(modo=CoupleTransferMode.PAR_PURO_EN_ZAPATA, z_b=z_b))
    N_a = W_V * (S_CUT - X_V) / S
    assert d.beam_node_reaction_kN == pytest.approx(N_a, rel=1e-12)
    # El peso del vano NO se suma entero a P_ext: solo su reacción en el nudo.
    R = 850.0 + N_a + DW_E[z_b]
    assert d.R_ext_kN == pytest.approx(R, rel=1e-12)
    C_Z = -((850.0 + N_a) * (L1 / 2 - A) - (X_E - L1 / 2) * DW_E[z_b])
    assert d.M_couple_kNm == pytest.approx(C_Z, rel=1e-12)
    dP = -C_Z / S
    assert d.delta_P_kN == pytest.approx(dP, rel=1e-12)
    assert d.P_int_corrected_kN == pytest.approx(
        1100.0 - dP + W_V * (X_V - A) / S + DW_I[z_b], rel=1e-12)
    if z_b == 0.0:
        assert (d.R_ext_kN, d.M_couple_kNm, d.delta_P_kN, d.P_int_corrected_kN) == pytest.approx(
            (865.1011, -647.880825, 107.980137, 1010.15126), abs=5e-6)


def test_b_estrella_coincide_con_equilibrio_cuando_el_par_es_nulo():
    """Si no hay par que transferir, el modo del par no puede cambiar nada: con C_Z = 0
    PAR_PURO y EQUILIBRIO deben dar el mismo reparto. Es la propiedad que descarta la
    lectura literal «fuerza neta nula» (C), que mandaría peso al pórtico igualmente.

    M_E050 que anula C_Z, a mano: e1·(P + N_a) − (x_e − L1/2)·ΔW_e."""
    N_a = W_V * (S_CUT - X_V) / S
    M = (L1 / 2 - A) * (850.0 + N_a) - (X_E - L1 / 2) * DW_E[0.0]
    pp = _reparto(_layout(modo=CoupleTransferMode.PAR_PURO_EN_ZAPATA, M_ext=M))
    eq = _reparto(_layout(modo=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION, M_ext=M))
    assert pp.M_couple_kNm == pytest.approx(0.0, abs=1e-9)
    assert pp.delta_P_kN == pytest.approx(0.0, abs=1e-9)
    for campo in ("R_ext_kN", "P_ext_corrected_kN", "P_int_corrected_kN", "V_cut_kN",
                  "M_ext_corrected_kNm", "beam_self_weight_kN"):
        assert getattr(pp, campo) == pytest.approx(getattr(eq, campo), rel=1e-12, abs=1e-9), campo


def test_p1_despreciado_bit_a_bit():
    """Aragón P1 con peso DESPRECIADO: se reejecuta aquí la aritmética de PAR_PURO previa
    a 9c, operación por operación, y se exige igualdad EXACTA (==), no aproximada."""
    caso = POR_NOMBRE["Z11_aragon_p1_articulado"]
    lay = caso.build_layout()
    fp = lay.footprints(caso.geometry.exterior_B_m, caso.geometry.exterior_L_m,
                        caso.geometry.exterior_h_m, caso.geometry.interior_B_m,
                        caso.geometry.interior_L_m, caso.geometry.interior_h_m)
    for ce, ci in zip(lay.exterior.loads.service + lay.exterior.loads.factored,
                      lay.interior.loads.service + lay.interior.loads.factored):
        d = distribute_couple(lay, fp, ce, ci, caso.soil, caso.concrete.unit_weight_kNm3)
        L1_ = fp.exterior.length_m
        a = lay.exterior.anchor.axis_distance_to_column_center_m(lay.exterior.column)
        sc = L1_ / 2.0
        suma_M = sum(x for x in ((a - sc) * -ce.P_kN, (sc - sc) * ce.P_kN)) + (-ce.Mx_kNm)
        M_par = -suma_M
        dP = -M_par / lay.axis_distance_m
        assert d.beam_self_weight_breakdown is None and d.beam_node_reaction_kN is None
        assert d.R_ext_kN == ce.P_kN
        assert d.M_couple_kNm == M_par
        assert d.delta_P_kN == dP
        assert d.V_cut_kN == -dP
        assert d.P_int_corrected_kN == ci.P_kN - dP
        assert d.residual_force_kN == sum(x for x in (-ce.P_kN, ce.P_kN))
        assert d.residual_moment_kNm == suma_M + M_par

    r = solve_connected_footing(lay, caso.geometry, soil=caso.soil, concrete=caso.concrete,
                                steel=caso.steel, code=CODE, contact_model=KERN,
                                depth_params=caso.depth_params)
    repartos = {d.combo_name: d for d in r.statics}
    for bs in r.beam_statics:
        d = repartos[bs.combo_name]
        V = -d.M_couple_kNm / d.S_m
        assert [e.s_m for e in bs.stations] == [d.a_m, d.a_m + 0.25, d.s_cut_m]
        for e in bs.stations:
            assert e.V_kN == V
            assert e.M_kNm == d.M_couple_kNm * (1.0 - (e.s_m - d.a_m) / d.S_m)


# =========================================================================
# 6. Estaciones de carga de la viga
# =========================================================================


def test_estaciones_articulado_equilibrio():
    r = _resolver(_layout(z_b=0.0))
    for bs in r.beam_statics:
        v_ce, v_l1 = _estacion(bs, 0.50).V_kN, _estacion(bs, L1).V_kN
        e_fi, e_cut = _estacion(bs, F_I), _estacion(bs, S_CUT)
        # [c_e, L1]: reacción uniforme hacia arriba menos ΔW_e.
        assert v_l1 - v_ce == pytest.approx(bs.w_up_kNm * (L1 - 0.50) - DW_E[0.0], abs=1e-9)
        # Vano libre: baja exactamente W_V.
        assert e_fi.V_kN - v_l1 == pytest.approx(-W_V, abs=1e-9)
        # Sobre la huella interior la viga no lleva peso: ΔW_i es de la zapata interior.
        assert e_cut.V_kN == pytest.approx(e_fi.V_kN, abs=1e-9)
        M_l1 = _estacion(bs, L1).M_kNm
        assert e_fi.M_kNm == pytest.approx(M_l1 + v_l1 * (F_I - L1) - W_V * (F_I - L1) / 2, abs=1e-9)
        assert e_cut.M_kNm == pytest.approx(0.0, abs=1e-6)
        assert bs.cut_moment_consistent


def test_estaciones_par_puro_b_estrella():
    r = _resolver(_layout(modo=CoupleTransferMode.PAR_PURO_EN_ZAPATA, z_b=0.0))
    N_a = W_V * (S_CUT - X_V) / S
    repartos = {d.combo_name: d for d in r.statics}
    for bs in r.beam_statics:
        d = repartos[bs.combo_name]
        V_a = -d.M_couple_kNm / S + N_a
        assert _estacion(bs, A).V_kN == pytest.approx(V_a, rel=1e-12)
        assert _estacion(bs, L1).V_kN == pytest.approx(V_a, rel=1e-12)
        assert _estacion(bs, F_I).V_kN == pytest.approx(V_a - W_V, rel=1e-12)
        assert _estacion(bs, S_CUT).V_kN == pytest.approx(V_a - W_V, rel=1e-12)
        M_fi = d.M_couple_kNm * (1 - (F_I - A) / S) + N_a * (F_I - A) - W_V * (F_I - X_V)
        assert _estacion(bs, F_I).M_kNm == pytest.approx(M_fi, rel=1e-12)
        assert _estacion(bs, S_CUT).M_kNm == pytest.approx(0.0, abs=1e-6)
        assert bs.cut_moment_consistent
        assert bs.V_design_kN == pytest.approx(abs(V_a), rel=1e-12)


def test_estaciones_cuerpo_rigido():
    r = _resolver(_layout(modelo=AnalysisModel.CUERPO_RIGIDO, z_b=0.30, M_ext=150.0))
    for bs in r.beam_statics:
        assert _estacion(bs, F_I).V_kN - _estacion(bs, L1).V_kN == pytest.approx(-W_V, abs=1e-9)
        assert bs.cut_moment_consistent


# =========================================================================
# 7. Ruido en la rótula — defecto destapado en 9a
# =========================================================================


def test_el_residuo_de_la_rotula_no_es_demanda_de_diseno():
    d = _reparto(_layout())
    tol = statics_tolerance(d)
    assert design_extreme(3.83693077e-13, tol) == 0.0
    assert design_extreme(-5.0, tol) == 0.0
    assert design_extreme(10.0, tol) == 10.0


def test_z8_conserva_el_acero_minimo_positivo():
    """Con el residuo de 3,8e-13 kN·m tomado como Mu⁺, E.060 §10.5.3 eximía el acero mínimo
    positivo y la viga quedaba sin él. Mu⁺ = 0 exacto mantiene el mínimo gobernando."""
    r = _resolver(POR_NOMBRE["Z8_peso_propio_de_viga_explicito"].build_layout())
    assert r.beam.Mu_positive_kNm == 0.0
    assert r.beam.min_steel_positive.exempt_by_10_5_3 is False
    assert r.beam.As_positive_m2 == pytest.approx(0.000924152765, rel=1e-8)


# =========================================================================
# 8. API — campo aditivo
# =========================================================================


def _peticion_api(beam: dict) -> dict:
    combos = lambda P: [{"name": "S1", "type": "SERVICIO", "P_kN": P},
                        {"name": "U1", "type": "FACTORIZADA", "P_kN": P * 1.4}]
    return {
        "project_name": "9a", "analysis_model": "ARTICULADO",
        "couple_transfer_mode": "PAR_PURO_EN_ZAPATA",
        "exterior": {"label": "Z1", "bx_m": 0.50, "by_m": 0.50, "combinations": combos(850.0)},
        "interior": {"label": "Z2", "bx_m": 0.50, "by_m": 0.50, "combinations": combos(1100.0)},
        "anchor": {"edge": "X_MIN", "face_clearance_m": 0.0},
        "beam": {"b_m": 0.35, "h_m": 1.20, "d_m": 1.10, "support_mode": "SIN_APOYO", **beam},
        "axis_distance_m": 6.0,
        "soil": {"qadm_kPa": 250.0, "gamma_kNm3": 18.0, "Df_m": 1.50,
                 "FS_overturning_required": 1.5, "source_notes": "9a"},
        "search": {
            "ext_long_min_m": 2.0, "ext_long_max_m": 2.0, "ext_long_step_m": 0.4,
            "ext_transv_min_m": 2.4, "ext_transv_max_m": 2.4, "ext_transv_step_m": 0.4,
            "int_long_min_m": 2.2, "int_long_max_m": 2.2, "int_long_step_m": 0.4,
            "int_transv_min_m": 2.2, "int_transv_max_m": 2.2, "int_transv_step_m": 0.4,
            "h_min_m": 0.90, "h_max_m": 0.90, "h_step_m": 0.20,
            "same_depth_both_footings": True, "max_systems": 10,
        },
        "top_n": 1,
    }


def test_api_exige_z_b_con_explicito_y_lo_acepta_declarado():
    cliente = TestClient(app)
    r = cliente.post("/api/design-connected", json=_peticion_api({"self_weight_mode": "EXPLICITO"}))
    assert r.status_code == 422 and "cota vertical" in r.text
    r = cliente.post("/api/design-connected", json=_peticion_api(
        {"self_weight_mode": "EXPLICITO", "soffit_above_base_m": 0.30}))
    assert r.status_code == 200, r.text
