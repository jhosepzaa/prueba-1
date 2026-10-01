"""FASE 3 — Integración zapata combinada → motor de vigas (RETIRADA en la auditoría C-V).

ACTUALIZACIÓN C-V (2026-09-17)
==============================
La combinada dimensionaba estribos con `check_beam_shear` tras un FAIL del cortante longitudinal,
pero la entrada del concreto seguía en FAIL: los estribos no intervenían en la aceptación. Se
retiró esa llamada y el criterio quedó explícito como CONCRETO SOLO (ver
docs/auditoria_cv_cortante_longitudinal_combinada.md). Los tests que exigían la invocación se
sustituyeron por su inversa: la combinada NO llama al motor de vigas. Se conservan los que
protegen la unicidad del motor de cortante y la exención de §11.5.6.1(a), que siguen vigentes
para una futura implementación de Vc + Vs.

Texto original:

EL RIESGO QUE ESTOS TESTS CUBREN
================================
Cuando el concreto de una zapata combinada no basta para el cortante longitudinal,
la zapata puede llevar refuerzo de cortante: E.060 §11.12.1.1 remite el
comportamiento como viga de una zapata a §11.1–11.5. La tentación es escribir ahí
una segunda implementación de la ec. 11-15 «adaptada a zapatas».

Eso produciría dos motores de cortante que se separan con el tiempo: se corrige un
límite en uno y no en el otro, y nadie se entera hasta que los resultados discrepan.
Estos tests fijan que la combinada llama al MISMO `check_beam_shear` que la viga de
conexión, y lo demuestran de tres maneras independientes:

  1. Interceptando la función: si la combinada tuviera su propia copia, el espía no
     se dispararía.
  2. Comparando números: el resultado de la combinada debe coincidir dígito a dígito
     con el de llamar al motor de vigas a mano con los mismos datos.
  3. Comprobando que la ÚNICA diferencia es la bandera `is_slab_or_footing`, que
     activa la exención de §11.5.6.1(a) — y que esa exención NO se aplica a la viga
     de conexión, que no es losa ni zapata.
"""

from __future__ import annotations

import pytest

import engine.foundation.combined_solver as combined_solver
from engine.beam import beam_shear as beam_shear_module
from engine.beam.beam_shear import check_beam_shear
from engine.beam.connecting_beam import SeismicContext, design_connecting_beam
from engine.codes.peru.e060_concrete import E060ConcreteCode
from engine.domain.column import Column
from engine.domain.column_placement import ColumnPlacement
from engine.domain.combined_layout import ColumnOnFooting, CombinedFootingLayout
from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.domain.materials import MaterialConcrete, MaterialSteel
from engine.domain.soil import PressureBasis, SoilProfile
from engine.foundation.combined_solver import solve_combined_footing
from engine.reinforcement.face_reinforcement import TopCoverDeclaration
from engine.results.status import CheckStatus
from engine.soil.contact_pressure import FullContactModel

CODE = E060ConcreteCode()
COL = Column(shape="cuadrada", bx_m=0.50, by_m=0.50)
TAPA = TopCoverDeclaration(case="contacto_suelo_barras_pequenas")


def _col(label: str, x_desde_extremo: float, P: float, L_total: float):
    return ColumnOnFooting(
        label=label,
        placement=ColumnPlacement(column=COL, offset_x_m=x_desde_extremo - L_total / 2.0),
        loads=LoadCaseSet(
            service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=P)],
            factored=[
                LoadCombination(
                    name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=P * 1.4
                )
            ],
        ),
    )


def _resolver(h: float, P: float = 900.0, B: float = 8.0, L: float = 3.60, qadm: float = 400.0):
    layout = CombinedFootingLayout(
        B_m=B, L_m=L,
        columns=[_col("C1", 1.0, P, B), _col("C2", B - 1.0, P, B)],
    )
    return solve_combined_footing(
        layout, h,
        soil=SoilProfile(
            qadm_kPa=qadm, pressure_basis=PressureBasis.BRUTA, gamma_kNm3=18.0,
            Df_m=1.50, source_notes="prueba",
        ),
        concrete=MaterialConcrete(fc_MPa=21.0), steel=MaterialSteel(fy_MPa=420.0),
        code=CODE, contact_model=FullContactModel(), top_cover=TAPA,
    )


def _peralte_que_falla_por_cortante() -> float:
    """Busca un h con el que el cortante longitudinal resulte FAIL.

    Se busca en vez de fijarlo: un peralte escrito a mano dejaría de fallar si algún
    día cambia la geometría por defecto, y el test pasaría sin verificar nada."""
    for h_mm in range(300, 1300, 25):
        r = _resolver(h_mm / 1000.0)
        if r.shear_longitudinal.status is CheckStatus.FAIL:
            return h_mm / 1000.0
    pytest.skip("Ninguna geometría del barrido produce FAIL por cortante longitudinal")


