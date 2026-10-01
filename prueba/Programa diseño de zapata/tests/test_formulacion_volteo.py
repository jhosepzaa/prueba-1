"""FORMULACION_VOLTEO — formulación común del momento volcador (aprobada 2026-09-19).

QUÉ CAMBIÓ Y POR QUÉ
====================
Hasta aquí la zapata aislada tomaba el momento volcador como `|M|` de la combinación,
sin el término `P·offset` de la columna descentrada, mientras la presión de contacto ya
usaba `ex = (M + P·offset)/(P + W)`. **La aislada era incoherente consigo misma**, y el
error iba en las dos direcciones:

  - INSEGURO en la zapata de lindero sin momento propio: el volcamiento se declaraba «no
    aplicable» mientras la presión veía la resultante fuera del núcleo;
  - FALSAMENTE CONSERVADOR en la zapata exterior de la conectada, donde el reparto centra
    la resultante —`M = −P·offset`— y el volcamiento publicaba un FS de 1,54 a 1,94, a un
    paso del mínimo, para una zapata sin demanda.

Desde FORMULACION_VOLTEO las tres tipologías usan

    M_volc = max(|M_total|, |M_estabilizante|) + |H|·h
    M_total = M + P·offset            M_estabilizante = Σ_estab (M_k + P_k·offset)

con UN solo ayudante, `engine.soil.stability.axis_moments_kNm`.

QUÉ ES QUÉ
==========
El término `P·offset` es ESTÁTICA: tomando momentos en la arista, el brazo real de la
carga de columna es `dim/2 − offset`. La ENVOLVENTE es un CRITERIO DEL PROGRAMA
(pendiente 7, opción B), no una exigencia normativa. Este archivo los prueba por
separado para que no se lean como una sola cosa.

Diagnóstico completo, ejemplos numéricos e impacto sobre los casos congelados en
`docs/formulacion_volteo_analisis.md` y `docs/freeze_formulacion_volteo.md`.
"""

import pytest

from engine.domain.column import Column
from engine.domain.column_placement import ColumnPlacement
from engine.domain.combined_layout import ColumnOnFooting, CombinedFootingLayout
from engine.domain.load_cases import (
    CombinationDefinition,
    LoadCase,
    LoadCaseKind,
    derive_load_case_set,
)
from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.domain.soil import PressureBasis, SoilProfile
from engine.foundation.combined_stability import check_combined_stability, resultants
from engine.results.status import CheckStatus
from engine.soil.eccentricity import compute_total_eccentricity
from engine.soil.stability import (
    MOMENT_NOISE_REL_TOL,
    axis_moments_kNm,
    check_stability,
    denoise_moment_kNm,
)

SERV = LoadCombinationType.SERVICIO
FACT = LoadCombinationType.FACTORIZADA
COL = Column(shape="cuadrada", bx_m=0.40, by_m=0.40)


def _suelo(fs_over=None, mu=None) -> SoilProfile:
    return SoilProfile(
        qadm_kPa=200.0, pressure_basis=PressureBasis.BRUTA, gamma_kNm3=18.0, Df_m=1.20,
        FS_overturning_required=fs_over, mu_friction_soil_concrete=mu,
    )


def _directo(P=500.0, **kw) -> LoadCaseSet:
    return LoadCaseSet(
        service=[LoadCombination(name="S1", type=SERV, P_kN=P, **kw)],
        factored=[LoadCombination(name="U1", type=FACT, P_kN=P * 1.4)],
    )


def _casos(P_cm: float, P_cv: float, **kw_cv) -> LoadCaseSet:
    """CM y CV por separado. Los momentos y fuerzas van en CV, que es el caso que NO
    estabiliza (E.020 art. 20.1)."""
    return derive_load_case_set(
        [
            LoadCase(name="CM", kind=LoadCaseKind.CM, P_kN=P_cm),
            LoadCase(name="CV", kind=LoadCaseKind.CV, P_kN=P_cv, **kw_cv),
        ],
        [
            CombinationDefinition(name="S1", type=SERV, factors={"CM": 1.0, "CV": 1.0}),
            CombinationDefinition(name="U1", type=FACT, factors={"CM": 1.4, "CV": 1.7}),
        ],
    )


