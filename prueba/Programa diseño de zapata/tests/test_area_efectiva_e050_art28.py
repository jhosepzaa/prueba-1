"""Método del área efectiva — E.050 art. 28.2-28.3 (2026-09-19).

QUÉ SE DECIDIÓ Y POR QUÉ
========================
Hasta aquí, una resultante fuera del núcleo central descartaba la alternativa: el campo
lineal `q = P/A ± M·c/I` produciría tracciones, que E.060 §15.2.3 prohíbe, y el motor no
tenía otro modelo. Pero **E.050 art. 28 sí prescribe uno** —`B' = B − 2|ex|`,
`L' = L − 2|ey|`, carga centrada sobre el área reducida—, de modo que no era un hueco
normativo sino de implementación.

EL CRITERIO ADOPTADO, QUE ES EL CONSERVADOR
===========================================
El área efectiva **extiende** al núcleo central, no lo sustituye:

  - **dentro del núcleo** rige el PICO de la distribución lineal, exactamente como con
    `KernCheckModel`. La presión uniforme del art. 28 es menor —3/4 del pico con
    excentricidad en un solo eje—, y aplicarla ahí relajaría casos que hoy se verifican
    con el pico;
  - **fuera del núcleo** rige E.050 art. 28.

Consecuencia comprobada abajo: elegir el modelo **solo puede añadir** geometrías que el
núcleo descartaba. Ninguna de las que ya pasaban cambia de resultado, y ningún FAIL se
convierte en PASS.

LA ASIMETRÍA DEL qadm
=====================
`qadm` lo declara el proyectista y el EMS lo obtiene para la zapata real B×L. El art. 28
evalúa sobre B'×L', y la capacidad portante de una zapata más estrecha no es la misma: en
suelo granular baja con B, y si gobierna el asentamiento, sube. El motor no puede saber
cuál es el caso sin parámetros geotécnicos que `CLAUDE.md` §1 le prohíbe suponer, así que
aplica la misma regla asimétrica que ya usa en la estabilidad con E.020 art. 20.1:

  - `q > qadm` → **FAIL**, válido a fortiori;
  - `q ≤ qadm` → **NO VERIFICADO**, salvo que el proyectista declare que su qadm vale para
    las dimensiones efectivas.

Detalle en `docs/area_efectiva_e050_art28.md`.
"""

import pytest

from engine.codes.peru.e050_soils import (
    EFFECTIVE_AREA_REFERENCE,
    effective_area_from_eccentricity,
    effective_area_meyerhof,
)
from engine.codes.peru.e060_concrete import E060ConcreteCode
from engine.domain.column import Column
from engine.domain.column_placement import ColumnPlacement
from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.domain.materials import MaterialConcrete, MaterialSteel
from engine.domain.search_parameters import DepthSearchParameters
from engine.domain.soil import PressureBasis, SoilProfile
from engine.foundation.depth_solver import evaluate_candidate
from engine.results.status import CheckStatus
from engine.soil.contact_pressure import (
    EffectiveAreaModel,
    FullContactModel,
    KernCheckModel,
)

SERV = LoadCombinationType.SERVICIO
FACT = LoadCombinationType.FACTORIZADA


# =========================================================================
# 1. El cálculo, reconstruido a mano
# =========================================================================


def test_las_dimensiones_efectivas_son_las_del_articulo():
    """«El ancho (B) o largo (L), se corrige por excentricidad reduciéndolo en dos veces
    la excentricidad» (art. 28.2). Reconstruido sin llamar al código que se prueba."""
    B, L, ex, ey = 3.00, 2.40, 0.55, 0.20
    r = effective_area_from_eccentricity(B, L, ex, ey)
    assert r.B_eff_m == pytest.approx(3.00 - 2 * 0.55)
    assert r.L_eff_m == pytest.approx(2.40 - 2 * 0.20)
    assert "28.2" in r.code_reference


def test_el_signo_de_la_excentricidad_no_cambia_el_area():
    """La reducción es por |e|: la resultante puede caer a un lado o al otro."""
    a = effective_area_from_eccentricity(3.0, 2.4, +0.55, -0.20)
    b = effective_area_from_eccentricity(3.0, 2.4, -0.55, +0.20)
    assert a.B_eff_m == pytest.approx(b.B_eff_m)
    assert a.L_eff_m == pytest.approx(b.L_eff_m)