# =========================================================================
# 1. La combinada NO llama al motor de vigas (criterio de concreto solo, C-V)
# =========================================================================

def test_cuando_el_concreto_basta_no_se_invoca_el_motor_de_vigas():
    """Condición de disparo: sin FAIL por cortante no hay refuerzo que dimensionar."""
    r = _resolver(1.20)
    assert r.shear_longitudinal.status is not CheckStatus.FAIL
    assert r.shear_reinforcement is None
    assert r.trace.by_id("shear_reinforcement") is None


def test_con_fail_de_cortante_la_combinada_no_invoca_el_motor_de_vigas(monkeypatch):
    """Inversa del test de la Fase 3: aunque el concreto no baste, no se dimensiona refuerzo.
    Se intercepta el motor de vigas en su módulo: no debe llamarse ni una vez."""
    h = _peralte_que_falla_por_cortante()
    llamadas: list[dict] = []
    original = beam_shear_module.check_beam_shear

    def espia(**kwargs):
        llamadas.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(beam_shear_module, "check_beam_shear", espia)
    r = _resolver(h)
    assert r.shear_longitudinal.status is CheckStatus.FAIL
    assert llamadas == []
    assert r.shear_reinforcement is None
    assert r.trace.by_id("shear_reinforcement") is None
    assert r.overall_status is CheckStatus.FAIL
    assert not hasattr(combined_solver, "check_beam_shear"), (
        "combined_solver no debe importar el motor de cortante con estribos mientras C-V sea "
        "criterio de concreto solo"
    )


def test_no_hay_una_segunda_implementacion_del_cortante_con_estribos():
    """La ecuación 11-15 y su cota de §11.5.7.9 solo pueden vivir en un sitio."""
    import inspect

    fuente = inspect.getsource(combined_solver)
    for prohibido in ("def check_beam_shear", "def _beam_shear", "Vs_max", "0.66 * math.sqrt"):
        assert prohibido not in fuente, (
            f"«{prohibido}» aparece en combined_solver: el cortante con estribos debe "
            f"resolverse en engine/beam/beam_shear.py y en ningún otro sitio."
        )


# =========================================================================
# 3. La única diferencia es la exención de §11.5.6.1(a)
# =========================================================================

def test_la_zapata_queda_exenta_del_refuerzo_minimo_y_la_viga_no():
    """§11.5.6.1(a) exime a losas y zapatas del refuerzo mínimo por cortante. Una
    viga de conexión NO está en esa lista, y tratarla como si lo estuviera la dejaría
    sin estribos donde la norma sí los exige."""
    datos = dict(Vu_kN=400.0, bw_m=3.60, h_m=0.60, d_m=0.50, fc_MPa=21.0, fyt_MPa=420.0)

    como_zapata = check_beam_shear(**datos, is_slab_or_footing=True)
    como_viga = check_beam_shear(**datos, is_slab_or_footing=False)

    # Lo que el concreto resiste es idéntico: la bandera no toca la ec. 11-3.
    assert como_zapata.Vc_kN == pytest.approx(como_viga.Vc_kN)
    assert como_zapata.Vs_required_kN == pytest.approx(como_viga.Vs_required_kN)
    # Y la diferencia está donde debe estar.
    assert como_zapata.av_min_exemption, "La zapata debe declarar qué exención aplica"
    assert "11.5.6.1" in como_zapata.av_min_exemption
    assert not como_viga.av_min_exemption, "La viga de conexión no está exenta"


def test_la_viga_de_conexion_usa_el_mismo_motor_sin_la_exencion():
    """Cierre del circuito: la viga de conexión también pasa por `check_beam_shear`,
    con la bandera en falso. Un solo motor, dos configuraciones declaradas."""
    r = design_connecting_beam(
        b_m=0.35, h_m=1.20, d_m=1.10, clear_span_m=5.50,
        Mu_negative_kNm=200.0, Mu_positive_kNm=100.0, Vu_kN=400.0,
        fc_MPa=21.0, fy_MPa=420.0, longitudinal_db_mm=25.4, sum_Pu_kN=1000.0,
        seismic=SeismicContext(qadm_kPa=200.0),
    )
    esperado = check_beam_shear(
        Vu_kN=400.0, bw_m=0.35, h_m=1.20, d_m=1.10,
        fc_MPa=21.0, fyt_MPa=420.0, is_slab_or_footing=False,
    )
    assert r.shear.equation_substituted == esperado.equation_substituted
    assert r.shear.Vs_required_kN == pytest.approx(esperado.Vs_required_kN, rel=1e-12)
    assert not r.shear.av_min_exemption