def _pl(offset_x=0.0, offset_y=0.0) -> ColumnPlacement:
    return ColumnPlacement(column=COL, offset_x_m=offset_x, offset_y_m=offset_y)


# =========================================================================
# 1. El término P·offset es estática: reconstrucción a mano
# =========================================================================


def _con_momento_y_cortante(P_cm: float, M: float, H: float) -> LoadCaseSet:
    """Toda la carga en CM, con M y H en la misma combinación de servicio.

    Se arma a mano porque `_casos` pone M y H en el caso CV, y aquí interesa el caso
    límite en que TODA la carga estabiliza: así las dos lecturas de la envolvente
    coinciden y la ecuación que se reconstruye es una sola."""
    base = _casos(P_cm=P_cm, P_cv=0.0)
    comp = base.service[0].composition
    return base.model_copy(update={
        "service": [LoadCombination(
            name="S1", type=SERV, P_kN=P_cm, Mx_kNm=M, Hx_kN=H, composition=comp,
        )],
    })


def test_el_momento_volcador_es_el_de_la_arista_reconstruido_a_mano():
    """Reconstrucción INDEPENDIENTE, sin llamar al código que se prueba.

    CONVENCIÓN ADOPTADA. El momento de la carga descentrada se lleva al miembro
    VOLCADOR, y el estabilizador se mantiene en `N·dim/2`:

        FS = N·(dim/2) / (|M + P·offset| + |H|·h)

    NO es lo mismo que acortar el brazo de la carga —`(N·dim/2 − P·offset)/(|M| + |H|·h)`—.
    Un cociente no es invariante al pasar un término de un miembro al otro, y las dos
    escrituras dan números distintos: con los datos de este test, 2,612 frente a 7,119.
    La adoptada es la MÁS CONSERVADORA siempre que el FS de la otra supere 1, que es el
    caso normal, y es la única coherente con la presión de contacto, que reduce la misma
    resultante con `ex = (M + P·offset)/(P + W)`. Con H = 0 da además
    `FS = dim/(2·e)`, que es la relación de la que sale «resultante en el núcleo central
    ⇒ FS ≥ 3» invocada en el alcance de la combinada.

    Es una HIPÓTESIS DE MODELACIÓN declarada, no una exigencia normativa: ninguna fuente
    del proyecto prescribe cómo plantear el volcamiento de una zapata."""
    B, L, h, W = 3.00, 2.40, 0.70, 180.0
    P, M, H, off = 600.0, 90.0, 40.0, 0.55

    s = check_stability(
        _casos(P_cm=P, P_cv=0.0), _suelo(fs_over=1.5), W, B, L, h, _pl(offset_x=off)
    )
    # Sin momento de columna: el volcador es enteramente el término de excentricidad.
    assert s.overturning_x.applied_moment_kNm == pytest.approx(P * off, rel=1e-12)

    s2 = check_stability(
        _con_momento_y_cortante(P, M, H), _suelo(fs_over=1.5), W, B, L, h, _pl(offset_x=off)
    )
    n_esperada = P + W
    m_estab_a_mano = n_esperada * (B / 2.0)
    m_volc_a_mano = abs(M + P * off) + abs(H) * h
    fs_a_mano = m_estab_a_mano / m_volc_a_mano

    o = s2.overturning_x
    assert o.N_total_kN == pytest.approx(n_esperada, rel=1e-12)
    assert o.stabilizing_moment_kNm == pytest.approx(m_estab_a_mano, rel=1e-12)
    assert o.overturning_moment_kNm == pytest.approx(m_volc_a_mano, rel=1e-12)
    assert o.FS_obtained == pytest.approx(fs_a_mano, rel=1e-12)

    # Y la otra escritura, la del brazo acortado, daría otro número: la elección entre
    # las dos es una decisión, no una identidad algebraica.
    fs_brazo_acortado = (n_esperada * (B / 2.0) - P * off) / (abs(M) + abs(H) * h)
    assert fs_brazo_acortado == pytest.approx(7.11864406779661, rel=1e-12)
    assert o.FS_obtained < fs_brazo_acortado, "La convención adoptada es la más estricta"