def test_cada_excentricidad_corrige_SU_dimension():
    """`ex` desplaza la resultante a lo largo de X y corrige B; `ey` corrige L. Cruzarlos
    es el defecto fácil de este cálculo (E.050 art. 28.1, convención de ejes del motor)."""
    r = effective_area_from_eccentricity(B_m=4.0, L_m=2.0, ex_m=0.50, ey_m=0.25)
    assert r.B_eff_m == pytest.approx(3.0)
    assert r.L_eff_m == pytest.approx(1.5)


def test_la_version_por_momentos_es_la_misma_implementacion():
    """`effective_area_meyerhof` es una envoltura, no un segundo cálculo: e = M/Q."""
    Q = 500.0
    por_momentos = effective_area_meyerhof(3.0, 2.4, M1_kNm=0.20 * Q, M2_kNm=0.55 * Q, Q_kN=Q)
    por_excentricidad = effective_area_from_eccentricity(3.0, 2.4, ex_m=0.55, ey_m=0.20)
    assert por_momentos == por_excentricidad


def test_area_no_positiva_se_rechaza_o_se_reporta_segun_se_pida():
    """Con |ex| ≥ B/2 la resultante cae fuera de la huella. En modo estricto es un error;
    en modo no estricto se devuelven las dimensiones para poder REPORTAR la condición."""
    with pytest.raises(ValueError, match="no positiva"):
        effective_area_from_eccentricity(3.0, 2.4, ex_m=1.60, ey_m=0.0)
    r = effective_area_from_eccentricity(3.0, 2.4, ex_m=1.60, ey_m=0.0, strict=False)
    assert r.B_eff_m == pytest.approx(-0.20)


def test_la_presion_es_la_carga_repartida_sobre_el_area_efectiva():
    """Art. 28.3: la carga se centra sobre el área efectiva, de modo que la presión
    aplicada es uniforme y vale Q/(B'·L')."""
    B, L, Q, ex = 3.00, 2.40, 600.0, 0.55  # ex > B/6 = 0,50: fuera del núcleo
    r = EffectiveAreaModel().compute(B, L, Q, ex, 0.0)
    q_a_mano = Q / ((B - 2 * ex) * L)
    assert r.qmax_kPa == pytest.approx(q_a_mano, rel=1e-12)
    assert r.qmin_kPa == pytest.approx(q_a_mano, rel=1e-12)
    assert r.qavg_kPa == pytest.approx(Q / (B * L), rel=1e-12), (
        "qavg conserva su significado: la media sobre la huella REAL"
    )
    assert r.code_reference == EFFECTIVE_AREA_REFERENCE


# =========================================================================
# 2. El criterio adoptado: extiende, no sustituye
# =========================================================================


@pytest.mark.parametrize("ex", [0.0, 0.10, 0.30, 0.49, 0.50])
def test_dentro_del_nucleo_el_modelo_no_cambia_absolutamente_nada(ex):
    """B/6 = 0,50 m. Hasta ahí, el área efectiva devuelve lo mismo que el núcleo central,
    bit a bit. Es lo que garantiza que elegir el modelo no relaje ningún caso."""
    B, L, Q = 3.00, 2.40, 600.0
    ea = EffectiveAreaModel().compute(B, L, Q, ex, 0.0)
    kern = KernCheckModel().compute(B, L, Q, ex, 0.0)
    assert ea.qmax_kPa == kern.qmax_kPa
    assert ea.qmin_kPa == kern.qmin_kPa
    assert ea.within_kern is True
    assert ea.usable is True
    assert ea.effective_area_governs is False
    assert ea.compliance_can_be_affirmed is True


