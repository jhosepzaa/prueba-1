"""Fase 9b — vano libre físico de la viga y geometría de las métricas de viga.

- `beam_span_m = max(f_i − L1, 0)` en todos los modelos. Hasta 9b valía s_corte − L1, o la
  distancia entre ejes en PAR_PURO.
- Volumen de viga = vano libre + lo que sobresale de cada zapata. Lo que queda dentro de
  una zapata ya es volumen de esa zapata.
- Sin z_b declarada, la métrica adopta z_b = 0 y lo traza como hipótesis.
- Acero longitudinal sobre c_i − c_e, sin anclajes ni estribos.

Los valores esperados están calculados a mano a partir de los datos de cada caso (ver
`tests/freeze/cases.py`), sin llamar al código que se prueba.
"""

import pytest
from fastapi.testclient import TestClient

from engine.codes.peru.e060_concrete import E060ConcreteCode
from engine.foundation.connected_solver import solve_connected_footing
from engine.optimization.connected_metrics import (
    BEAM_METRIC_SOFFIT_HYPOTHESIS,
    BEAM_METRIC_STEEL_HYPOTHESIS,
    beam_volume_breakdown,
    compute_connected_metrics,
)
from engine.optimization.metrics import STEEL_DENSITY_KGM3, compute_metrics
from engine.soil.contact_pressure import KernCheckModel
from tests.freeze.cases import CONNECTED_CASES

B_VIGA, H_VIGA = 0.35, 1.20


def _caso(nombre: str):
    return next(c for c in CONNECTED_CASES if c.name == nombre)


def _resolver(nombre: str, layout=None):
    c = _caso(nombre)
    return solve_connected_footing(
        layout or c.build_layout(), c.geometry, soil=c.soil, concrete=c.concrete, steel=c.steel,
        code=E060ConcreteCode(), contact_model=KernCheckModel(), depth_params=c.depth_params,
    )


def _volumen_a_mano(c_e, L1, f_i, c_i, h_e, h_i, z_b=0.0):
    """Ecuaciones de 9b escritas de nuevo, con la sección de la viga de los casos."""
    z_t = z_b + H_VIGA
    t_e = max(0.0, min(z_t, h_e) - max(z_b, 0.0))
    t_i = max(0.0, min(z_t, h_i) - max(z_b, 0.0))
    return (
        B_VIGA * H_VIGA * (f_i - L1)
        + B_VIGA * (H_VIGA - t_e) * (L1 - c_e)
        + B_VIGA * (H_VIGA - t_i) * (c_i - f_i)
    )


# (caso, c_e, L1, f_i, c_i, h_e, h_i, vano, volumen de viga, longitud de acero)
#   c_e = a + b_col/2 · L1 = longitud de la zapata exterior · f_i = s_corte − L_int/2 ·
#   c_i = s_corte − b_col/2. Columnas de 0,50 m.
ESPERADOS = [
    # a = 0,25; S = 6,00 → s_corte 6,25; zapatas 2,00 y 2,20 m; h = 0,90
    ("Z1_articulado_equilibrio", 0.50, 2.00, 5.15, 6.00, 0.90, 0.90, 3.15, 1.56975, 5.50),
    ("Z2_articulado_par_puro", 0.50, 2.00, 5.15, 6.00, 0.90, 0.90, 3.15, 1.56975, 5.50),
    ("Z3_cuerpo_rigido_equilibrio", 0.50, 2.00, 5.15, 6.00, 0.90, 0.90, 3.15, 1.56975, 5.50),
    # holgura al lindero: a = 0,40
    ("Z6_holgura_al_lindero_no_nula", 0.65, 2.00, 5.30, 6.15, 0.90, 0.90, 3.30, 1.617, 5.50),
    # Aragón P1: zapata exterior 1,40 m, interior 3,20 m, h = 0,60
    ("Z11_aragon_p1_articulado", 0.50, 1.40, 4.65, 6.00, 0.60, 0.60, 3.25, 1.8375, 5.50),
    # Aragón P2: a = 0,40, S = 6,50, zapata exterior 2,30 m, interior 6,70 m, h = 0,60
    ("Z12_aragon_p2_cuerpo_rigido", 0.65, 2.30, 3.55, 6.65, 0.60, 0.60, 1.25, 1.5225, 6.00),
    # PAR_PURO con peso EXPLICITO y z_b = 0 declarada
    ("Z15_par_puro_con_peso_propio_de_viga_explicito", 0.50, 2.00, 5.15, 6.00, 0.90, 0.90, 3.15, 1.56975, 5.50),
]


@pytest.mark.parametrize("nombre,c_e,L1,f_i,c_i,h_e,h_i,vano,volumen,largo_acero", ESPERADOS)
def test_vano_volumen_y_acero_contra_calculo_a_mano(
    nombre, c_e, L1, f_i, c_i, h_e, h_i, vano, volumen, largo_acero
):
    r = _resolver(nombre)
    ax = r.beam_axis
    assert (ax.s_exterior_face_m, ax.s_span_start_m, ax.s_span_end_m, ax.s_interior_face_m) == (
        pytest.approx(c_e), pytest.approx(L1), pytest.approx(f_i), pytest.approx(c_i)
    )
    assert r.beam_span_m == pytest.approx(vano)
    assert r.beam_span_m == pytest.approx(f_i - L1)

    v = beam_volume_breakdown(r)
    assert v.total_m3 == pytest.approx(volumen)
    assert v.total_m3 == pytest.approx(_volumen_a_mano(c_e, L1, f_i, c_i, h_e, h_i))
    assert v.steel_length_m == pytest.approx(largo_acero)


