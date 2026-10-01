"""FASE 5A — D1 (compatibilidad de modelo) y D3 (estática de la viga de conexión).

QUÉ SE DEMUESTRA, Y POR QUÉ DE FORMA INDEPENDIENTE
==================================================
Los cinco bloques corresponden a los cinco puntos pedidos:

  1. Equilibrio de la viga en cuerpo rígido.
  2. Entrada correcta del momento de columna (E.050 art. 28.1).
  3. `cut_moment_consistent = True` en los casos corregidos, y que ya no se ignora.
  4. Rechazo de CUERPO_RIGIDO + PAR_PURO_EN_ZAPATA.
  5. Que D3 no mueve las zapatas ni el reparto.

La referencia de los bloques 1 y 2 NO usa el código nuevo. El campo de presión del
cuerpo rígido se reconstruye aquí desde la geometría cruda —área, centroide e inercia
calculados a mano, sin `Footprints`, sin `_rigid_pressure`, sin `rigid_pressure_field`—
y se integra por Simpson, no con las primitivas cerradas del motor. Si el motor y este
archivo coinciden, coinciden dos derivaciones distintas.

La referencia del bloque 5 es un archivo extraído del baseline ANTERIOR a 5A, con la
lista de claves fijada antes de implementar.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

import engine.foundation.connected_solver as solver_module
from engine.analysis.connected_statics import distribute_couple
from engine.analysis.connecting_beam_statics import solve_connecting_beam
from engine.codes.peru.e060_concrete import E060ConcreteCode
from engine.domain.connected_layout import (
    AnalysisModel,
    BeamSelfWeightMode,
    BeamSupportMode,
    CoupleTransferMode,
    check_couple_mode_compatible,
)
from engine.domain.search_parameters import DepthSearchParameters
from engine.foundation.connected_solver import (
    ConnectedFootingGeometry,
    solve_connected_footing,
)
from engine.optimization.connected_generator import (
    ConnectedSearchParameters,
    RejectionReason,
    generate_connected_alternatives,
)
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
from tests.freeze.snapshot import snapshot_connected, trace_key

CODE = E060ConcreteCode()
KERN = KernCheckModel()
DEPTH = DepthSearchParameters(h_min_m=0.40, h_max_m=1.20, h_step_m=0.05)
REFERENCIA = Path(__file__).parent / "freeze" / "reference_pre_5a_non_beam.json"

RIGIDOS = [
    "Z3_cuerpo_rigido_equilibrio",
    "Z12_aragon_p2_cuerpo_rigido",
    "Z14_cuerpo_rigido_con_momento_de_columna",
]
CORREGIDOS = RIGIDOS + ["Z13_articulado_con_momento_de_columna"]


def _caso(nombre: str):
    return next(c for c in CONNECTED_CASES if c.name == nombre)


def _resolver_caso(nombre: str):
    c = _caso(nombre)
    return c, solve_connected_footing(
        c.build_layout(), c.geometry, soil=c.soil, concrete=c.concrete, steel=c.steel,
        code=CODE, contact_model=KERN, depth_params=c.depth_params,
    )


def _factorizado(result):
    return next(d for d in result.statics if d.combo_type == "FACTORIZADA")


def _estacion(beam_statics, s: float):
    """La estación EN `s`. Falla si no existe: tomar la más cercana dejaba pasar una
    comparación contra otra sección sin que nada lo delatara."""
    e = min(beam_statics.stations, key=lambda e: abs(e.s_m - s))
    assert abs(e.s_m - s) < 1e-9, (
        f"No hay estación en s = {s:.6f} m; la más cercana está en {e.s_m:.6f} m."
    )
    return e


# =========================================================================
# Referencia INDEPENDIENTE del cuerpo rígido
# =========================================================================


def _simpson(f, a: float, b: float, n: int = 2000) -> float:
    if n % 2:
        n += 1
    h = (b - a) / n
    total = f(a) + f(b)
    for i in range(1, n):
        total += (4 if i % 2 else 2) * f(a + i * h)
    return total * h / 3.0


class _Rigido:
    """Cuerpo rígido reconstruido desde la geometría cruda, sin código del motor.

    Solo toma del resultado lo que D3 NO toca y que el bloque 5 protege aparte: las
    cargas de la combinación y los pesos propios de las zapatas."""

    def __init__(self, layout, geometry: ConnectedFootingGeometry, d, soil=None,
                 gamma_c_zapata: float = 24.0):
        eje_x = layout.longitudinal_axis == "X"
        col = layout.exterior.column
        self.a = layout.exterior.anchor.face_clearance_m + (col.bx_m if eje_x else col.by_m) / 2.0
        self.S = layout.axis_distance_m
        self.s_cut = self.a + self.S

        self.Le = geometry.exterior_B_m if eje_x else geometry.exterior_L_m
        self.Be = geometry.exterior_L_m if eje_x else geometry.exterior_B_m
        self.Li = geometry.interior_B_m if eje_x else geometry.interior_L_m
        self.Bi = geometry.interior_L_m if eje_x else geometry.interior_B_m

        self.xe = self.Le / 2.0
        self.xi = self.s_cut
        self.s_fin = self.xi - self.Li / 2.0

        Ae, Ai = self.Be * self.Le, self.Bi * self.Li
        self.A = Ae + Ai
        self.xc = (Ae * self.xe + Ai * self.xi) / self.A
        self.I = (
            self.Be * self.Le**3 / 12.0 + Ae * (self.xc - self.xe) ** 2
            + self.Bi * self.Li**3 / 12.0 + Ai * (self.xc - self.xi) ** 2
        )

        self.P_ext, self.P_int = d.P_ext_kN, d.P_int_kN
        self.M_ext, self.M_int = d.M_ext_kNm, d.M_int_kNm
        self.W_ext, self.W_int = d.W_ext_kN, d.W_int_kN
        self.W_viga = d.beam_self_weight_kN
        cargas = [(self.a, self.P_ext), (self.xi, self.P_int),
                  (self.xe, self.W_ext), (self.xi, self.W_int)]
        # Peso de la viga por geometría física (Fase 9a), reconstruido aquí desde la
        # geometría cruda: tramo sobre la huella exterior, vano libre y tramo sobre la
        # interior, cada uno con su peso NETO de lo que la zapata ya cuenta.
        self.dWe = self.WV = self.dWi = 0.0
        self.ce = self.a + (col.bx_m if eje_x else col.by_m) / 2.0
        if self.W_viga > 0.0:
            viga = layout.beam
            zb = viga.soffit_above_base_m
            zt = zb + viga.h_m
            gc, gs, Df = viga.concrete_unit_weight_kNm3, soil.gamma_kNm3, soil.Df_m

            def incremento(hf: float) -> float:
                dentro = max(0.0, min(zt, hf) - max(zb, 0.0))
                relleno = max(0.0, min(zt, Df) - max(zb, hf))
                aire = max(0.0, zt - max(zb, Df))
                return viga.b_m * ((gc - gamma_c_zapata) * dentro + (gc - gs) * relleno + gc * aire)

            col_i = layout.interior.column
            ci = self.s_cut - (col_i.bx_m if eje_x else col_i.by_m) / 2.0
            self.dWe = incremento(geometry.exterior_h_m) * (self.Le - self.ce)
            self.WV = viga.b_m * viga.h_m * gc * (self.s_fin - self.Le)
            self.dWi = incremento(geometry.interior_h_m) * (ci - self.s_fin)
            assert self.dWe + self.WV + self.dWi == pytest.approx(self.W_viga, rel=1e-12)
            cargas += [((self.ce + self.Le) / 2.0, self.dWe),
                       ((self.Le + self.s_fin) / 2.0, self.WV),
                       ((self.s_fin + ci) / 2.0, self.dWi)]
        self.P = sum(P for _, P in cargas)
        x_R = (sum(x * P for x, P in cargas) + self.M_ext + self.M_int) / self.P
        self.e = x_R - self.xc

    def p(self, s: float) -> float:
        return self.P / self.A + self.P * self.e * (s - self.xc) / self.I

    def V_vano(self, s: float) -> float:
        """Cortante en el vano libre, cuerpo libre izquierdo, fuerzas + arriba."""
        R = _simpson(lambda t: self.Be * self.p(t), 0.0, self.Le)
        v = R - self.W_ext - self.P_ext
        if self.W_viga > 0.0:
            v -= self.dWe + self.WV * (s - self.Le) / (self.s_fin - self.Le)
        return v

    def M_vano(self, s: float) -> float:
        """Momento en el vano libre: Σ F_up·(s − s_i) + M_E050."""
        m = _simpson(lambda t: self.Be * self.p(t) * (s - t), 0.0, self.Le)
        m -= self.W_ext * (s - self.xe)
        m -= self.P_ext * (s - self.a)
        m += self.M_ext
        if self.W_viga > 0.0:
            m -= self.dWe * (s - (self.ce + self.Le) / 2.0)
            tramo = s - self.Le
            m -= self.WV * tramo / (self.s_fin - self.Le) * (tramo / 2.0)
        return m


def _rigido_de(nombre: str):
    c, r = _resolver_caso(nombre)
    d = _factorizado(r)
    return c, r, d, _Rigido(c.build_layout(), c.geometry, d)


# =========================================================================
# 1. Equilibrio de la viga en cuerpo rígido
# =========================================================================


@pytest.mark.parametrize("nombre", RIGIDOS)
def test_el_campo_independiente_equilibra_la_carga_total(nombre):
    """Control de la propia referencia: si el campo reconstruido aquí no equilibrara
    la carga, los tests siguientes compararían contra un número sin sentido."""
    _, _, _, rig = _rigido_de(nombre)
    R_ext = _simpson(lambda t: rig.Be * rig.p(t), 0.0, rig.Le)
    R_int = _simpson(lambda t: rig.Bi * rig.p(t), rig.xi - rig.Li / 2.0, rig.xi + rig.Li / 2.0)
    assert R_ext + R_int == pytest.approx(rig.P, rel=1e-10)


@pytest.mark.parametrize("nombre", RIGIDOS)
def test_equilibrio_vertical_de_la_viga_rigida(nombre):
    """ΣF_v sobre el cuerpo libre izquierdo: el cortante del vano es la reacción real
    bajo la zapata exterior, menos su peso propio, menos la carga de columna.

    Antes de 5A el motor omitía el peso propio y usaba la reacción bruta: en Z3 el
    cortante salía 325,5 kN frente a 170,0 kN."""
    _, r, _, rig = _rigido_de(nombre)
    V_ref = rig.V_vano(rig.Le)
    assert r.beam.shear.Vu_kN == pytest.approx(abs(V_ref), rel=1e-9)
    for s in (rig.Le, rig.s_fin):
        assert _estacion(r.beam_statics[0], s).V_kN == pytest.approx(V_ref, rel=1e-9)


@pytest.mark.parametrize("nombre", RIGIDOS)
def test_equilibrio_de_momentos_de_la_viga_rigida(nombre):
    """ΣM sobre el cuerpo libre izquierdo en los dos extremos del vano libre."""
    _, r, _, rig = _rigido_de(nombre)
    for s in (rig.Le, rig.s_fin):
        assert _estacion(r.beam_statics[0], s).M_kNm == pytest.approx(
            rig.M_vano(s), rel=1e-9, abs=1e-6
        )


@pytest.mark.parametrize("nombre", RIGIDOS)
def test_el_diagrama_rigido_cumple_dM_ds_igual_a_V(nombre):
    """Equilibrio de una rebanada del vano: sin carga, dM/ds = V. Lo comprueba el
    diagrama del motor contra sí mismo, entre sus dos estaciones del vano libre."""
    _, r, _, rig = _rigido_de(nombre)
    b = r.beam_statics[0]
    e0, e1 = _estacion(b, rig.Le), _estacion(b, rig.s_fin)
    pendiente = (e1.M_kNm - e0.M_kNm) / (e1.s_m - e0.s_m)
    assert pendiente == pytest.approx(e0.V_kN, rel=1e-9)


@pytest.mark.parametrize("nombre", RIGIDOS)
def test_llevar_el_vano_al_eje_interior_reproduce_el_reparto(nombre):
    """La referencia independiente, trasladada al eje de la columna interior, debe dar
    el momento que el REPARTO calculó por su cuenta. Cierra el triángulo: reparto,
    motor de viga y este archivo describen el mismo cuerpo."""
    _, _, d, rig = _rigido_de(nombre)
    M_eje = rig.M_vano(rig.s_fin) + rig.V_vano(rig.s_fin) * (rig.s_cut - rig.s_fin)
    assert M_eje == pytest.approx(d.M_cut_kNm, rel=1e-8, abs=1e-6)


@pytest.mark.parametrize("nombre", RIGIDOS)
def test_la_viga_rigida_no_fabrica_momento_positivo(nombre):
    """En el vano libre de estos casos el momento es negativo de extremo a extremo. El
    diagrama anterior, con presión uniforme y reacción bruta, fabricaba Mu⁺ de hasta
    816 kN·m que no existen."""
    _, r, _, rig = _rigido_de(nombre)
    assert rig.M_vano(rig.Le) < 0 and rig.M_vano(rig.s_fin) < 0
    assert r.beam.Mu_positive_kNm == 0.0
    assert r.beam.Mu_negative_kNm == pytest.approx(
        max(-rig.M_vano(rig.Le), -rig.M_vano(rig.s_fin)), rel=1e-9
    )


def test_equilibrio_de_la_viga_rigida_con_peso_propio_explicito():
    """Ningún caso rígido congelado declara peso propio de viga EXPLICITO. Este cierra
    el hueco: la viga reparte su peso en su tramo físico (Fase 9a: ΔW_e sobre la huella
    exterior y W_V en el vano libre; ΔW_i es de la zapata interior) y el contraste con
    el reparto —que trata cada tramo como carga puntual en su centro— sigue cerrando."""
    lay = _conn_layout(
        modelo=AnalysisModel.CUERPO_RIGIDO,
        modo=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION,
        P_ext=850.0, P_int=1100.0, M_ext=150.0,
        peso=BeamSelfWeightMode.EXPLICITO, z_b=0.0,
    )
    r = solve_connected_footing(lay, GEO_REF, soil=SOIL_CONN_250, concrete=CONCRETE_21,
                                steel=STEEL_420, code=CODE, contact_model=KERN,
                                depth_params=DEPTH)
    d = _factorizado(r)
    assert d.beam_self_weight_kN > 0
    rig = _Rigido(lay, GEO_REF, d, soil=SOIL_CONN_250)
    b = r.beam_statics[0]
    assert b.cut_moment_consistent
    for s in (rig.Le, rig.s_fin):
        e = _estacion(b, s)
        assert e.V_kN == pytest.approx(rig.V_vano(s), rel=1e-9)
        assert e.M_kNm == pytest.approx(rig.M_vano(s), rel=1e-9, abs=1e-6)


# =========================================================================
# 2. Entrada correcta del momento de columna
# =========================================================================


def _articulado_con_momento(M: float):
    lay = _conn_layout(
        modelo=AnalysisModel.ARTICULADO,
        modo=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION,
        P_ext=850.0, P_int=1100.0, M_ext=M,
    )
    fp = lay.footprints(GEO_REF.exterior_B_m, GEO_REF.exterior_L_m, GEO_REF.exterior_h_m,
                        GEO_REF.interior_B_m, GEO_REF.interior_L_m, GEO_REF.interior_h_m)
    combo_e, combo_i = lay.exterior.loads.factored[0], lay.interior.loads.factored[0]
    d = distribute_couple(lay, fp, combo_e, combo_i, SOIL_CONN_250)
    return lay, fp, d


def test_el_momento_de_columna_se_superpone_exactamente():
    """Aísla M2. Mismo reparto —misma reacción—, solo cambia M_ext: el diagrama tiene
    que desplazarse EXACTAMENTE en ΔM a la derecha de la columna, no moverse a su
    izquierda, y dejar el cortante intacto (un par no produce cortante)."""
    lay, fp, d = _articulado_con_momento(0.0)
    delta = 275.0
    base = solve_connecting_beam(lay, d, fp)
    con = solve_connecting_beam(lay, d.model_copy(update={"M_ext_kNm": delta}), fp)

    for e0, e1 in zip(base.stations, con.stations):
        assert e1.s_m == e0.s_m
        assert e1.V_kN == e0.V_kN
        esperado = delta if e0.s_m > d.a_m else 0.0
        assert e1.M_kNm - e0.M_kNm == pytest.approx(esperado, abs=1e-9)


@pytest.mark.parametrize("M", [420.0, -420.0, 0.0])
def test_la_rotula_cierra_con_momento_de_columna(M):
    """En el modelo articulado M(s_corte) = 0 por definición. Antes de 5A, con momento
    de columna, el diagrama daba −M ahí: la rótula no cerraba y nadie lo leía."""
    lay, fp, d = _articulado_con_momento(M)
    b = solve_connecting_beam(lay, d, fp)
    assert b.M_at_cut_kNm == pytest.approx(0.0, abs=1e-7)
    assert b.cut_moment_consistent


@pytest.mark.parametrize("M", [420.0, -420.0])
def test_el_momento_de_columna_contra_un_cuerpo_libre_independiente(M):
    """Cuerpo libre izquierdo en el vano, escrito a mano: reacción neta uniforme en el
    centroide, carga de columna y +M_E050. Los DOS signos: el error anterior era −M, de
    modo que con el sismo invertido caía del lado inseguro."""
    lay, fp, d = _articulado_con_momento(M)
    b = solve_connecting_beam(lay, d, fp)
    L1 = fp.exterior.length_m
    # Estaciones del diagrama ARTICULADO: su tramo llega al eje interior (la rótula),
    # no al borde de la huella interior como el del cuerpo rígido.
    for s in (L1, d.s_cut_m):
        e = _estacion(b, s)
        assert e.s_m == pytest.approx(s, abs=1e-12), "no hay estación en esa sección"
        M_ref = d.R_ext_kN * (s - L1 / 2.0) - d.P_ext_kN * (s - d.a_m) + d.M_ext_kNm
        assert e.M_kNm == pytest.approx(M_ref, rel=1e-12, abs=1e-9)


def test_invertir_el_momento_de_columna_invierte_su_efecto():
    """El efecto del momento sobre el diagrama es impar en M: lo que suma con +M lo
    resta con −M. Se descuenta la parte que no depende del momento."""
    _, fp, d0 = _articulado_con_momento(0.0)
    lay_p, _, d_p = _articulado_con_momento(300.0)
    lay_n, _, d_n = _articulado_con_momento(-300.0)
    s = fp.exterior.length_m
    b0 = _estacion(solve_connecting_beam(lay_p, d0, fp), s).M_kNm
    bp = _estacion(solve_connecting_beam(lay_p, d_p, fp), s).M_kNm
    bn = _estacion(solve_connecting_beam(lay_n, d_n, fp), s).M_kNm
    assert (bp - b0) == pytest.approx(-(bn - b0), rel=1e-12)


def test_Z13_ya_no_arrastra_el_momento_de_columna():
    """Regresión concreta: Mu⁻ era 802,5 kN·m; el cuerpo libre da 382,5."""
    _, r = _resolver_caso("Z13_articulado_con_momento_de_columna")
    assert r.beam.Mu_negative_kNm == pytest.approx(382.5, abs=1e-6)


@pytest.mark.parametrize("M", [300.0, -300.0])
def test_el_momento_de_columna_en_cuerpo_rigido(M):
    """En rígido el momento cambia además el campo de presión, así que no se aísla por
    diferencia: se compara con la referencia independiente, en los dos signos."""
    lay = _conn_layout(
        modelo=AnalysisModel.CUERPO_RIGIDO,
        modo=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION,
        P_ext=850.0, P_int=1100.0, M_ext=M,
    )
    r = solve_connected_footing(lay, GEO_REF, soil=SOIL_CONN_250, concrete=CONCRETE_21,
                                steel=STEEL_420, code=CODE, contact_model=KERN,
                                depth_params=DEPTH)
    d = _factorizado(r)
    rig = _Rigido(lay, GEO_REF, d, soil=SOIL_CONN_250)
    b = r.beam_statics[0]
    assert b.cut_moment_consistent
    for s in (rig.Le, rig.s_fin):
        assert _estacion(b, s).M_kNm == pytest.approx(rig.M_vano(s), rel=1e-9, abs=1e-6)


# =========================================================================
# 3. El contraste cierra en los corregidos, y ya no se ignora
# =========================================================================


@pytest.mark.parametrize("nombre", CORREGIDOS)
def test_el_contraste_cierra_en_los_casos_corregidos(nombre):
    _, r = _resolver_caso(nombre)
    for b in r.beam_statics:
        assert b.cut_moment_consistent, (
            f"{nombre}/{b.combo_name}: diagrama {b.M_at_cut_kNm:.4f} frente a reparto "
            f"{b.M_cut_declared_kNm:.4f} kN·m"
        )


def test_el_contraste_cierra_en_todas_las_ternas_aceptadas():
    """No solo en las cinco corregidas: en TODAS las ternas congeladas que el motor
    resuelve. Antes de 5A salía False en cinco de ellas."""
    for c in CONNECTED_CASES:
        if c.expects_rejection:
            continue
        _, r = _resolver_caso(c.name)
        entradas = [e for e in r.trace.entries if e.id.startswith("beam_statics_")]
        assert entradas, f"{c.name}: falta la entrada de la viga en la traza"
        assert all(b.cut_moment_consistent for b in r.beam_statics), c.name
        assert all(e.status is CheckStatus.INFO for e in entradas), c.name


def test_un_contraste_que_no_cierra_descarta_la_alternativa(monkeypatch):
    """La prueba de que el campo ya no se ignora: si el diagrama y el reparto no
    coinciden, la alternativa sale FAIL, con la entrada de traza en FAIL y un motivo de
    descarte que lo dice. Se fuerza la discrepancia sustituyendo la estática de la viga
    por una que declara otro momento de junta."""
    original = solver_module.solve_connecting_beam

    def mentirosa(layout, d, footprints=None):
        b = original(layout, d, footprints)
        return b.model_copy(update={"cut_moment_consistent": False,
                                    "M_at_cut_kNm": b.M_at_cut_kNm + 123.0})

    monkeypatch.setattr(solver_module, "solve_connecting_beam", mentirosa)
    c = _caso("Z3_cuerpo_rigido_equilibrio")
    r = solve_connected_footing(c.build_layout(), c.geometry, soil=c.soil,
                                concrete=c.concrete, steel=c.steel, code=CODE,
                                contact_model=KERN, depth_params=c.depth_params)

    entradas = [e for e in r.trace.entries if e.id.startswith("beam_statics_")]
    assert entradas and all(e.status is CheckStatus.FAIL for e in entradas)
    assert r.overall_status is CheckStatus.FAIL
    assert any("La estática de la viga no cierra" in m for m in r.discard_reasons)


# =========================================================================
# 4. Rechazo de CUERPO_RIGIDO + PAR_PURO_EN_ZAPATA
# =========================================================================


def test_el_layout_rechaza_la_combinacion_incompatible():
    with pytest.raises(ValueError, match="Combinación incompatible"):
        _conn_layout(modelo=AnalysisModel.CUERPO_RIGIDO,
                     modo=CoupleTransferMode.PAR_PURO_EN_ZAPATA,
                     P_ext=850.0, P_int=1100.0)


@pytest.mark.parametrize("modelo, modo", [
    (AnalysisModel.CUERPO_RIGIDO, CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION),
    (AnalysisModel.ARTICULADO, CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION),
    (AnalysisModel.ARTICULADO, CoupleTransferMode.PAR_PURO_EN_ZAPATA),
])
def test_las_tres_combinaciones_compatibles_siguen_resolviendose(modelo, modo):
    """Control positivo: la validación no puede rechazar de más. El par puro sigue
    siendo válido en el modelo articulado, que es donde lo usa el libro."""
    check_couple_mode_compatible(modelo, modo)
    lay = _conn_layout(modelo=modelo, modo=modo, P_ext=850.0, P_int=1100.0)
    r = solve_connected_footing(lay, GEO_REF, soil=SOIL_CONN_250, concrete=CONCRETE_21,
                                steel=STEEL_420, code=CODE, contact_model=KERN,
                                depth_params=DEPTH)
    assert all(b.cut_moment_consistent for b in r.beam_statics)


def _layout_colado():
    """CUERPO_RIGIDO + PAR_PURO obtenido por `model_copy`, que NO ejecuta validadores."""
    lay = _conn_layout(modelo=AnalysisModel.CUERPO_RIGIDO,
                       modo=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION,
                       P_ext=850.0, P_int=1100.0)
    colado = lay.model_copy(update={"couple_transfer_mode": CoupleTransferMode.PAR_PURO_EN_ZAPATA})
    assert colado.couple_transfer_mode is CoupleTransferMode.PAR_PURO_EN_ZAPATA
    return colado


def test_la_combinacion_colada_por_model_copy_se_rechaza_en_el_reparto():
    colado = _layout_colado()
    with pytest.raises(ValueError, match="Combinación incompatible"):
        solve_connected_footing(colado, GEO_REF, soil=SOIL_CONN_250, concrete=CONCRETE_21,
                                steel=STEEL_420, code=CODE, contact_model=KERN,
                                depth_params=DEPTH)


def test_la_estatica_de_la_viga_rechaza_un_reparto_incompatible():
    """Defensa en profundidad: un reparto construido a mano con la combinación
    incompatible tampoco llega a producir diagramas."""
    lay = _conn_layout(modelo=AnalysisModel.CUERPO_RIGIDO,
                       modo=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION,
                       P_ext=850.0, P_int=1100.0)
    fp = lay.footprints(GEO_REF.exterior_B_m, GEO_REF.exterior_L_m, GEO_REF.exterior_h_m,
                        GEO_REF.interior_B_m, GEO_REF.interior_L_m, GEO_REF.interior_h_m)
    d = distribute_couple(lay, fp, lay.exterior.loads.factored[0],
                          lay.interior.loads.factored[0], SOIL_CONN_250)
    falso = d.model_copy(update={"couple_transfer_mode": CoupleTransferMode.PAR_PURO_EN_ZAPATA})
    with pytest.raises(ValueError, match="Combinación incompatible"):
        solve_connecting_beam(lay, falso, fp)


def test_la_busqueda_rechaza_la_combinacion_sin_detenerse():
    """El rechazo se clasifica como ENTRADA_INVALIDA y el barrido termina: es una
    negativa del motor más, no una excepción que tumbe la búsqueda."""
    params = ConnectedSearchParameters(
        ext_long_min_m=2.0, ext_long_max_m=2.4, ext_long_step_m=0.4,
        ext_transv_min_m=2.4, ext_transv_max_m=2.4, ext_transv_step_m=0.4,
        int_long_min_m=2.2, int_long_max_m=2.2, int_long_step_m=0.4,
        int_transv_min_m=2.2, int_transv_max_m=2.2, int_transv_step_m=0.4,
        h_min_m=0.80, h_max_m=0.80, h_step_m=0.10, same_depth_both_footings=True,
    )
    r = generate_connected_alternatives(
        _layout_colado(), params, soil=SOIL_CONN_250, concrete=CONCRETE_21,
        steel=STEEL_420, code=CODE, contact_model=KERN, depth_params=DEPTH,
    )
    assert r.accepted == []
    assert r.evaluated_count == len(r.rejected) > 0
    assert r.rejections_by_reason() == {RejectionReason.ENTRADA_INVALIDA.value: len(r.rejected)}


def test_la_API_devuelve_422_con_el_motivo():
    from fastapi.testclient import TestClient

    from api.server import app
    from tests.test_connected_presentation_phase4e import _peticion

    r = TestClient(app).post("/api/design-connected", json=_peticion(
        analysis_model="CUERPO_RIGIDO", couple_transfer_mode="PAR_PURO_EN_ZAPATA",
    ))
    assert r.status_code == 422
    assert "Combinación incompatible" in json.dumps(r.json(), ensure_ascii=False)


# =========================================================================
# 5. D3 no mueve las zapatas ni el reparto
# =========================================================================


def _referencia() -> dict:
    return json.loads(REFERENCIA.read_text(encoding="utf-8"))


def _es_de_viga(clave_traza: str) -> bool:
    return clave_traza.startswith("viga/") or clave_traza.startswith("sistema/beam_statics_")


# CLAVES QUE ESTA REFERENCIA YA NO PUEDE EXIGIR, Y POR QUÉ NO SE REGENERA EL ARCHIVO
# ==================================================================================
# `reference_pre_5a_non_beam.json` vale como prueba precisamente por ser ANTERIOR a 5A.
# Regenerarla la convertiría en una foto del presente y dejaría de demostrar nada sobre
# D3: la afirmación «D3 no movió las zapatas» se comprobaría contra un archivo escrito
# después de D3. Por eso el archivo NO se toca, ni siquiera cuando un cambio posterior y
# ajeno a D3 mueve una de sus claves.
#
# Lo que se hace en su lugar es enumerar, una por una, las claves que otro cambio
# posterior movió, con su decisión asociada. Todo lo demás sigue exigido tal cual.
#
# FORMULACION_VOLTEO (aprobada 2026-09-19): el momento volcador pasó a incluir el término
# `P·offset` de la columna descentrada. La zapata EXTERIOR de la conectada es de lindero y
# su carga corregida trae M = −P·offset, de modo que el momento neto respecto del
# centroide es nulo o residual: el volcamiento en X deja de tener demanda. El cambio es
# posterior a 5A, no lo produce D3 y su alcance está acotado a esa verificación.
# Diagnóstico en `docs/formulacion_volteo_analisis.md`.
EXCLUIDAS_FORMULACION_VOLTEO = frozenset({
    ("numeros", "exterior.stability.applicable"),
    ("numeros", "exterior.stability.overturning_x.FS_obtained"),
    ("numeros", "exterior.stability.overturning_x.N_total_kN"),
    ("numeros", "exterior.stability.overturning_x.applied_moment_kNm"),
    ("numeros", "exterior.stability.overturning_x.horizontal_lever_arm_m"),
    ("numeros", "exterior.stability.overturning_x.overturning_moment_kNm"),
    ("numeros", "exterior.stability.overturning_x.stabilizing_moment_kNm"),
    ("numeros", "traza[zap_ext/overturning_x].result_value"),
    ("estados", "exterior.overall_status"),
    ("estados", "exterior.stability.overturning_x.status"),
    ("estados", "traza[zap_ext/overturning_x].status"),
    ("referencias", "zap_ext/overturning_x"),
})

# AUDITORÍA NORMATIVA (2026-09-19): la cita de la premisa de TBD-C1.
# La entrada decía «Sin artículo», y era inexacto: E.060 §15.2.6 EXIGE evaluar el
# comportamiento de las vigas de conexión según su rigidez y la del conjunto
# suelo-cimentación. Lo que falta es el criterio con que responder, no la exigencia. La
# cita corregida lo dice, y la premisa sigue en NO VERIFICADO. Es contrato BLANDO
# (`referencias`) y ajeno a D3 por completo: no toca ningún número ni ningún estado.
EXCLUIDAS_AUDITORIA_CITAS = frozenset({
    ("referencias", "sistema/uniform_pressure_premise"),
    ("referencias", "sistema/rigid_body_premise"),
    # Misma auditoría: la prohibición de tracciones se citaba como «E.060 §15.2» y su
    # sección exacta es §15.2.3. El número no cambia; la cita, sí.
    ("referencias", "zap_ext/contact_pressure"),
    ("referencias", "zap_int/contact_pressure"),
})

# H6 (2026-09-20): E.050 art. 23.3 se verifica desde entonces en LAS TRES tipologías, de
# modo que las zapatas de la conectada emiten una entrada de traza que en 5A no existía.
#
# Esto NO es una dispensa de valor: ninguna clave de la referencia cambia de número ni de
# estado. Es una entrada AÑADIDA, y una adición no es un reordenamiento. Por eso se
# enumera aparte y se filtra solo de `traza.orden`, que es la única clave donde aparecer
# de nuevas tiene efecto. Si alguna vez moviera un valor, caería en el test de arriba.
ENTRADAS_NUEVAS_TRAS_5A = frozenset({
    "zap_ext/shape_ratio",
    "zap_int/shape_ratio",
    # H7 (2026-09-20): E.050 art. 23.1, Df/B <= 5, también en las tres tipologías.
    "zap_ext/shallow_foundation",
    "zap_int/shallow_foundation",
})

# E.060 §15.6.2 (2026-09-28, aprobado por el proyectista junto con su diff de baselines,
# `docs/freeze_desarrollo_columna_descentrada.md`): el desarrollo del acero de la zapata
# de LINDERO se mide ahora con la posición real de la columna, y los casos declaran gancho
# de 90° en la dirección de la viga. Cambian la longitud disponible, la ld (con gancho) y la
# traza de desarrollo de la zapata exterior; ni el reparto, ni la viga, ni las presiones, ni
# la zapata interior, que es lo que esta referencia protege. Acotada por
# `test_la_dispensa_de_desarrollo_esta_acotada`.
EXCLUIDAS_DESARROLLO_COLUMNA_DESCENTRADA = frozenset({
    ("numeros", "exterior.development_x.deficit_m"),
    ("numeros", "exterior.development_x.hook_result"),
    ("numeros", "exterior.development_x.ld_available_m"),
    ("numeros", "exterior.development_x.ld_required_m"),
    ("numeros", "exterior.development_x.uses_hook"),
    ("numeros", "exterior.development_x.utilization"),
    ("numeros", "exterior.rebar_geometry.layer_x.available_development_length_m"),
    ("numeros", "exterior.rebar_geometry.layer_x.cantilever_m"),
    ("numeros", "exterior.rebar_geometry.layer_x.has_hook"),
    ("numeros", "exterior.rebar_options_x[0].ld_available_m"),
    ("numeros", "exterior.rebar_options_x[0].ld_required_m"),
    ("numeros", "exterior.rebar_options_x[1].ld_available_m"),
    ("numeros", "exterior.rebar_options_x[1].ld_required_m"),
    ("numeros", "traza[zap_ext/development_x].result_value"),
    ("numeros", "traza[zap_ext/rebar_options_development_x].result_value"),
    ("referencias", "zap_ext/development_x"),
})

DISPENSADAS = (
    EXCLUIDAS_FORMULACION_VOLTEO | EXCLUIDAS_AUDITORIA_CITAS | EXCLUIDAS_DESARROLLO_COLUMNA_DESCENTRADA
)


def test_la_dispensa_de_desarrollo_esta_acotada():
    """Solo el desarrollo del acero de la zapata EXTERIOR: ningún estado, nada del reparto,
    de la viga, de las presiones ni de la zapata interior."""
    for seccion, clave in EXCLUIDAS_DESARROLLO_COLUMNA_DESCENTRADA:
        assert seccion in ("numeros", "referencias"), (seccion, clave)
        assert clave.startswith((
            "exterior.development_", "exterior.rebar_geometry.", "exterior.rebar_options_",
            "traza[zap_ext/development_", "traza[zap_ext/rebar_options_development_",
            "zap_ext/development_",
        )), clave


@pytest.mark.parametrize("nombre", CORREGIDOS)
def test_D3_no_mueve_zapatas_ni_reparto(nombre):
    """Toda clave de la lista positiva —zapatas, reparto, geometría y traza del sistema
    salvo el diagrama de la viga— debe valer lo mismo que ANTES de 5A.

    La lista se fijó antes de implementar y se guardó junto con los valores. Las únicas
    claves dispensadas son las de `EXCLUIDAS_FORMULACION_VOLTEO`, cada una con su
    justificación; el archivo de referencia no se regenera."""
    ref = _referencia()[nombre]
    _, r = _resolver_caso(nombre)
    actual = snapshot_connected(r)

    for seccion in ("numeros", "estados", "referencias"):
        for clave, valor in ref[seccion].items():
            if clave == "traza.orden":
                continue  # se contrasta aparte, filtrado
            if (seccion, clave) in DISPENSADAS:
                continue
            assert actual[seccion].get(clave, "<AUSENTE>") == valor, (
                f"{nombre}: «{clave}» cambió de {valor!r} a "
                f"{actual[seccion].get(clave, '<AUSENTE>')!r}. D3 no debía tocarla."
            )


def test_la_dispensa_de_formulacion_volteo_esta_acotada():
    """Una dispensa sin límite acaba tapando cualquier regresión.

    `FORMULACION_VOLTEO` movió NÚMEROS y ESTADOS, que son contrato duro, de modo que su
    dispensa es la que hay que acotar con más severidad: toda clave tiene que pertenecer al
    volcamiento en X de la zapata exterior —o ser su consecuencia directa,
    `exterior.overall_status`— y ninguna puede tocar el reparto, la viga, la presión de
    contacto ni la zapata interior, que es lo que esta referencia existe para proteger."""
    propias = {
        "exterior.overall_status",
        "exterior.stability.applicable",
        "traza[zap_ext/overturning_x].result_value",
        "traza[zap_ext/overturning_x].status",
        "zap_ext/overturning_x",
    }
    for seccion, clave in EXCLUIDAS_FORMULACION_VOLTEO:
        assert seccion in ("numeros", "estados", "referencias")
        assert clave.startswith("exterior.stability.overturning_x.") or clave in propias, clave

    prohibido = ("interior", "viga", "beam", "contact_pressure", "punching", "flexure",
                 "P_ext_corrected", "P_int_corrected")
    for _, clave in EXCLUIDAS_FORMULACION_VOLTEO:
        assert not any(p in clave for p in prohibido), clave


def test_la_dispensa_de_la_auditoria_de_citas_es_solo_de_contrato_blando():
    """La otra dispensa se acota de otra manera, y más fuerte: **solo `referencias`**.

    Corregir una cita —«E.060 §15.2» → «§15.2.3», «Sin artículo» → «§15.2.6»— es
    exactamente para lo que existe el contrato blando. Que toque la presión de contacto o
    la zapata interior da igual mientras no mueva un número ni un estado: si lo hiciera, ya
    no sería una corrección de cita y esta dispensa no la ampararía."""
    for seccion, clave in EXCLUIDAS_AUDITORIA_CITAS:
        assert seccion == "referencias", (seccion, clave)
    # Y no se solapan: cada clave pertenece a una sola dispensa, con su justificación.
    assert not (EXCLUIDAS_FORMULACION_VOLTEO & EXCLUIDAS_AUDITORIA_CITAS)
    assert not (EXCLUIDAS_DESARROLLO_COLUMNA_DESCENTRADA & (EXCLUIDAS_FORMULACION_VOLTEO | EXCLUIDAS_AUDITORIA_CITAS))
    assert len(DISPENSADAS) == (
        len(EXCLUIDAS_FORMULACION_VOLTEO) + len(EXCLUIDAS_AUDITORIA_CITAS)
        + len(EXCLUIDAS_DESARROLLO_COLUMNA_DESCENTRADA)
    )


def test_la_dispensa_no_se_ha_quedado_obsoleta():
    """Si un cambio posterior devolviera una clave dispensada a su valor de antes de 5A,
    la dispensa sobraría y debe retirarse. Se exige que cada una siga siendo necesaria en
    al menos un caso: una lista de excepciones que nadie poda deja de ser una lista."""
    necesarias = set()
    for nombre in CORREGIDOS:
        ref = _referencia()[nombre]
        _, r = _resolver_caso(nombre)
        actual = snapshot_connected(r)
        for seccion, clave in DISPENSADAS:
            if clave in ref[seccion] and actual[seccion].get(clave, "<AUSENTE>") != ref[seccion][clave]:
                necesarias.add((seccion, clave))
    sobrantes = DISPENSADAS - necesarias
    assert not sobrantes, f"Dispensas que ya no hacen falta: {sorted(sobrantes)}"


@pytest.mark.parametrize("nombre", CORREGIDOS)
def test_D3_no_cambia_el_orden_de_la_traza_fuera_de_la_viga(nombre):
    """`traza.orden` cambia en Z12 y Z14, y el motivo está acotado: con el cortante
    corregido la viga deja de exigir estribos por cálculo y su propia entrada
    `viga/beam_stirrup_spacing` desaparece. Lo que se exige aquí es la afirmación
    física exacta: el orden de todas las entradas que NO son de la viga es idéntico."""
    antes = [k for k in _referencia()[nombre]["numeros"]["traza.orden"].split("|")
             if not _es_de_viga(k)]
    _, r = _resolver_caso(nombre)
    despues = [
        trace_key(e) for e in r.trace.entries
        if not _es_de_viga(trace_key(e))
        and trace_key(e) not in ENTRADAS_NUEVAS_TRAS_5A
    ]
    assert despues == antes


def test_las_entradas_nuevas_existen_de_verdad_y_son_solo_adiciones():
    """La lista de adiciones no puede ser una puerta trasera.

    Se exige lo contrario de lo habitual: que cada entrada enumerada **esté** hoy en la
    traza y **no estuviera** en la referencia. Una que ya existiera antes de 5A sería un
    reordenamiento disfrazado; una que no exista hoy es una lista sin podar."""
    ref = _referencia()
    for nombre in CORREGIDOS:
        _, r = _resolver_caso(nombre)
        hoy = {trace_key(e) for e in r.trace.entries}
        antes = set(ref[nombre]["numeros"]["traza.orden"].split("|"))
        for clave in ENTRADAS_NUEVAS_TRAS_5A:
            assert clave in hoy, f"{nombre}: «{clave}» ya no se emite; poda la lista."
            assert clave not in antes, f"{nombre}: «{clave}» ya existía antes de 5A."


def test_la_referencia_se_extrajo_antes_de_5A():
    """La referencia declara de dónde viene y con qué lista de claves. Un archivo de
    referencia sin procedencia no demuestra nada."""
    ref = _referencia()
    assert "a52f813b1e64806598c31fbd" in ref["_descripcion"]
    assert set(CORREGIDOS) <= set(ref)
