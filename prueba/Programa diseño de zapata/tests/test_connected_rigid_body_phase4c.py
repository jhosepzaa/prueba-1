"""FASE 4C — Modelo de CUERPO RÍGIDO de la zapata conectada.

FUENTE PRIMARIA
===============
Apuntes CR2-93-134 §3.6, problema de aplicación 2. El enunciado declara el modelo:

    «Solución simplificada del problema asumiendo zapata rígida y comportamiento
     elástico lineal del suelo. El modelo de análisis será el de un cuerpo rígido para
     el conjunto de 2 zapatas y la viga de conexión pues la viga lleva esfuerzos de la
     zapata izquierda a la zapata derecha y viceversa.»

QUÉ SE VERIFICA
===============
1. El motor reproduce el problema 2 del libro: A, centroide, I y las presiones de sus
   tres combinaciones, dentro del redondeo de la propia fuente.
2. El módulo de balasto NO hace falta — resolución de TBD-C2 — y el motor no lo pide.
3. Las tres consecuencias de arquitectura que el modelo articulado no tenía:
   F1 las dos huellas, F2 el peso propio en el reparto, F3 la detección de despegue.
4. Los dos modelos dan resultados DISTINTOS sobre la misma entrada.
"""

from __future__ import annotations

import pytest

from engine.analysis.connected_statics import distribute_couple
from engine.analysis.connecting_beam_statics import solve_connecting_beam
from engine.domain.column import Column
from engine.domain.connected_layout import (
    AnalysisModel,
    BeamSelfWeightMode,
    BeamSupportMode,
    ConnectedElement,
    ConnectedFootingLayout,
    ConnectingBeamSpec,
    CoupleTransferMode,
    EdgeAnchor,
    Footprint,
    Footprints,
)
from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.domain.soil import PressureBasis, SoilProfile

TON = 9.80665

# --- Problema 2: columna 0,80 al ras (eje a 0,40) e interior a 6,50 m -------
COL80 = Column(shape="cuadrada", bx_m=0.80, by_m=0.80)
S = 6.50
SIGMA_ADM_TM2 = 17.5

# El libro toma p.p. = volumen × 2,4 t/m³, sin relleno. Para contrastar se usa
# Df = h, con lo que `compute_self_weight` no añade relleno y las dos cuentas son la
# misma. No es un ajuste del motor: es igualar las hipótesis antes de comparar.
SUELO_P2 = SoilProfile(
    qadm_kPa=SIGMA_ADM_TM2 * TON, pressure_basis=PressureBasis.BRUTA,
    gamma_kNm3=18.0, Df_m=0.60, source_notes="Aragón CR2-93-134 §3.6 problema 2",
)
GAMMA_CONCRETO_KNM3 = 2.4 * TON

# (largo longitudinal, ancho transversal, h) — el libro los lista como ancho × largo.
PREDIM = dict(ext=(2.0, 3.0, 0.6), inter=(5.5, 2.1, 0.6))
FINAL = dict(ext=(2.3, 4.5, 0.6), inter=(6.7, 3.3, 0.6))


def _cargas(P_t: float, M_tm: float) -> LoadCaseSet:
    return LoadCaseSet(
        service=[LoadCombination(name="S1", type=LoadCombinationType.SERVICIO,
                                 P_kN=P_t * TON, Mx_kNm=M_tm * TON)],
        factored=[LoadCombination(name="U1", type=LoadCombinationType.FACTORIZADA,
                                  P_kN=P_t * TON, Mx_kNm=M_tm * TON)],
    )


def _layout(P_ext, M_ext, P_int, M_int, modelo=AnalysisModel.CUERPO_RIGIDO):
    return ConnectedFootingLayout(
        analysis_model=modelo,
        couple_transfer_mode=CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION,
        exterior=ConnectedElement(
            label="Z1", column=COL80, loads=_cargas(P_ext, M_ext),
            anchor=EdgeAnchor(edge="X_MIN", face_clearance_m=0.0),
        ),
        interior=ConnectedElement(label="Z2", column=COL80, loads=_cargas(P_int, M_int)),
        beam=ConnectingBeamSpec(
            b_m=0.35, h_m=1.20, d_m=1.10,
            support_mode=BeamSupportMode.SIN_APOYO,
            self_weight_mode=BeamSelfWeightMode.DESPRECIADO,
        ),
        axis_distance_m=S, longitudinal_axis="X",
    )