def test_la_presion_uniforme_del_articulo_es_MENOR_que_el_pico_lineal():
    """La razón de ser del criterio adoptado, con números.

    Con excentricidad en un solo eje, el cociente entre las dos lecturas vale

        q_area / pico = B² / ((B − 2e)·(B + 6e))

    que es menor que 1 en todo el núcleo y vale exactamente 3/4 en su borde, e = B/6.
    Si el art. 28 se aplicara también dentro del núcleo, el modelo sería MÁS PERMISIVO que
    el actual justo donde el actual es válido, y elegirlo podría convertir un FAIL en un
    PASS. Por eso extiende y no sustituye."""
    B, L, Q = 3.00, 2.40, 600.0
    for ex in (0.05, 0.20, 0.40, B / 6.0):
        pico_lineal = FullContactModel().compute(B, L, Q, ex, 0.0).qmax_kPa
        q_area = Q / ((B - 2 * ex) * L)
        esperado = B**2 / ((B - 2 * ex) * (B + 6 * ex))
        assert q_area / pico_lineal == pytest.approx(esperado, rel=1e-12), ex
        assert q_area < pico_lineal, ex
    # En el borde del núcleo, exactamente 3/4.
    ex = B / 6.0
    pico_borde = FullContactModel().compute(B, L, Q, ex, 0.0).qmax_kPa
    assert Q / ((B - 2 * ex) * L) / pico_borde == pytest.approx(0.75, rel=1e-12)


@pytest.mark.parametrize("ex", [0.55, 0.70, 1.00, 1.40])
def test_fuera_del_nucleo_gobierna_el_articulo_28(ex):
    B, L, Q = 3.00, 2.40, 600.0
    r = EffectiveAreaModel().compute(B, L, Q, ex, 0.0)
    assert r.within_kern is False
    assert r.usable is True, "El área efectiva sí resuelve este caso"
    assert r.effective_area_governs is True
    assert r.qmax_kPa == pytest.approx(Q / ((B - 2 * ex) * L), rel=1e-12)
    assert "art. 28" in r.code_reference


def test_fuera_de_la_huella_no_lo_resuelve_ningun_modelo():
    """|ex| ≥ B/2: no hay equilibrio posible sobre esta base."""
    r = EffectiveAreaModel().compute(3.00, 2.40, 600.0, 1.60, 0.0)
    assert r.B_eff_m <= 0.0
    assert r.usable is False
    assert "fuera de la huella" in r.equation_substituted or "NO\nPOSITIVA" in r.equation_substituted


# =========================================================================
# 3. La asimetría del qadm
# =========================================================================


def test_sin_la_declaracion_un_cumplimiento_no_puede_afirmarse():
    r = EffectiveAreaModel().compute(3.00, 2.40, 600.0, 0.55, 0.0)
    assert r.qadm_declared_for_effective_area is False
    assert r.compliance_can_be_affirmed is False


def test_con_la_declaracion_del_proyectista_si_puede_afirmarse():
    r = EffectiveAreaModel(qadm_declared_for_effective_area=True).compute(
        3.00, 2.40, 600.0, 0.55, 0.0
    )
    assert r.qadm_declared_for_effective_area is True
    assert r.compliance_can_be_affirmed is True


def test_la_declaracion_no_tiene_efecto_dentro_del_nucleo():
    """Dentro del núcleo el art. 28 no gobierna, de modo que no hay asimetría que cerrar:
    el qadm se compara contra el pico lineal sobre la huella real, como siempre."""
    sin = EffectiveAreaModel().compute(3.00, 2.40, 600.0, 0.30, 0.0)
    assert sin.compliance_can_be_affirmed is True


# =========================================================================
# 4. De punta a punta, en el solver de la zapata aislada
# =========================================================================

COL = Column(shape="cuadrada", bx_m=0.50, by_m=0.50)
CONC = MaterialConcrete(fc_MPa=21.0, unit_weight_kNm3=24.0)
STEEL = MaterialSteel(fy_MPa=420.0, bar_type="corrugada")
CODE = E060ConcreteCode()


def _suelo(qadm: float) -> SoilProfile:
    return SoilProfile(
        qadm_kPa=qadm, pressure_basis=PressureBasis.BRUTA, gamma_kNm3=18.0, Df_m=1.20,
    )


def _cargas(P: float, Mx: float) -> LoadCaseSet:
    return LoadCaseSet(
        service=[LoadCombination(name="S1", type=SERV, P_kN=P, Mx_kNm=Mx)],
        factored=[LoadCombination(name="U1", type=FACT, P_kN=P * 1.4, Mx_kNm=Mx * 1.4)],
    )