def test_el_vano_no_depende_del_modelo_ni_del_reparto():
    """Z1 (EQUILIBRIO), Z2 (PAR_PURO) y Z3 (CUERPO_RIGIDO) tienen la misma geometría: el vano
    y la métrica de la viga son idénticos. Antes de 9b, Z2 medía 6,00 m desde el eje."""
    resultados = [_resolver(n) for n in (
        "Z1_articulado_equilibrio", "Z2_articulado_par_puro", "Z3_cuerpo_rigido_equilibrio"
    )]
    assert resultados[0].beam_axis == resultados[1].beam_axis == resultados[2].beam_axis
    assert len({round(beam_volume_breakdown(r).total_m3, 12) for r in resultados}) == 1
    par_puro = resultados[1]
    assert par_puro.beam_span_m < par_puro.statics[0].S_m - 1.0


@pytest.mark.parametrize("nombre", [c.name for c in CONNECTED_CASES if c.name not in (
    "Z4_cuerpo_rigido_par_puro", "Z9_despegue_rechaza_la_terna",
    "Z10_geometria_imposible_huellas_solapadas",
)])
def test_sin_doble_conteo_y_metricas_aditivas(nombre):
    """Viga atribuida + viga dentro de las zapatas = prisma b·h entre caras de columna, y
    las métricas del sistema son zapatas completas + viga atribuida."""
    c = _caso(nombre)
    r = _resolver(nombre)
    v = beam_volume_breakdown(r)
    ax = r.beam_axis
    prisma = r.beam.b_m * r.beam.h_m * (ax.s_interior_face_m - ax.s_exterior_face_m)
    assert v.total_m3 + v.exterior_inside_m3 + v.interior_inside_m3 == pytest.approx(prisma, rel=1e-12)
    for parte in (v.span_m3, v.exterior_inside_m3, v.exterior_above_m3,
                  v.interior_inside_m3, v.interior_above_m3):
        assert parte >= 0.0

    cover = 0.075
    m = compute_connected_metrics(r, c.soil.Df_m, cover)
    m_ext = compute_metrics(r.exterior, c.soil.Df_m, cover)
    m_int = compute_metrics(r.interior, c.soil.Df_m, cover)
    assert m.concrete_volume_m3 == pytest.approx(
        m_ext.concrete_volume_m3 + m_int.concrete_volume_m3 + v.total_m3, rel=1e-12
    )
    As = r.beam.As_negative_m2 + r.beam.As_positive_m2
    assert m.steel_mass_kg == pytest.approx(
        m_ext.steel_mass_kg + m_int.steel_mass_kg
        + As * (ax.s_interior_face_m - ax.s_exterior_face_m) * STEEL_DENSITY_KGM3,
        rel=1e-12,
    )


def test_z_b_no_declarada_se_adopta_cero_y_se_traza():
    v = beam_volume_breakdown(_resolver("Z1_articulado_equilibrio"))
    assert v.soffit_declared is False
    assert v.soffit_above_base_m == 0.0
    assert BEAM_METRIC_SOFFIT_HYPOTHESIS in v.hypotheses
    assert BEAM_METRIC_STEEL_HYPOTHESIS in v.hypotheses


def test_z_b_declarada_se_usa_y_no_se_declara_hipotesis():
    """Z8 declara z_b = 0 (mismo volumen que la hipótesis). Con z_b = 0,30 la franja dentro de
    la zapata baja a 0,90 − 0,30 = 0,60 m y sobresale 0,60 m sobre cada huella."""
    z8 = beam_volume_breakdown(_resolver("Z8_peso_propio_de_viga_explicito"))
    assert z8.soffit_declared is True
    assert BEAM_METRIC_SOFFIT_HYPOTHESIS not in z8.hypotheses
    assert z8.total_m3 == pytest.approx(1.56975)

    layout = _caso("Z8_peso_propio_de_viga_explicito").build_layout()
    alto = layout.model_copy(update={
        "beam": layout.beam.model_copy(update={"soffit_above_base_m": 0.30})
    })
    v = beam_volume_breakdown(_resolver("Z8_peso_propio_de_viga_explicito", alto))
    # 0,35·1,20·3,15 + 0,35·0,60·1,50 + 0,35·0,60·0,85
    assert v.total_m3 == pytest.approx(1.323 + 0.315 + 0.1785)
    assert v.soffit_above_base_m == 0.30


def test_la_geometria_es_la_misma_que_la_del_peso_propio():
    """La viga del peso propio (9a) y la de las métricas (9b) son el mismo cuerpo."""
    r = _resolver("Z8_peso_propio_de_viga_explicito")
    bw = r.statics[0].beam_self_weight_breakdown
    ax = r.beam_axis
    assert (bw.s_exterior_face_m, bw.s_span_start_m, bw.s_span_end_m, bw.s_interior_face_m) == (
        ax.s_exterior_face_m, ax.s_span_start_m, ax.s_span_end_m, ax.s_interior_face_m
    )
    assert bw.soffit_above_base_m == ax.soffit_above_base_m


def test_el_informe_muestra_el_desglose_y_las_hipotesis_de_la_metrica():
    from api.server import app
    from tests.test_connected_presentation_phase4e import _peticion

    r = TestClient(app).post("/api/report-connected", json=_peticion())
    assert r.status_code == 200, r.text
    html = r.text
    assert "Vano libre de la viga" in html
    assert "Concreto atribuido a la viga" in html
    assert "z_b no está declarada" in html
    assert "No incluye anclajes ni estribos" in html