def test_sin_fuerza_horizontal_el_FS_es_la_relacion_del_nucleo_central():
    """Comprobación cruzada de la convención: con H = 0 y toda la carga en CM,

        FS = N·(dim/2) / |M + P·offset| = dim / (2·e)

    de donde sale que una resultante en el borde del núcleo central (e = dim/6) da
    FS = 3. Es la relación que el alcance de la combinada invoca para no verificar el
    volcamiento cuando no hay fuerza horizontal; aquí se comprueba con números."""
    B, L, h, W = 3.00, 2.40, 0.70, 0.0
    P, off = 600.0, B / 6.0
    s = check_stability(
        _con_momento_y_cortante(P, 0.0, 0.0), _suelo(fs_over=1.5), W, B, L, h, _pl(offset_x=off)
    )
    assert s.overturning_x.FS_obtained == pytest.approx(3.0, rel=1e-12)


def test_con_la_columna_centrada_la_formulacion_se_reduce_a_la_anterior():
    """No regresión: `offset = 0` ⇒ `M_volc = |M| + |H|·h`, que es lo de siempre."""
    B, L, h, W = 2.50, 2.50, 0.60, 150.0
    sin_placement = check_stability(
        _directo(500.0, Mx_kNm=100.0, Hx_kN=50.0), _suelo(fs_over=1.5), W, B, L, h
    )
    concentrico = check_stability(
        _directo(500.0, Mx_kNm=100.0, Hx_kN=50.0), _suelo(fs_over=1.5), W, B, L, h, _pl()
    )
    assert sin_placement.overturning_x.applied_moment_kNm == pytest.approx(100.0)
    assert sin_placement.overturning_x.overturning_moment_kNm == pytest.approx(130.0)
    assert (
        concentrico.overturning_x.FS_obtained
        == pytest.approx(sin_placement.overturning_x.FS_obtained, rel=1e-15)
    )


def test_cada_eje_usa_su_propio_desplazamiento():
    """X toma `offset_x` y Y toma `offset_y`. Cruzarlos fue un defecto real de la Fase 1B
    en otros cálculos; aquí se cierra con números distintos en cada eje."""
    B, L, h, W = 3.00, 2.00, 0.50, 120.0
    s = check_stability(
        _directo(400.0, Hx_kN=10.0, Hy_kN=10.0), _suelo(fs_over=1.5), W, B, L, h,
        _pl(offset_x=0.60, offset_y=-0.30),
    )
    assert s.overturning_x.applied_moment_kNm == pytest.approx(400.0 * 0.60)
    assert s.overturning_y.applied_moment_kNm == pytest.approx(400.0 * 0.30)


# =========================================================================
# 2. Coherencia con la presión de contacto
# =========================================================================


def test_el_volcamiento_y_la_presion_usan_la_MISMA_excentricidad():
    """El defecto que FORMULACION_VOLTEO cerró: dos excentricidades para una resultante.

    `compute_total_eccentricity` reduce la resultante con `M + P·offset`; el volcamiento
    debe partir del mismo numerador. Se comprueba la identidad exacta
    `M_total = ex·(P + W)`."""
    B, L, h, W = 3.20, 2.60, 0.70, 200.0
    P, M, off = 700.0, 120.0, 0.45

    s = check_stability(
        _directo(P, Mx_kNm=M, Hx_kN=25.0), _suelo(fs_over=1.5), W, B, L, h, _pl(offset_x=off)
    )
    e = compute_total_eccentricity(P, W, M, 0.0, offset_x_m=off)
    assert s.overturning_x.applied_moment_total_kNm == pytest.approx(
        abs(e.ex_m) * (P + W), rel=1e-12
    )