def _resolver(geo, P_ext=95.0, M_ext=6.0, P_int=180.0, M_int=-6.5,
              modelo=AnalysisModel.CUERPO_RIGIDO):
    lay = _layout(P_ext, M_ext, P_int, M_int, modelo)
    fp = lay.footprints(*geo["ext"], *geo["inter"])
    d = distribute_couple(
        lay, fp, lay.exterior.loads.service[0], lay.interior.loads.service[0],
        SUELO_P2, GAMMA_CONCRETO_KNM3,
    )
    return lay, fp, d


# =========================================================================
# 1. Benchmark del problema 2 — las propiedades de sección
# =========================================================================

def test_p2_el_motor_reproduce_el_area_de_apoyo():
    _, fp, _ = _resolver(FINAL)
    assert fp.total_area_m2 == pytest.approx(32.46, abs=0.005)


def test_p2_el_motor_reproduce_el_momento_de_inercia():
    """Sale solo si las dos huellas se tratan como una sección compuesta, que es la
    lectura del método. Si estuviera mal, este número no caería cerca."""
    _, fp, _ = _resolver(FINAL)
    assert fp.inertia_m4 == pytest.approx(320.36, abs=0.05)


def test_p2_el_vano_entre_huellas_no_aporta_area():
    """La zapata combinada tiene área continua; la conectada, no. Confundirlas daría
    un área mayor y presiones menores: un falso PASS."""
    _, fp, _ = _resolver(FINAL)
    assert fp.width_at((fp.exterior.end_m + fp.interior.start_m) / 2.0) == 0.0
    assert fp.total_area_m2 < (fp.end_m - fp.start_m) * fp.exterior.width_m


# =========================================================================
# 2. Benchmark del problema 2 — las presiones
# =========================================================================

@pytest.mark.parametrize("nombre, P_ext, M_ext, P_int, M_int, s_min, s_max", [
    ("CM+CV", 95.0, 6.0, 180.0, -6.5, 8.14, 11.63),
    ("CM+CV+CS", 75.0, 146.0, 200.0, 143.5, 5.01, 14.96),
    ("CM+CV-CS", 115.0, -134.0, 160.0, -156.5, 1.32, 18.25),
])
def test_p2_el_motor_reproduce_las_presiones(nombre, P_ext, M_ext, P_int, M_int,
                                             s_min, s_max):
    """Las tres combinaciones del libro, dentro de su propio redondeo: la fuente
    redondea el centroide a 5,05 m cuando el exacto es 5,067, y eso propaga menos de
    un 1 % a las presiones."""
    _, _, d = _resolver(FINAL, P_ext, M_ext, P_int, M_int)
    assert d.sigma_min_kPa / TON == pytest.approx(s_min, abs=0.10)
    assert d.sigma_max_kPa / TON == pytest.approx(s_max, abs=0.15)


def test_p2_el_predimensionamiento_del_libro_se_rechaza():
    """El libro lo descarta —σ⁺ = 18,91 > 17,5— y redimensiona. El motor debe llegar a
    la misma conclusión, o su criterio de aceptación no serviría."""
    _, _, d = _resolver(PREDIM)
    assert d.sigma_max_kPa / TON == pytest.approx(18.91, abs=0.10)
    assert d.sigma_max_kPa / TON > SIGMA_ADM_TM2


def test_p2_la_combinacion_sismica_es_la_critica():
    _, _, gravedad = _resolver(FINAL)
    _, _, sismo = _resolver(FINAL, 115.0, -134.0, 160.0, -156.5)
    assert sismo.sigma_max_kPa > gravedad.sigma_max_kPa


# =========================================================================
# 3. TBD-C2 resuelto: el módulo de balasto se cancela
# =========================================================================

def test_el_resultado_no_depende_de_ningun_parametro_de_rigidez_del_suelo():
    """Para un cuerpo rígido, p(s) = k_s·w0 + (k_s·θ)·s y las incógnitas que fijan la
    presión son esos dos PRODUCTOS, determinados por el equilibrio. k_s se cancela.

    Se comprueba variando lo único del perfil de suelo que podría hacer las veces de
    rigidez —γ y qadm— y verificando que las presiones no se mueven."""
    lay = _layout(95.0, 6.0, 180.0, -6.5)
    fp = lay.footprints(*FINAL["ext"], *FINAL["inter"])
    presiones = []
    for qadm, gamma in ((17.5 * TON, 18.0), (60.0 * TON, 22.0)):
        suelo = SoilProfile(qadm_kPa=qadm, pressure_basis=PressureBasis.BRUTA,
                            gamma_kNm3=gamma, Df_m=0.60, source_notes="x")
        d = distribute_couple(lay, fp, lay.exterior.loads.service[0],
                              lay.interior.loads.service[0], suelo, GAMMA_CONCRETO_KNM3)
        presiones.append((d.sigma_min_kPa, d.sigma_max_kPa))
    assert presiones[0] == pytest.approx(presiones[1], rel=1e-12)