def _evaluar(modelo, qadm: float, P: float = 600.0, Mx: float = 420.0):
    """Mx/P = 0,70 m de excentricidad sobre B = 3,00 m: B/6 = 0,50, de modo que la
    resultante cae FUERA del núcleo y los dos modelos se separan."""
    return evaluate_candidate(
        B_m=3.00, L_m=2.40, h_m=0.70, column=COL, soil=_suelo(qadm),
        concrete=CONC, steel=STEEL, load_case_set=_cargas(P, Mx), code=CODE,
        contact_model=modelo, placement=ColumnPlacement(column=COL),
        depth_params=DepthSearchParameters(h_min_m=0.40, h_max_m=1.20, h_step_m=0.05),
    )


def test_el_nucleo_descarta_y_el_area_efectiva_evalua():
    """El caso que motiva todo: una geometría que E.050 art. 28 admite y que el modelo
    por defecto descartaba sin llegar a mirarla."""
    con_nucleo = _evaluar(KernCheckModel(), qadm=400.0)
    entrada = con_nucleo.trace.by_id("contact_pressure")
    assert entrada.status is CheckStatus.FAIL
    assert any("núcleo central" in m for m in con_nucleo.discard_reasons)

    con_area = _evaluar(EffectiveAreaModel(), qadm=400.0)
    entrada_area = con_area.trace.by_id("contact_pressure")
    assert entrada_area.status is CheckStatus.NOT_VERIFIED
    assert not any("núcleo central" in m for m in con_area.discard_reasons)
    assert "28.2" in entrada_area.code_reference


def test_un_incumplimiento_calculado_con_area_efectiva_es_FAIL_de_verdad():
    """La mitad válida de la asimetría: si ni siquiera con la cota optimista cumple, el
    incumplimiento se afirma."""
    r = _evaluar(EffectiveAreaModel(), qadm=80.0)
    assert r.trace.by_id("contact_pressure").status is CheckStatus.FAIL
    assert any("qmax > qadm" in m for m in r.discard_reasons)


def test_la_declaracion_del_proyectista_cierra_la_asimetria_de_punta_a_punta():
    r = _evaluar(EffectiveAreaModel(qadm_declared_for_effective_area=True), qadm=400.0)
    assert r.trace.by_id("contact_pressure").status is CheckStatus.PASS


def test_el_motivo_del_descarte_dice_que_el_area_efectiva_existe():
    """El texto anterior decía «no implementado en el MVP», que ya no es cierto. Es una
    categoría de texto global (`CLAUDE.md` §5): una redacción por causa."""
    r = _evaluar(KernCheckModel(), qadm=400.0)
    motivo = next(m for m in r.discard_reasons if "núcleo central" in m)
    assert "E.050 art. 28" in motivo
    assert "MVP" not in motivo


def test_la_hipotesis_de_la_asimetria_llega_a_la_traza():
    entrada = _evaluar(EffectiveAreaModel(), qadm=400.0).trace.by_id("contact_pressure")
    texto = " ".join(entrada.hypotheses)
    assert "ÁREA EFECTIVA" in texto
    assert "NO VERIFICADO" in texto


# =========================================================================
# 5. Elegir el modelo nunca empeora un resultado que ya pasaba
# =========================================================================


@pytest.mark.parametrize("Mx", [0.0, 60.0, 150.0, 240.0, 300.0])
def test_dentro_del_nucleo_los_dos_modelos_dan_el_mismo_estado(Mx):
    """Barrido hasta el borde del núcleo (e = 0,50 m ⇒ Mx = 300 con P = 600). Ni un solo
    estado ni un solo número se mueven."""
    a = _evaluar(KernCheckModel(), qadm=400.0, Mx=Mx)
    b = _evaluar(EffectiveAreaModel(), qadm=400.0, Mx=Mx)
    ea, eb = a.trace.by_id("contact_pressure"), b.trace.by_id("contact_pressure")
    assert ea.status is eb.status
    assert ea.result_value == pytest.approx(eb.result_value, rel=1e-15)
    assert a.contact_pressure.qmax_kPa == pytest.approx(b.contact_pressure.qmax_kPa, rel=1e-15)
    assert a.overall_status is b.overall_status