def test_el_nucleo_central_no_cubre_la_omision():
    """El ejemplo numérico del diagnóstico: resultante DENTRO del núcleo y el volcamiento
    falla igualmente.

    B = L = 1,60 · h = 0,80 · CM = 300 · CV = 700 · offset = 0,264 · H = 200 · M = 0

        ex = 264/1067,58 = 0,2473 ≤ B/6 = 0,2667   → la presión de contacto PASA
        N_estab = 300 + 67,58 = 367,58 kN          (solo carga muerta, E.020 art. 20.1)
        M_estab = 367,58 · 0,80 = 294,06 kN·m
        M_volc(antes)  = |0| + 200·0,80 = 160,0    → FS = 1,838  PASA
        M_volc(ahora)  = 264 + 160     = 424,0     → FS = 0,694  FALLA

    Es la demostración de que la exigencia de núcleo central NO acotaba el volcamiento: el
    estabilizante solo cuenta la carga muerta y `H·h` no entra en el núcleo. Sí podía
    producirse un falso PASS."""
    B = L = 1.60
    h, W = 0.80, 67.58
    off, H = 0.264, 200.0

    e = compute_total_eccentricity(1000.0, W, 0.0, 0.0, offset_x_m=off)
    assert abs(e.ex_m) <= B / 6.0, "El ejemplo debe estar DENTRO del núcleo central"

    s = check_stability(
        _casos(P_cm=300.0, P_cv=700.0, Hx_kN=H), _suelo(fs_over=1.5), W, B, L, h,
        _pl(offset_x=off),
    )
    o = s.overturning_x
    assert o.N_total_kN == pytest.approx(367.58, rel=1e-9)
    assert o.stabilizing_moment_kNm == pytest.approx(294.064, rel=1e-6)
    assert o.overturning_moment_kNm == pytest.approx(424.0, rel=1e-9)
    assert o.FS_obtained == pytest.approx(0.69355, rel=1e-4)
    assert o.status is CheckStatus.FAIL

    # Y la formulación anterior habría dicho que cumple.
    fs_anterior = o.stabilizing_moment_kNm / (0.0 + H * h)
    assert fs_anterior == pytest.approx(1.8379, rel=1e-4)
    assert fs_anterior >= 1.5


# =========================================================================
# 3. La envolvente (criterio del programa, opción B)
# =========================================================================


def test_la_excentricidad_favorable_de_la_carga_viva_no_enmascara_el_volcamiento():
    """La lectura TOTAL puede ser MENOR que la estabilizante y subestimar el volcamiento.

    Se construye a propósito: la carga viva aporta un momento de signo contrario al
    término `P_CM·offset`, de modo que `|M_total| < |M_estabilizante|`. La envolvente toma
    la peor de las dos."""
    B, L, h, W = 3.00, 2.40, 0.60, 150.0
    off = 0.50
    # CM = 400 en x = +0,50 → momento +200. CV = 100 con Mx = −250 → total −50.
    loads = _casos(P_cm=400.0, P_cv=100.0, Mx_kNm=-250.0, Hx_kN=20.0)
    s = check_stability(loads, _suelo(fs_over=1.5), W, B, L, h, _pl(offset_x=off))
    o = s.overturning_x

    assert o.applied_moment_total_kNm == pytest.approx(abs(-250.0 + 500.0 * off), rel=1e-12)
    assert o.applied_moment_dead_kNm == pytest.approx(abs(400.0 * off), rel=1e-12)
    assert o.applied_moment_dead_kNm > o.applied_moment_total_kNm
    assert o.envelope_reading == "ESTABILIZANTE"
    assert o.applied_moment_kNm == pytest.approx(o.applied_moment_dead_kNm, rel=1e-12)
    assert "ESTABILIZANTE" in o.equation_substituted


def test_sin_composicion_las_dos_lecturas_coinciden():
    """Modo directo: no se sabe qué parte es carga muerta, de modo que la envolvente no
    puede aportar nada y las dos lecturas son la misma. El resultado, además, no puede
    afirmarse (E.020 art. 20.1)."""
    s = check_stability(
        _directo(500.0, Mx_kNm=100.0, Hx_kN=30.0), _suelo(fs_over=1.5), 150.0,
        2.50, 2.50, 0.60, _pl(offset_x=0.30),
    )
    o = s.overturning_x
    assert o.applied_moment_total_kNm == pytest.approx(o.applied_moment_dead_kNm, rel=1e-15)
    assert o.envelope_reading == "TOTAL"
    assert o.status is CheckStatus.NOT_VERIFIED


