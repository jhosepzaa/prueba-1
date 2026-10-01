"""Correcciones normativas incorporadas en la Fase 1A.

Las tres provienen de la revisión contra fuente primaria de E.050, E.060 y E.030:

  1. E.050 art. 26.2 — Df >= 0,80 m, salvo cimentación sobre roca. No se verificaba.
  2. E.030 art. 64.2 — FS de volteo >= 1,20 para sismo. El motor calculaba el FS pero
     lo reportaba NO VERIFICADO por no conocer el criterio, que sí existía.
  3. E.060 §9.3.2 — los factores φ se citaban como §9.4, que es otra sección
     ("Resistencia mínima del concreto estructural").
"""

from __future__ import annotations

import pytest

from engine.codes.peru.e060_concrete import E060ConcreteCode
from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.domain.soil import PressureBasis, SoilProfile
from engine.foundation.depth_solver import evaluate_candidate
from engine.results.status import CheckStatus
from engine.soil.contact_pressure import KernCheckModel
from engine.soil.foundation_depth import MIN_FOUNDATION_DEPTH_M, check_foundation_depth
from engine.soil.stability import E030_FS_OVERTURNING_SEISMIC, check_stability
from tests.freeze.cases import COLUMN_40x40, CONCRETE_21, DEPTH_PARAMS, STEEL_420

CODE = E060ConcreteCode()
CONTACT = KernCheckModel()


def _soil(Df_m: float, *, rock: bool = False, fs_over: float | None = None) -> SoilProfile:
    return SoilProfile(
        qadm_kPa=250.0, pressure_basis=PressureBasis.BRUTA, gamma_kNm3=18.0, Df_m=Df_m,
        founded_on_rock=rock, FS_overturning_required=fs_over,
        source_notes="Caso de prueba.",
    )


def _loads(*, seismic: bool, Hx: float = 0.0, Mx: float = 0.0) -> LoadCaseSet:
    return LoadCaseSet(
        service=[
            LoadCombination(
                name="S1", type=LoadCombinationType.SERVICIO, P_kN=600.0,
                Mx_kNm=Mx, Hx_kN=Hx, includes_seismic_loads=seismic,
            )
        ],
        factored=[
            LoadCombination(
                name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=840.0,
                Mx_kNm=Mx * 1.4, Hx_kN=Hx * 1.4, includes_seismic_loads=seismic,
            )
        ],
    )


def _evaluate(soil: SoilProfile, loads: LoadCaseSet):
    return evaluate_candidate(
        B_m=2.6, L_m=2.6, h_m=0.60, column=COLUMN_40x40, soil=soil,
        concrete=CONCRETE_21, steel=STEEL_420, load_case_set=loads,
        code=CODE, contact_model=CONTACT, depth_params=DEPTH_PARAMS,
    )


# =========================================================================
# 1. E.050 art. 26.2 — profundidad mínima de cimentación
# =========================================================================

def test_el_minimo_es_el_valor_literal_de_la_norma():
    assert MIN_FOUNDATION_DEPTH_M == 0.80


@pytest.mark.parametrize("Df", [0.80, 1.00, 1.50, 3.00])
def test_profundidad_suficiente_cumple(Df: float):
    r = check_foundation_depth(Df, founded_on_rock=False)
    assert r.status is CheckStatus.PASS
    assert r.Df_min_required_m == 0.80


@pytest.mark.parametrize("Df", [0.20, 0.50, 0.79])
def test_profundidad_insuficiente_falla(Df: float):
    r = check_foundation_depth(Df, founded_on_rock=False)
    assert r.status is CheckStatus.FAIL
    assert "E.050 art. 26.2" in r.code_reference


def test_el_borde_exacto_de_080_cumple():
    """0,80 m es «no menor de 0,80»: el valor exacto CUMPLE. Un error de signo aquí
    rechazaría diseños válidos."""
    assert check_foundation_depth(0.80, founded_on_rock=False).status is CheckStatus.PASS


def test_solo_la_roca_exime_del_minimo():
    """Única excepción del art. 26.2. Y la declara el usuario: el motor no la deduce."""
    r = check_foundation_depth(0.40, founded_on_rock=True)
    assert r.status is CheckStatus.INFO
    assert r.Df_min_required_m is None
    assert "roca" in r.message.lower()