def test_el_layout_no_admite_un_modulo_de_balasto():
    campos = set(ConnectedFootingLayout.model_fields) | set(SoilProfile.model_fields)
    assert not any("balasto" in c or "subgrade" in c for c in campos)


# =========================================================================
# 4. F1 — el contrato lleva las dos huellas
# =========================================================================

def test_F1_el_resultado_depende_de_la_huella_INTERIOR():
    """En el modelo articulado la geometría de la zapata interior no entraba en el
    reparto. Aquí sí: si no cambiara nada, F1 sería innecesaria y el modelo, falso."""
    _, _, base = _resolver(FINAL)
    otra = dict(ext=FINAL["ext"], inter=(4.0, 3.3, 0.6))
    _, _, cambiada = _resolver(otra)
    assert cambiada.sigma_max_kPa != pytest.approx(base.sigma_max_kPa, rel=1e-6)
    assert cambiada.bearing_inertia_m4 != pytest.approx(base.bearing_inertia_m4, rel=1e-6)


def test_F1_la_huella_interior_va_centrada_en_su_columna():
    _, fp, _ = _resolver(FINAL)
    assert fp.interior.centroid_m == pytest.approx(0.40 + S, abs=1e-12)


def test_F1_la_huella_exterior_arranca_en_el_lindero():
    _, fp, _ = _resolver(FINAL)
    assert fp.exterior.start_m == pytest.approx(0.0, abs=1e-12)


# =========================================================================
# 5. F2 — el peso propio de las zapatas entra en el reparto
# =========================================================================

def test_F2_el_peso_propio_de_las_zapatas_aparece_en_el_resultado():
    _, _, d = _resolver(FINAL)
    assert d.W_ext_kN > 0.0 and d.W_int_kN > 0.0


def test_F2_el_peso_propio_cambia_el_reparto():
    """En el modelo articulado se agrupaba y desaparecía. Aquí la resultante bajo cada
    zapata NO pasa por su centroide, de modo que sus momentos dejan de cancelarse."""
    lay = _layout(95.0, 6.0, 180.0, -6.5)
    fp_delgada = lay.footprints(2.3, 4.5, 0.30, 6.7, 3.3, 0.30)
    fp_gruesa = lay.footprints(2.3, 4.5, 1.20, 6.7, 3.3, 1.20)
    suelo = SoilProfile(qadm_kPa=17.5 * TON, pressure_basis=PressureBasis.BRUTA,
                        gamma_kNm3=18.0, Df_m=1.20, source_notes="x")
    d1 = distribute_couple(lay, fp_delgada, lay.exterior.loads.service[0],
                           lay.interior.loads.service[0], suelo, GAMMA_CONCRETO_KNM3)
    d2 = distribute_couple(lay, fp_gruesa, lay.exterior.loads.service[0],
                           lay.interior.loads.service[0], suelo, GAMMA_CONCRETO_KNM3)
    assert d2.W_ext_kN > d1.W_ext_kN
    assert d2.sigma_max_kPa != pytest.approx(d1.sigma_max_kPa, rel=1e-6)


def test_F2_la_carga_corregida_es_NETA_de_peso_propio():
    """`evaluate_candidate` añade el peso propio por su cuenta. Entregarle la carga
    bruta lo contaría dos veces."""
    _, _, d = _resolver(FINAL)
    assert d.P_ext_corrected_kN == pytest.approx(d.R_ext_kN - d.W_ext_kN, rel=1e-12)


def test_F2_la_carga_se_conserva_pese_al_peso_propio():
    _, _, d = _resolver(FINAL)
    assert d.conserves_load
    assert d.P_ext_corrected_kN + d.P_int_corrected_kN == pytest.approx(
        d.P_ext_kN + d.P_int_kN, rel=1e-9
    )


# =========================================================================
# 6. F3 — detección de despegue
# =========================================================================

def test_F3_sin_despegue_en_el_caso_del_libro():
    for datos in ((95.0, 6.0, 180.0, -6.5), (115.0, -134.0, 160.0, -156.5)):
        _, _, d = _resolver(FINAL, *datos)
        assert not d.uplift
        assert d.sigma_min_kPa > 0.0


def test_F3_un_momento_suficiente_produce_despegue_y_se_detecta():
    """E.060 §15.2 prohíbe considerar tracciones. Con presión negativa el campo lineal
    deja de valer y el caso exige contacto parcial, fuera de alcance: debe declararse,
    no aceptarse en silencio."""
    _, _, d = _resolver(FINAL, 115.0, -900.0, 160.0, -900.0)
    assert d.uplift
    assert d.sigma_min_kPa < 0.0
    assert any("DESPEGUE" in h for h in d.hypotheses)
    assert any("15.2" in h for h in d.hypotheses)