def test_la_envolvente_nunca_es_menor_que_ninguna_de_las_dos_lecturas():
    """Invariante del criterio: `applied_moment_kNm = max(total, estabilizante)`."""
    for off in (-0.60, -0.10, 0.0, 0.25, 0.70):
        for m in (-300.0, -80.0, 0.0, 120.0):
            s = check_stability(
                _casos(P_cm=400.0, P_cv=150.0, Mx_kNm=m, Hx_kN=15.0), _suelo(fs_over=1.5),
                150.0, 3.00, 2.40, 0.60, _pl(offset_x=off),
            )
            o = s.overturning_x
            assert o.applied_moment_kNm == pytest.approx(
                max(o.applied_moment_total_kNm, o.applied_moment_dead_kNm), rel=1e-15
            ), (off, m)
            assert o.envelope_reading in ("TOTAL", "ESTABILIZANTE")


# =========================================================================
# 4. Una sola implementación para las tres tipologías
# =========================================================================


def test_la_resultante_de_la_combinada_se_reconstruye_con_el_ayudante_comun():
    """`resultants` no reimplementa el término: suma lo que devuelve `axis_moments_kNm`."""
    lay = CombinedFootingLayout(
        B_m=6.00, L_m=2.40,
        columns=[
            ColumnOnFooting(label="C1", placement=_pl(offset_x=-2.00),
                            loads=_casos(P_cm=300.0, P_cv=100.0, Mx_kNm=40.0, Hx_kN=10.0)),
            ColumnOnFooting(label="C2", placement=_pl(offset_x=+1.50),
                            loads=_casos(P_cm=500.0, P_cv=200.0, Mx_kNm=-60.0, Hx_kN=15.0)),
        ],
    )
    r = resultants(lay)[0]
    total = suma_estab = 0.0
    for col in lay.columns:
        c = next(x for x in col.loads.service if x.name == r.name)
        t, e = axis_moments_kNm(c, col.offset_x_m, "X")
        total += t
        suma_estab += e
    assert r.Mx_total_kNm == pytest.approx(total, rel=1e-12)
    assert r.Mx_stabilizing_kNm == pytest.approx(suma_estab, rel=1e-12)


def test_la_aislada_y_la_combinada_dan_lo_mismo_ante_la_misma_resultante():
    """Paridad entre tipologías: una combinada cuya segunda columna no aporta carga debe
    dar exactamente el mismo volcamiento que la aislada con esa única columna.

    Si alguna de las dos vuelve a divergir, este test lo delata con números, no con
    inspección de código."""
    B, L, h, W = 6.00, 2.40, 0.70, 400.0
    off = -1.80
    carga = _casos(P_cm=450.0, P_cv=150.0, Mx_kNm=70.0, Hx_kN=35.0)
    sin_carga = _casos(P_cm=0.0, P_cv=0.0, Mx_kNm=0.0, Hx_kN=0.0)

    aislada = check_stability(carga, _suelo(fs_over=1.5, mu=0.45), W, B, L, h, _pl(offset_x=off))
    lay = CombinedFootingLayout(
        B_m=B, L_m=L,
        columns=[
            ColumnOnFooting(label="C1", placement=_pl(offset_x=off), loads=carga),
            ColumnOnFooting(label="C2", placement=_pl(offset_x=+2.00), loads=sin_carga),
        ],
    )
    combinada = check_combined_stability(lay, _suelo(fs_over=1.5, mu=0.45), W, B, L, h)

    a, c = aislada.overturning_x, combinada.overturning_x
    assert c.applied_moment_total_kNm == pytest.approx(a.applied_moment_total_kNm, rel=1e-12)
    assert c.applied_moment_dead_kNm == pytest.approx(a.applied_moment_dead_kNm, rel=1e-12)
    assert c.overturning_moment_kNm == pytest.approx(a.overturning_moment_kNm, rel=1e-12)
    assert c.FS_obtained == pytest.approx(a.FS_obtained, rel=1e-12)
    assert c.status is a.status
    assert c.envelope_reading == a.envelope_reading