def test_la_roca_no_se_supone_nunca():
    """El default debe ser la rama ESTRICTA: no suponer roca."""
    assert _soil(1.0).founded_on_rock is False


def test_df_insuficiente_descarta_el_candidato_con_motivo_explicito():
    cand = _evaluate(_soil(0.50), _loads(seismic=False))
    entrada = cand.trace.by_id("foundation_depth")
    assert entrada is not None and entrada.status is CheckStatus.FAIL
    assert cand.overall_status is CheckStatus.FAIL
    assert any("0,80" in r or "0.80" in r for r in cand.discard_reasons)


def test_df_insuficiente_no_se_arregla_cambiando_la_geometria():
    """Es un requisito sobre un DATO DE ENTRADA. Ninguna geometría lo corrige, y el
    motivo debe ser el mismo en todas."""
    soil = _soil(0.50)
    motivos = set()
    for B, h in ((2.0, 0.40), (3.0, 0.60), (4.0, 0.90)):
        cand = evaluate_candidate(
            B_m=B, L_m=B, h_m=h, column=COLUMN_40x40, soil=soil,
            concrete=CONCRETE_21, steel=STEEL_420, load_case_set=_loads(seismic=False),
            code=CODE, contact_model=CONTACT, depth_params=DEPTH_PARAMS,
        )
        assert cand.trace.by_id("foundation_depth").status is CheckStatus.FAIL
        motivos.add(cand.trace.by_id("foundation_depth").equation_substituted)
    assert len(motivos) == 1, "El motivo no debe depender de la geometría"


def test_df_suficiente_no_altera_el_resto():
    """La verificación es aditiva: no debe cambiar ningún otro estado."""
    cand = _evaluate(_soil(1.20), _loads(seismic=False))
    assert cand.trace.by_id("foundation_depth").status is CheckStatus.PASS
    assert cand.trace.by_id("foundation_depth").code_name == "E.050"


# =========================================================================
# 2. E.030 art. 64.2 — FS de volteo en sismo
# =========================================================================

def test_el_fs_de_la_norma_se_conserva_aunque_el_programa_adopte_otro():
    """D10-2b no borra el valor normativo: lo conserva para poder citarlo y para dejar ver
    que el criterio adoptado es más estricto."""
    from engine.soil.stability import PROGRAM_FS_OVERTURNING_SEISMIC

    assert E030_FS_OVERTURNING_SEISMIC == 1.20, "Valor literal de E.030 art. 64.2"
    assert PROGRAM_FS_OVERTURNING_SEISMIC == 1.50, "Criterio adoptado por el proyecto"


def test_combinacion_sismica_exige_el_fs_adoptado_sin_atribuirselo_a_la_norma():
    """ACTUALIZADO en D10-2b. E.030 art. 64.2 exige 1,20; el proyecto adopta 1,50. La
    referencia tiene que decir las dos cosas: cuál es el valor de la norma y que 1,50 es
    criterio del programa, más estricto."""
    st = check_stability(
        _loads(seismic=True, Hx=40.0, Mx=120.0), _soil(1.2), 150.0, 2.6, 2.6, 0.60
    )
    assert st.overturning_x.FS_required == pytest.approx(1.50)
    ref = st.overturning_x.code_reference
    assert "criterio del programa (D10-2b)" in ref
    assert "E.030 art. 64.2" in ref and "1,20" in ref
    assert "más estricto" in ref
    # Fase 10B: con combinaciones directas un cumplimiento queda NO VERIFICADO (E.020 20.1).
    assert st.overturning_x.status in (CheckStatus.NOT_VERIFIED, CheckStatus.FAIL)