def test_F3_el_despegue_no_rompe_los_invariantes():
    """Sigue siendo un resultado de equilibrio: lo que deja de valer es su lectura
    física, y por eso se marca en vez de levantar excepción."""
    _, _, d = _resolver(FINAL, 115.0, -900.0, 160.0, -900.0)
    assert d.closes and d.conserves_load


# =========================================================================
# 7. Los dos modelos son distintos, y la junta transmite momento
# =========================================================================

def test_la_junta_del_cuerpo_rigido_transmite_momento():
    """Es lo que define el modelo frente al articulado: «la viga lleva esfuerzos de la
    zapata izquierda a la derecha y viceversa»."""
    _, _, d = _resolver(FINAL)
    assert d.M_cut_kNm != pytest.approx(0.0, abs=1.0)


def test_el_modelo_articulado_mantiene_la_rotula():
    _, _, d = _resolver(FINAL, modelo=AnalysisModel.ARTICULADO)
    assert d.M_cut_kNm == 0.0


def test_los_dos_modelos_dan_resultados_distintos():
    """Si coincidieran sobre la misma entrada, uno de los dos estaría mal
    implementado."""
    _, _, rigido = _resolver(FINAL)
    _, _, articulado = _resolver(FINAL, modelo=AnalysisModel.ARTICULADO)
    assert rigido.P_ext_corrected_kN != pytest.approx(
        articulado.P_ext_corrected_kN, rel=1e-6
    )
    assert rigido.M_cut_kNm != pytest.approx(articulado.M_cut_kNm, abs=1.0)


def test_la_viga_del_cuerpo_rigido_se_contrasta_contra_el_reparto():
    """La comprobación cruzada del momento de junta, que en el articulado verificaba
    la rótula, aquí verifica que el diagrama y el reparto cuentan lo mismo.

    Fase 5A. Antes solo se afirmaba que el valor DECLARADO se copiaba, y el contraste
    real salía False sin que nada lo notara. Ahora la viga necesita las huellas —usa el
    campo de presión real— y el contraste tiene que CERRAR."""
    lay, fp, d = _resolver(FINAL)
    b = solve_connecting_beam(lay, d, fp)
    assert b.M_cut_declared_kNm == pytest.approx(d.M_cut_kNm)
    assert b.cut_moment_consistent, (
        f"El diagrama de la viga da {b.M_at_cut_kNm:.4f} kN·m en el eje interior y el "
        f"reparto {d.M_cut_kNm:.4f} kN·m: describen cuerpos distintos."
    )


def test_la_viga_del_cuerpo_rigido_exige_las_huellas():
    """Sin las huellas la viga solo podría suponer presión uniforme, que es
    exactamente el defecto D3/M1. Se rechaza en vez de suponerlo."""
    lay, _, d = _resolver(FINAL)
    with pytest.raises(ValueError, match="necesita las huellas"):
        solve_connecting_beam(lay, d)


def test_en_cuerpo_rigido_solo_es_aplicable_el_equilibrio_en_cimentacion():
    """TBD-C11 pregunta dónde va la rama cercana del par. En cuerpo rígido no hay dos
    cuerpos: el conjunto se equilibra globalmente y la pregunta no se plantea.

    Fase 5A, D1. Este test afirmaba antes que los dos modos daban el mismo reparto, y
    era cierto para las ZAPATAS; pero la viga sí cambiaba, porque se resolvía con el
    cuerpo libre de par puro articulado. La decisión (a1) no es declarar el modo inerte
    sino rechazar la combinación, porque sus hipótesis se excluyen.

    Se prueba por `model_copy`, que NO ejecuta validadores: es precisamente el camino
    por el que la combinación podría colarse si la guarda estuviera solo en el layout."""
    lay = _layout(95.0, 6.0, 180.0, -6.5)
    fp = lay.footprints(*FINAL["ext"], *FINAL["inter"])

    d = distribute_couple(lay, fp, lay.exterior.loads.service[0],
                          lay.interior.loads.service[0], SUELO_P2, GAMMA_CONCRETO_KNM3)
    assert d.couple_transfer_mode is CoupleTransferMode.EQUILIBRIO_EN_CIMENTACION

    colado = lay.model_copy(
        update={"couple_transfer_mode": CoupleTransferMode.PAR_PURO_EN_ZAPATA}
    )
    with pytest.raises(ValueError, match="Combinación incompatible"):
        distribute_couple(colado, fp, colado.exterior.loads.service[0],
                          colado.interior.loads.service[0], SUELO_P2,
                          GAMMA_CONCRETO_KNM3)