def test_el_modelo_de_resultado_es_uno_solo():
    """`CombinedOverturningResult` dejó de ser un tipo aparte: los tres lo comparten."""
    from engine.foundation import combined_stability as comb
    from engine.soil import stability as st

    assert comb.CombinedOverturningResult is st.OverturningResult
    for campo in ("applied_moment_total_kNm", "applied_moment_dead_kNm", "envelope_reading"):
        assert campo in st.OverturningResult.model_fields


# =========================================================================
# 5. Ruido numérico (CLAUDE.md §10)
# =========================================================================


def test_un_momento_exactamente_compensado_no_es_demanda():
    """`M = −P·offset` —la zapata exterior de la conectada— deja un residuo de coma
    flotante, no una demanda. Sin tolerancia ese residuo producía un FS de 1e16."""
    P, off = 971.428571428571, -0.75
    s = check_stability(
        _directo(P, Mx_kNm=-P * off), _suelo(fs_over=1.5), 150.0, 2.00, 2.40, 0.90,
        _pl(offset_x=off),
    )
    o = s.overturning_x
    assert o.applied_moment_total_kNm == 0.0
    assert o.FS_obtained is None
    assert o.status is CheckStatus.PASS
    assert "No aplicable" in o.pivot_description
    assert s.applicable is False


def test_la_tolerancia_es_relativa_y_no_silencia_una_demanda_real():
    """Un momento pequeño PERO por encima del ruido sigue contando. La tolerancia mide la
    precisión con la que la diferencia puede formarse, no un umbral de ingeniería."""
    assert denoise_moment_kNm(1e-13, 728.0) == 0.0
    assert denoise_moment_kNm(0.05, 728.0) == 0.05
    # Justo por encima y justo por debajo del umbral relativo.
    escala = 1000.0
    assert denoise_moment_kNm(MOMENT_NOISE_REL_TOL * escala * 1.01, escala) != 0.0
    assert denoise_moment_kNm(MOMENT_NOISE_REL_TOL * escala * 0.99, escala) == 0.0
    # Un cero exacto sin escala no divide por nada.
    assert denoise_moment_kNm(0.0, 0.0) == 0.0


# =========================================================================
# 6. Protección de los campos excluidos del congelamiento
# =========================================================================


def test_las_dos_lecturas_son_coherentes_en_todos_los_casos_congelados():
    """`applied_moment_total_kNm` y `applied_moment_dead_kNm` están en `DIAGNOSTIC_FIELDS`
    y no se congelan: lo que se congela es su máximo, `applied_moment_kNm`.

    Este test es la contrapartida de esa exclusión. Recorre TODOS los casos congelados de
    las tres tipologías y comprueba, entrada por entrada, que el máximo es el que manda y
    que la lectura declarada es la que corresponde. Sin él, un error en el desglose no lo
    vería nadie."""
    from tests.freeze.cases import CASES, CONNECTED_CASES
    from tests.freeze.test_freeze_connected import _solve as _solve_conectada
    from tests.freeze.test_freeze_isolated import _evaluate

    revisadas = 0

    def _revisar(o, etiqueta):
        nonlocal revisadas
        revisadas += 1
        assert o.applied_moment_kNm == pytest.approx(
            max(o.applied_moment_total_kNm, o.applied_moment_dead_kNm), abs=1e-12
        ), etiqueta
        esperado = (
            "TOTAL" if o.applied_moment_total_kNm >= o.applied_moment_dead_kNm
            else "ESTABILIZANTE"
        )
        assert o.envelope_reading == esperado, etiqueta
        assert o.applied_moment_total_kNm >= 0.0 and o.applied_moment_dead_kNm >= 0.0, etiqueta

    for caso in CASES:
        r = _evaluate(caso)
        for eje in ("x", "y"):
            _revisar(getattr(r.stability, f"overturning_{eje}"), f"{caso.name}/{eje}")

    for caso in CONNECTED_CASES:
        if caso.expects_rejection:
            continue
        r = _solve_conectada(caso)
        for lado in ("exterior", "interior"):
            for eje in ("x", "y"):
                _revisar(
                    getattr(getattr(r, lado).stability, f"overturning_{eje}"),
                    f"{caso.name}/{lado}/{eje}",
                )

    assert revisadas >= 40, f"Solo se revisaron {revisadas} entradas de volcamiento"