def test_el_modelo_por_defecto_no_cambia_y_no_publica_los_campos_del_articulo_28():
    """Con `KernCheckModel` los tres campos nuevos valen None, de modo que no añaden
    ninguna clave al congelamiento (`OPTIONAL_WHEN_NONE_FIELDS`)."""
    r = KernCheckModel().compute(3.00, 2.40, 600.0, 0.30, 0.0)
    assert r.B_eff_m is None and r.L_eff_m is None
    assert r.qadm_declared_for_effective_area is None
    assert r.uses_effective_area is False
    assert r.usable is r.within_kern


def test_los_campos_del_articulo_28_si_se_congelan_cuando_existen():
    """La contrapartida: si el modelo los produce, entran en la instantánea como contrato
    duro. `OPTIONAL_WHEN_NONE_FIELDS` los omite solo cuando valen None."""
    from tests.freeze.snapshot import OPTIONAL_WHEN_NONE_FIELDS, snapshot_candidate

    for campo in ("B_eff_m", "L_eff_m", "qadm_declared_for_effective_area"):
        assert ("ContactPressureResult", campo) in OPTIONAL_WHEN_NONE_FIELDS

    con_area = snapshot_candidate(_evaluar(EffectiveAreaModel(), qadm=400.0))
    con_nucleo = snapshot_candidate(_evaluar(KernCheckModel(), qadm=400.0))
    nuevas = set(con_area["numeros"]) - set(con_nucleo["numeros"])
    assert nuevas == {
        "contact_pressure.B_eff_m",
        "contact_pressure.L_eff_m",
        "contact_pressure.qadm_declared_for_effective_area",
    }, nuevas
    # Y nada más: la declaración del punzonamiento con contacto parcial aparece en los DOS
    # modelos —depende de la excentricidad de diseño, no del modelo—, de modo que no
    # figura entre las diferencias.


# =========================================================================
# 6. La API lo expone, y apagado por defecto
# =========================================================================


def test_la_api_usa_el_nucleo_central_salvo_que_se_pida_lo_contrario():
    from api import mapping, schemas

    por_defecto = mapping.contact_model_for(schemas.SoilInput())
    assert isinstance(por_defecto, KernCheckModel)

    pedido = mapping.contact_model_for(
        schemas.SoilInput(use_effective_area_e050_art28=True)
    )
    assert isinstance(pedido, EffectiveAreaModel)
    assert pedido.qadm_declared_for_effective_area is False

    declarado = mapping.contact_model_for(
        schemas.SoilInput(
            use_effective_area_e050_art28=True, qadm_declared_for_effective_area=True
        )
    )
    assert declarado.qadm_declared_for_effective_area is True


def test_todos_los_endpoints_construyen_el_modelo_por_el_mismo_sitio():
    """Si un endpoint se quedara con `KernCheckModel()` a mano, una tipología perdería la
    opción sin que nadie lo notara. Es el defecto de paridad que la auditoría del
    2026-09-19 encontró con §15.7, y aquí se cierra de antemano."""
    import inspect

    from api import server

    fuente = inspect.getsource(server)
    assert "KernCheckModel()" not in fuente, (
        "Ningún endpoint debe instanciar el modelo por su cuenta: usa mapping.contact_model_for"
    )
    assert fuente.count("mapping.contact_model_for(") == 5


# =========================================================================
# 7. El punzonamiento: alivio integrado sobre el campo de contacto unilateral
# =========================================================================