def test_combinacion_sin_sismo_coincide_con_e020_y_lo_dice():
    """E.030 art. 64 habla del volteo QUE PRODUCE UN SISMO y no se extiende al volteo no
    sísmico. Ahí el criterio adoptado (1,50) COINCIDE con E.020 art. 21, y la referencia lo
    dice así en vez de atribuirle el valor a E.030."""
    st = check_stability(
        _loads(seismic=False, Hx=40.0, Mx=120.0), _soil(1.2), 150.0, 2.6, 2.6, 0.60
    )
    assert st.overturning_x.FS_required == pytest.approx(1.50)
    ref = st.overturning_x.code_reference
    assert "E.020 art. 21" in ref and "coincide" in ref
    assert "E.030" not in ref
    assert "E.030" not in st.overturning_x.code_reference


def test_lo_declarado_por_el_proyectista_manda_sobre_el_default():
    st = check_stability(
        _loads(seismic=True, Hx=40.0, Mx=120.0), _soil(1.2, fs_over=2.0), 150.0, 2.6, 2.6, 0.60
    )
    assert st.overturning_x.FS_required == pytest.approx(2.0)
    assert "E.030" not in st.overturning_x.code_reference


def test_un_volteo_sismico_insuficiente_falla():
    loads = LoadCaseSet(
        service=[
            LoadCombination(
                name="S1", type=LoadCombinationType.SERVICIO, P_kN=100.0,
                Mx_kNm=400.0, Hx_kN=200.0, includes_seismic_loads=True,
            )
        ],
        factored=[
            LoadCombination(
                name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=140.0,
                Mx_kNm=560.0, Hx_kN=280.0, includes_seismic_loads=True,
            )
        ],
    )
    st = check_stability(loads, _soil(1.2), 100.0, 2.0, 2.0, 0.50)
    assert st.overturning_x.status is CheckStatus.FAIL
    assert st.overturning_x.FS_obtained < 1.20


def test_una_combinacion_sin_criterio_no_queda_tapada_por_otra_que_cumple():
    """Regresión: si se eligiera la gobernante solo por el FS más bajo, una
    combinación sísmica holgada podría reportarse PASS y dejar invisible una
    combinación sin sismo que nadie puede juzgar."""
    loads = LoadCaseSet(
        service=[
            # Sísmica muy holgada: FS altísimo, cumpliría 1,20 sin problema.
            LoadCombination(
                name="S_sismo", type=LoadCombinationType.SERVICIO, P_kN=2000.0,
                Mx_kNm=10.0, includes_seismic_loads=True,
            ),
            # Sin sismo y ajustada: no hay criterio normativo que aplicarle.
            LoadCombination(
                name="S_gravedad", type=LoadCombinationType.SERVICIO, P_kN=300.0,
                Mx_kNm=250.0, includes_seismic_loads=False,
            ),
        ],
        factored=[
            LoadCombination(
                name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=2800.0, Mx_kNm=14.0
            )
        ],
    )
    st = check_stability(loads, _soil(1.2), 150.0, 2.6, 2.6, 0.60)
    assert st.overturning_x.status is CheckStatus.NOT_VERIFIED
    assert st.overturning_x.governing_combo == "S_gravedad"


def test_la_interpretacion_de_e030_queda_declarada_en_la_traza():
    """E.030 art. 64 dice «toda estructura y su cimentación». Llevarlo al volteo de
    una zapata aislada es interpretación, y debe verse."""
    cand = _evaluate(_soil(1.2), _loads(seismic=True, Hx=40.0, Mx=120.0))
    entrada = cand.trace.by_id("overturning_x")
    assert entrada.code_name == "E.030"
    texto = " ".join(entrada.hypotheses)
    assert "INTERPRETACIÓN" in texto
    assert "art. 29" in texto, "Debe constar que el FS se calcula sin la reducción de 0,8"


# =========================================================================
# 3. E.060 §9.3.2 — cita de los factores φ
# =========================================================================

def test_los_phi_citan_la_seccion_correcta():
    phi = CODE.phi_factors()
    assert phi.code_reference == "E.060 §9.3.2"
    assert (phi.flexion, phi.cortante) == (0.90, 0.85), "Los VALORES no cambian"


def test_el_minimo_de_fc_sigue_citando_9_4():
    """§9.4 sí es la sección de la resistencia mínima del concreto: esa cita era
    correcta y no debe 'corregirse' por arrastre."""
    valor, referencia = CODE.fc_min_MPa()
    assert valor == 17.0
    assert referencia == "E.060 §9.4"