# =========================================================================
# 7. Paridad de API y UI con lo que el motor calcula
# =========================================================================


def test_la_api_publica_el_criterio_y_la_lectura_de_la_envolvente():
    """La UI no puede reconstruir el criterio: tiene que venir resuelto (CLAUDE.md §2).

    Antes de FORMULACION_VOLTEO la aislada publicaba el FS obtenido del volcamiento pero
    no el requerido, ni la combinación que gobierna, ni —cuando pasó a existir— la lectura
    de la envolvente. La tabla de la UI enseñaba «—» en esas columnas. El contrato se
    amplió de forma ADITIVA, igual que ya lo tenía la combinada."""
    from fastapi.testclient import TestClient

    from api.server import app

    combos = [
        {"name": "S1", "type": "SERVICIO", "P_kN": 450.0, "Mx_kNm": 40.0, "Hx_kN": 30.0},
        {"name": "U1", "type": "FACTORIZADA", "P_kN": 630.0, "Mx_kNm": 56.0, "Hx_kN": 42.0},
    ]
    peticion = {
        "combinations": combos,
        "column": {"shape": "cuadrada", "bx_m": 0.40, "by_m": 0.40, "offset_x_m": 0.30},
        "soil": {
            "qadm_kPa": 150.0, "pressure_basis": "BRUTA", "gamma_kNm3": 18.0, "Df_m": 1.2,
            "mu_friction_soil_concrete": 0.45, "FS_sliding_required": 1.5,
            "FS_overturning_required": 1.5, "source_notes": "",
        },
        "search": {
            "B_min_m": 2.0, "B_max_m": 3.0, "B_step_m": 0.2,
            "L_min_m": 2.0, "L_max_m": 3.0, "L_step_m": 0.2,
            "max_LB_ratio": 1.6, "h_min_m": 0.50, "h_max_m": 0.80, "h_step_m": 0.05,
            "hook_type_x": "ninguno", "hook_type_y": "ninguno",
        },
    }
    r = TestClient(app).post("/api/design", json=peticion)
    assert r.status_code == 200, r.text
    est = r.json()["top"][0]["stability"]

    assert est["overturning_x_FS_required"] == 1.5
    assert est["overturning_x_governing_combo"] == "S1"
    assert est["overturning_x_envelope_reading"] in ("TOTAL", "ESTABILIZANTE")
    assert est["overturning_y_FS_required"] == 1.5
    # El criterio adoptado, el término de excentricidad y la envolvente llegan escritos
    # por el motor, sin que la UI tenga que redactarlos.
    for fragmento in ("D10-2b", "P·offset", "ENVOLVENTE"):
        assert fragmento in est["criterion_note"], fragmento


def test_la_api_no_reinterpreta_el_estado_del_volcamiento():
    """El DTO transporta; no decide. Se comprueba contra el motor, no contra sí mismo."""
    from types import SimpleNamespace

    from api import mapping

    s = check_stability(
        _casos(P_cm=300.0, P_cv=700.0, Hx_kN=200.0), _suelo(fs_over=1.5), 67.58,
        1.60, 1.60, 0.80, _pl(offset_x=0.264),
    )
    dto = mapping.stability_to_dto(SimpleNamespace(stability=s))
    assert dto.overturning_x_status == s.overturning_x.status.value
    assert dto.overturning_x_FS == s.overturning_x.FS_obtained
    assert dto.overturning_x_FS_required == s.overturning_x.FS_required
    assert dto.overturning_x_envelope_reading == s.overturning_x.envelope_reading
    assert dto.overturning_y_envelope_reading == s.overturning_y.envelope_reading