def test_el_alivio_del_punzonamiento_se_integra_sobre_el_campo_de_contacto():
    """Riesgo MEDIDO al implementar el bloque triangular, y CERRADO en dos pasos.

    El alivio del suelo bajo la sección crítica salía de la forma cerrada del campo LINEAL,
    que fuera del núcleo no existe: el alivio lineal resultaba MAYOR y Vu quedaba
    subestimado hasta un 1,4 %.

    El 2026-09-20 se integró primero el campo real y después —decisión 1— se sustituyó la
    superposición por el CONTACTO UNILATERAL resuelto por equilibrio:

        Vu = Pu − ∫∫(A_crit) q⁺(x, y) dA,   q⁺ = max(a + b·u + c·v, 0)

    Es el mismo campo que usan la flexión y el cortante. Detalle en
    `tests/test_contacto_unilateral.py` y `docs/freeze_contacto_unilateral.md`."""
    r = _evaluar(EffectiveAreaModel(qadm_declared_for_effective_area=True), qadm=400.0)
    punz = r.punching
    campo = _campo_de_diseno()
    esperado = campo.force_over_rectangle(*_rectangulo_critico(r.d_m))
    assert punz.Vu_kN == pytest.approx(_pu_punz() - esperado, rel=1e-12)

    # Y el alivio lineal, el que se usaba antes, es MAYOR: Vu quedaba subestimado.
    qu_avg = _pu_punz() / (3.00 * 2.40)
    x_lo, x_hi, y_lo, y_hi = _rectangulo_critico(r.d_m)
    area = (x_hi - x_lo) * (y_hi - y_lo)
    cx = (x_hi + x_lo) / 2.0
    alivio_lineal = qu_avg * (1.0 + 12.0 * 0.70 * cx / 3.00**2) * area
    assert alivio_lineal > esperado


def test_el_campo_del_area_efectiva_es_el_mismo_que_el_de_siempre():
    """El modelo de contacto que elija el proyectista NO cambia la física del diseño.

    `EffectiveAreaModel` es un criterio sobre la CAPACIDAD PORTANTE del suelo (E.050
    art. 28), no sobre la distribución de presiones con que se dimensiona el concreto. El
    campo de diseño lo fijan las cargas factorizadas y la geometría, y es el mismo se elija
    el modelo que se elija."""
    con_area = _evaluar(EffectiveAreaModel(qadm_declared_for_effective_area=True), qadm=400.0)
    con_nucleo = _evaluar(KernCheckModel(), qadm=400.0)
    assert con_area.punching.Vu_kN == pytest.approx(con_nucleo.punching.Vu_kN, rel=1e-12)
    assert con_area.flexure_x.Mu_kNm == pytest.approx(con_nucleo.flexure_x.Mu_kNm, rel=1e-12)


def test_la_limitacion_del_punzonamiento_se_retiro_al_resolverse():
    """La declaración desapareció porque el hueco se cerró, no porque estorbara.

    `punching_partial_contact` (2026-09-19) → `punching_biaxial_uplift` (estrechada el
    2026-09-20) → **retirada** el mismo día, cuando el contacto unilateral pasó a
    equilibrar por construcción. Que ya no exista es la afirmación."""
    from engine.results.limitations import limitation_by_id

    for retirada in ("punching_partial_contact", "punching_biaxial_uplift"):
        with pytest.raises(KeyError):
            limitation_by_id(retirada)

    r = _evaluar(EffectiveAreaModel(), qadm=400.0)
    ids = {e.id for e in r.trace.entries}
    assert "punching_biaxial_uplift" not in ids
    assert "punching_partial_contact" not in ids


def _pu_punz(P: float = 600.0) -> float:
    """La combinación factorizada de `_cargas`: la única, de modo que gobierna."""
    return P * 1.4


def _campo_de_diseno(P: float = 600.0, Mx: float = 420.0):
    """El campo de diseño, reconstruido a mano desde las cargas del test.

    La excentricidad de diseño se mide con las cargas FACTORIZADAS y SIN peso propio, que
    es lo que hace el solver: 588/840 = 0,70 m sobre B = 3,00 m, fuera del núcleo."""
    from engine.foundation.unilateral_contact import solve_unilateral_contact

    P_u, Mu = P * 1.4, Mx * 1.4
    return solve_unilateral_contact(P_u, 3.00, 2.40, Mu / P_u, 0.0)


def _rectangulo_critico(d_m: float) -> tuple[float, float, float, float]:
    from engine.foundation.critical_section import build_critical_section

    s = build_critical_section(3.00, 2.40, COL.bx_m, COL.by_m, d_m)
    return s.x_lo_m, s.x_hi_m, s.y_lo_m, s.y_hi_m
