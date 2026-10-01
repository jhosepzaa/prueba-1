"""FASE 1B — Columna descentrada con perímetro de punzonamiento CERRADO.

ALCANCE DE LA FASE
==================
La columna puede desplazarse respecto del centroide de la zapata mientras su
holgura mínima al borde siga siendo >= d/2, de modo que la sección crítica de
§11.12.1.2 se cierre por los cuatro lados. Por debajo de esa holgura el perímetro
se trunca, y ése es el alcance de la Fase 1C: aquí se rechaza con motivo
explícito en vez de calcularse con un modelo que no le corresponde.

QUÉ SE VERIFICA
===============
1. CONTINUIDAD. Con desplazamiento cero, el camino generalizado debe dar
   exactamente el mismo resultado que antes. Es el requisito de la Fase 1A.
2. La excentricidad geométrica se SUMA a la de carga, con el cociente correcto.
3. Los dos voladizos de cada dirección se evalúan y gobierna el peor — no siempre
   el del lado de mayor presión.
4. La holgura < d/2 se rechaza, y el motivo dice qué hacer.
5. Simetría por reflexión: desplazar +a o -a debe dar resultados espejo.
"""

from __future__ import annotations

import pytest

from engine.codes.peru.e060_concrete import E060ConcreteCode
from engine.domain.column import Column
from engine.domain.column_placement import ColumnPlacement, concentric
from engine.domain.loads import LoadCaseSet, LoadCombination, LoadCombinationType
from engine.domain.materials import MaterialConcrete, MaterialSteel
from engine.domain.search_parameters import DepthSearchParameters
from engine.domain.soil import PressureBasis, SoilProfile
from engine.foundation.depth_solver import evaluate_candidate
from engine.foundation.punching_shear import critical_section_fits_in_footing, punching_demand
from engine.results.status import CheckStatus
from engine.soil.contact_pressure import FullContactModel
from engine.soil.eccentricity import compute_eccentricity, compute_total_eccentricity

CODE = E060ConcreteCode()
CONTACT = FullContactModel()
COLUMNA = Column(shape="cuadrada", bx_m=0.50, by_m=0.50)
B, L, H = 3.20, 3.20, 0.65
PARAMS = DepthSearchParameters(h_min_m=H, h_max_m=H, h_step_m=0.05)


def _soil() -> SoilProfile:
    return SoilProfile(
        qadm_kPa=350.0, pressure_basis=PressureBasis.BRUTA, gamma_kNm3=18.0, Df_m=1.20,
        source_notes="Caso de prueba de columna descentrada.",
    )


def _loads(Mx: float = 0.0, My: float = 0.0, P: float = 900.0) -> LoadCaseSet:
    return LoadCaseSet(
        service=[
            LoadCombination(name="S1", type=LoadCombinationType.SERVICIO, P_kN=P, Mx_kNm=Mx, My_kNm=My)
        ],
        factored=[
            LoadCombination(
                name="U1", type=LoadCombinationType.FACTORIZADA, P_kN=P * 1.4,
                Mx_kNm=Mx * 1.4, My_kNm=My * 1.4,
            )
        ],
    )


def _evaluar(placement: ColumnPlacement | None, loads: LoadCaseSet | None = None, B_m: float = B, L_m: float = L):
    return evaluate_candidate(
        B_m=B_m, L_m=L_m, h_m=H, column=COLUMNA, soil=_soil(),
        concrete=MaterialConcrete(fc_MPa=21.0), steel=MaterialSteel(fy_MPa=420.0),
        load_case_set=loads or _loads(), code=CODE, contact_model=CONTACT,
        depth_params=PARAMS, placement=placement,
    )


# =========================================================================
# 1. Continuidad — el requisito irrenunciable
# =========================================================================

def test_omitir_la_posicion_equivale_a_columna_concentrica():
    """Ninguna llamada existente cambia de resultado por la existencia de la Fase 1B."""
    sin = _evaluar(None)
    con = _evaluar(concentric(COLUMNA))
    assert sin.model_dump() == con.model_dump()


def test_desplazamiento_cero_reproduce_exactamente_el_caso_centrado():
    """El camino generalizado debe DEGENERAR en el anterior, no aproximarlo."""
    centrado = _evaluar(None, _loads(Mx=180.0, My=90.0))
    explicito = _evaluar(
        ColumnPlacement(column=COLUMNA, offset_x_m=0.0, offset_y_m=0.0), _loads(Mx=180.0, My=90.0)
    )
    assert explicito.model_dump() == centrado.model_dump()


def test_la_excentricidad_total_degenera_en_la_de_carga():
    a = compute_total_eccentricity(1000.0, 200.0, 300.0, 60.0)
    b = compute_eccentricity(1200.0, 300.0, 60.0)
    assert (a.ex_m, a.ey_m) == (b.ex_m, b.ey_m)


def test_la_demanda_de_punzonamiento_degenera_con_desplazamiento_cero():
    base = punching_demand(1000.0, 3.0, 3.0, 0.5, 0.5, 0.5)
    con_ecc = punching_demand(1000.0, 3.0, 3.0, 0.5, 0.5, 0.5, ex_m=0.3, ey_m=0.2)
    assert con_ecc == base, "Sin desplazamiento, la excentricidad no debe alterar la resultante"


# =========================================================================
# 2. La excentricidad geométrica se suma a la de carga
# =========================================================================

def test_el_desplazamiento_geometrico_produce_excentricidad_por_si_solo():
    e = compute_total_eccentricity(
        P_column_kN=1000.0, self_weight_kN=200.0, Mx_kNm=0.0, My_kNm=0.0, offset_x_m=0.30
    )
    # Solo la carga DESCENTRADA aporta momento; el peso propio actúa en el centroide.
    assert e.ex_m == pytest.approx(1000.0 * 0.30 / 1200.0)
    assert e.ey_m == pytest.approx(0.0)


def test_el_peso_propio_entra_en_el_denominador_pero_no_en_el_numerador():
    """Es el error fácil de este cálculo: usar la carga total también arriba."""
    sin_peso = compute_total_eccentricity(1000.0, 0.0, 0.0, 0.0, offset_x_m=0.30)
    con_peso = compute_total_eccentricity(1000.0, 500.0, 0.0, 0.0, offset_x_m=0.30)
    assert sin_peso.ex_m == pytest.approx(0.30), "Sin peso propio, ex = offset exacto"
    assert con_peso.ex_m == pytest.approx(1000.0 * 0.30 / 1500.0)
    assert con_peso.ex_m < sin_peso.ex_m, "El peso propio centra la resultante"


def test_momento_y_desplazamiento_se_suman_o_se_cancelan_segun_el_signo():
    suma = compute_total_eccentricity(1000.0, 0.0, 200.0, 0.0, offset_x_m=0.20)
    resta = compute_total_eccentricity(1000.0, 0.0, -200.0, 0.0, offset_x_m=0.20)
    assert suma.ex_m == pytest.approx(0.20 + 0.20)
    assert resta.ex_m == pytest.approx(0.20 - 0.20)
    assert resta.ex_m == pytest.approx(0.0), "Un momento opuesto puede centrar la resultante"


def test_una_columna_descentrada_carga_mas_el_suelo_del_lado_al_que_se_mueve():
    centrada = _evaluar(None)
    movida = _evaluar(ColumnPlacement(column=COLUMNA, offset_x_m=0.40))
    assert movida.contact_pressure.qmax_kPa > centrada.contact_pressure.qmax_kPa
    assert movida.eccentricity_governing.ex_m > centrada.eccentricity_governing.ex_m


# =========================================================================
# 3. Los dos voladizos — riesgo R3 de la auditoría
# =========================================================================

def test_los_voladizos_se_reparten_con_el_desplazamiento():
    p = ColumnPlacement(column=COLUMNA, offset_x_m=0.40)
    izq, der = p.cantilevers_x(B)
    assert izq == pytest.approx((B - 0.50) / 2.0 + 0.40)
    assert der == pytest.approx((B - 0.50) / 2.0 - 0.40)
    assert izq + der == pytest.approx(B - 0.50), "La suma es invariante"


def _excentricidad_de_diseno_x(loads, placement) -> float:
    """|ex| de la combinación FACTORIZADA, que es la que arma el campo de presión de
    diseño: solo carga de columna, sin peso propio (ver `engine/foundation/flexure.py`).
    No es la misma que la de servicio, y confundirlas es justo lo que este par de tests
    existe para impedir."""
    from engine.soil.eccentricity import compute_total_eccentricity

    peor = 0.0
    for combo in loads.factored:
        e = compute_total_eccentricity(
            combo.P_kN, 0.0, combo.Mx_kNm, combo.My_kNm,
            placement.offset_x_m, placement.offset_y_m,
        )
        peor = max(peor, abs(e.ex_m))
    return peor


def test_gobierna_el_voladizo_largo_aunque_este_del_lado_de_menor_presion():
    """RIESGO R3 de la auditoría de Fase 0.

    La columna se desplaza hacia +X, de modo que el voladizo LARGO queda del lado
    x=0. La resultante se desplaza hacia +X —e > 0—, así que la presión alta cae en
    x=B, donde el voladizo es CORTO. El momento debe salir del voladizo largo pese a
    tener menos presión: crece con el CUADRADO de la longitud y solo linealmente con
    la presión.

    Evaluar solo el lado de mayor presión —lo que hacía el motor antes de la Fase
    1B— subestimaría Mu.

    POR QUÉ Mx NEGATIVO (decisión B, 2026-09-19). El desplazamiento de 0,55 m ya es
    mayor que B/6 = 0,533 m por sí solo, de modo que con Mx positivo la resultante se
    sale del núcleo central y la zapata despega: ahí el campo ya no es lineal y el
    voladizo largo cae en parte sobre la zona levantada. Un Mx negativo pequeño
    devuelve la resultante al núcleo sin mover la geometría, que es donde este riesgo
    se enuncia. El caso con despegue se comprueba en el test siguiente."""
    placement = ColumnPlacement(column=COLUMNA, offset_x_m=0.55)
    cargas = _loads(Mx=-40.0)
    cand = _evaluar(placement, cargas)

    izq, der = placement.cantilevers_x(B)
    assert izq > der, "Preparación del caso: el voladizo de x=0 debe ser el largo"
    assert _excentricidad_de_diseno_x(cargas, placement) <= B / 6.0, (
        "El caso se enuncia con contacto total bajo las cargas de DISEÑO"
    )
    # El voladizo que gobierna la flexión X es el LARGO, no el de mayor presión.
    assert cand.flexure_x.cantilever_m == pytest.approx(izq)


def test_con_despegue_puede_gobernar_el_voladizo_CORTO_y_eso_es_correcto():
    """La otra cara del riesgo R3, que apareció al implementar el bloque triangular.

    Con la misma geometría y Mx POSITIVO, la resultante se sale del núcleo: la zapata
    apoya solo sobre `a = 3·(B/2 − e)` medidos desde el borde comprimido, y el voladizo
    largo queda en parte sobre la zona LEVANTADA, donde no recibe nada. Entonces puede
    gobernar el voladizo corto, y no es un error: es lo que exige el equilibrio.

    Antes de la decisión B el motor recortaba a cero las presiones negativas del campo
    lineal y seguía repartiendo carga sobre la zona levantada, de modo que el voladizo
    largo «ganaba» con un momento que no existe.

    Reconstrucción a mano, sin llamar al código que se prueba
    (Pu = 1260 kN, Mx_u = 168 kN·m, offset 0,55 ⇒ e = 0,6833 m sobre B = 3,20 m):

        a    = 3·(1,600 − 0,6833) = 2,7500 m
        q(0) = 2·1260/2,7500      = 916,364 kN/m
        voladizo corto, c = 0,800: M = 264,801 kN·m
        voladizo largo, c = 1,900: M = 169,312 kN·m   (solo carga hasta s = 2,750)

    Los dos valores salen de integrar numéricamente el bloque triangular."""
    placement = ColumnPlacement(column=COLUMNA, offset_x_m=0.55)
    cand = _evaluar(placement, _loads(Mx=120.0))
    izq, der = placement.cantilevers_x(B)

    assert _excentricidad_de_diseno_x(_loads(Mx=120.0), placement) > B / 6.0, (
        "El caso se enuncia CON despegue bajo las cargas de diseño"
    )
    assert cand.contact_pressure.within_kern, (
        "Y la sutileza que hace esto importante: bajo las cargas de SERVICIO la "
        "resultante sí cae en el núcleo. El despegue aparece solo en el campo de DISEÑO, "
        "que usa las cargas factorizadas y no incluye el peso propio. Por eso el defecto "
        "que la decisión B corrige se daba también con el modelo de contacto por defecto."
    )
    assert cand.flexure_x.cantilever_m == pytest.approx(der), (
        "Con despegue gobierna el voladizo corto, que es el que sí está cargado"
    )
    assert cand.flexure_x.Mu_kNm == pytest.approx(264.801, rel=1e-4)


def test_con_columna_concentrica_los_dos_lados_dan_lo_mismo():
    """Control: si los voladizos son iguales, evaluar ambos no cambia nada respecto
    de evaluar uno. Es lo que garantiza la continuidad."""
    cand = _evaluar(None, _loads(Mx=150.0))
    assert cand.flexure_x.cantilever_m == pytest.approx((B - 0.50) / 2.0)


# =========================================================================
# 4. Holgura menor que d/2 — frontera con la Fase 1C
# =========================================================================

def test_la_holgura_exacta_de_d_medios_todavia_cierra_el_perimetro():
    """Frontera determinista: `>= d/2` cierra. Un error de signo aquí rechazaría
    geometrías válidas o, peor, aceptaría truncadas."""
    d = 0.50
    # Holgura derecha = B/2 - offset - bx/2 = 1.60 - offset - 0.25
    offset_exacto = 1.60 - 0.25 - d / 2.0
    assert critical_section_fits_in_footing(B, L, 0.50, 0.50, d, offset_x_m=offset_exacto)
    assert not critical_section_fits_in_footing(B, L, 0.50, 0.50, d, offset_x_m=offset_exacto + 0.01)


def test_holgura_insuficiente_ya_no_se_rechaza_sino_que_se_trunca():
    """ACTUALIZADO EN LA FASE 1C.

    Hasta la Fase 1B este caso se descartaba porque el modelo de sección cerrada no
    le correspondía. Con el perímetro truncado implementado, ya se calcula: la
    columna se clasifica «borde» y la sección pasa a tener 3 lados."""
    cand = _evaluar(ColumnPlacement(column=COLUMNA, offset_x_m=1.15))
    assert cand.punching.critical_section_fits is False, "La sección ya no se cierra"
    assert cand.punching.column_position == "borde"
    assert cand.punching.critical_section_sides == 3
    assert cand.punching.alpha_s == 30.0
    assert cand.punching.phi_Vc_kN > 0.0, "Ahora sí hay una resistencia calculada"


def test_la_traza_declara_la_posicion_tambien_cuando_es_concentrica():
    """Si la traza callara la posición, el lector tendría que suponerla."""
    for placement in (None, ColumnPlacement(column=COLUMNA, offset_x_m=0.35)):
        entrada = _evaluar(placement).trace.by_id("column_placement")
        assert entrada is not None
        assert entrada.status is CheckStatus.INFO
        assert "holgura mínima" in entrada.equation_substituted


def test_la_columna_fuera_de_la_zapata_es_un_error_no_un_resultado():
    with pytest.raises(ValueError, match="SOBRESALE de la"):
        _evaluar(ColumnPlacement(column=COLUMNA, offset_x_m=2.0))


def test_el_voladizo_nulo_es_valido_es_la_zapata_de_lindero():
    """ACTUALIZADO EN LA FASE 1C. Una cara de columna al ras del borde deja voladizo
    cero de ese lado: es la zapata de límite de propiedad, perfectamente válida. El
    diseño lo gobierna el otro voladizo."""
    al_ras = (B - COLUMNA.bx_m) / 2.0
    cand = _evaluar(ColumnPlacement(column=COLUMNA, offset_x_m=al_ras))
    izq, der = ColumnPlacement(column=COLUMNA, offset_x_m=al_ras).cantilevers_x(B)
    assert der == pytest.approx(0.0)
    assert cand.flexure_x.cantilever_m == pytest.approx(izq), "Gobierna el voladizo que existe"
    assert cand.punching.column_position == "borde"


# =========================================================================
# 5. Simetría por reflexión
# =========================================================================

@pytest.mark.parametrize("offset", [0.20, 0.45, 0.70])
def test_reflejar_el_desplazamiento_y_el_momento_da_el_mismo_resultado(offset: float):
    """Desplazar +a con +Mx debe ser el espejo de desplazar -a con -Mx. Cualquier
    asimetría oculta en el tratamiento de signos aparece aquí."""
    directo = _evaluar(ColumnPlacement(column=COLUMNA, offset_x_m=offset), _loads(Mx=140.0))
    espejo = _evaluar(ColumnPlacement(column=COLUMNA, offset_x_m=-offset), _loads(Mx=-140.0))

    assert espejo.contact_pressure.qmax_kPa == pytest.approx(directo.contact_pressure.qmax_kPa)
    assert espejo.contact_pressure.qmin_kPa == pytest.approx(directo.contact_pressure.qmin_kPa)
    assert espejo.flexure_x.Mu_kNm == pytest.approx(directo.flexure_x.Mu_kNm)
    assert espejo.shear_x.Vu_kN == pytest.approx(directo.shear_x.Vu_kN)
    assert espejo.punching.Vu_kN == pytest.approx(directo.punching.Vu_kN)
    assert espejo.eccentricity_governing.ex_m == pytest.approx(-directo.eccentricity_governing.ex_m)


def test_desplazar_en_X_o_en_Y_da_las_mismas_solicitaciones():
    """Con B = L y columna cuadrada, desplazar en X o en Y produce las mismas
    SOLICITACIONES con las direcciones intercambiadas."""
    en_x = _evaluar(ColumnPlacement(column=COLUMNA, offset_x_m=0.40))
    en_y = _evaluar(ColumnPlacement(column=COLUMNA, offset_y_m=0.40))

    assert en_y.contact_pressure.qmax_kPa == pytest.approx(en_x.contact_pressure.qmax_kPa)
    assert en_y.contact_pressure.qmin_kPa == pytest.approx(en_x.contact_pressure.qmin_kPa)
    assert en_y.eccentricity_governing.ey_m == pytest.approx(en_x.eccentricity_governing.ex_m)
    assert en_y.flexure_y.Mu_kNm == pytest.approx(en_x.flexure_x.Mu_kNm)
    # El cortante y el punzonamiento NO entran aquí: ambos dependen de `d`
    # (sección crítica a d de la cara; A_crit = (bx+d)(by+d)), y `d` no es simétrico
    # en X<->Y. Ver el test siguiente.


def test_el_peralte_efectivo_NO_es_simetrico_en_X_e_Y_y_es_correcto_que_no_lo_sea():
    """La parrilla tiene dos capas y la convención del motor pone la de la dirección
    X ABAJO (ver rebar_geometry.py). Las dos capas no están al mismo nivel, así que
    la zapata no es simétrica en X<->Y aunque B = L.

    Desplazar en X carga más la dirección X, cuya barra va en la capa INFERIOR;
    desplazar en Y carga más la que va en la SUPERIOR. Una barra mayor cuesta más
    peralte abajo que arriba, de modo que el `d` resultante difiere.

    Se deja escrito porque la tentación de «arreglar» esta asimetría es real, y
    hacerlo rompería la convención de capas, que sí está justificada: la dirección
    del lado largo recibe el mayor momento y conviene darle el mayor peralte."""
    en_x = _evaluar(ColumnPlacement(column=COLUMNA, offset_x_m=0.40))
    en_y = _evaluar(ColumnPlacement(column=COLUMNA, offset_y_m=0.40))

    assert en_x.d_m != pytest.approx(en_y.d_m), (
        "Si estos d coincidieran, o bien la convención de capas dejó de aplicarse, "
        "o bien el peralte efectivo dejó de depender del diámetro realmente seleccionado."
    )
    # El de la capa inferior sí debe coincidir: es el mismo nivel en ambos casos.
    assert en_x.rebar_geometry.layer_x.layer == "inferior"
    assert en_y.rebar_geometry.layer_x.layer == "inferior"
    # Y la diferencia debe ser del orden de medio diámetro de barra, no mayor.
    assert abs(en_x.d_m - en_y.d_m) < 0.020

    # Todo lo que depende de `d` hereda esa asimetría, y es correcto que lo haga:
    # la sección crítica de cortante está a `d` de la cara y A_crit = (bx+d)(by+d).
    assert en_x.shear_x.Vu_kN != pytest.approx(en_y.shear_y.Vu_kN)
    assert en_x.punching.Vu_kN != pytest.approx(en_y.punching.Vu_kN)
    # Pero la diferencia debe ser pequeña: es un efecto de segundo orden, no un
    # cambio de comportamiento.
    assert abs(en_x.punching.Vu_kN - en_y.punching.Vu_kN) / en_x.punching.Vu_kN < 0.01


# =========================================================================
# 6. Punzonamiento: la descarga del suelo con columna descentrada
# =========================================================================

def test_la_descarga_usa_la_presion_en_el_centroide_de_la_columna():
    """DERIVACIÓN de la Fase 1B: con la columna descentrada la presión media deja de
    dar la resultante exacta; hay que usar la del centroide de la columna."""
    Pu, B_m, L_m, bx, by, d = 1000.0, 3.0, 3.0, 0.5, 0.5, 0.5
    ax, ex = 0.40, 0.40
    obtenido = punching_demand(Pu, B_m, L_m, bx, by, d, offset_x_m=ax, ex_m=ex)

    q_avg = Pu / (B_m * L_m)
    q_col = q_avg * (1.0 + 12.0 * ex * ax / B_m**2)
    esperado = Pu - q_col * (bx + d) * (by + d)
    assert obtenido == pytest.approx(esperado)


def test_la_escena_3d_dibuja_la_columna_donde_esta():
    """El 3D visualiza datos calculados: si la columna está descentrada, debe verse
    descentrada. Una vista que la centrara siempre mostraría una geometría distinta
    de la que se calculó."""
    from engine.visualization.scene_dto import build_footing_scene

    cand = _evaluar(ColumnPlacement(column=COLUMNA, offset_x_m=0.45, offset_y_m=-0.20))
    escena = build_footing_scene(
        alternative_id="ALT-001", status=cand.overall_status,
        B_m=B, L_m=L, h_m=H, d_m=cand.d_m, cover_m=0.07,
        column_bx_m=0.50, column_by_m=0.50,
        rebar_geometry=cand.rebar_geometry,
        designation_x=cand.rebar_x.bar_designation, designation_y=cand.rebar_y.bar_designation,
        label_x="x", label_y="y",
        column_offset_x_m=0.45, column_offset_y_m=-0.20,
    )
    assert escena.column.center.x == pytest.approx(0.45)
    assert escena.column.center.y == pytest.approx(-0.20)
    # Y la zapata sigue centrada en el origen: lo que se movió es la columna.
    assert escena.footing.center.x == pytest.approx(0.0)


def test_moverse_hacia_la_presion_alta_descarga_mas_la_seccion_critica():
    comun = dict(P_u_column_kN=1000.0, B_m=3.0, L_m=3.0, bx_m=0.5, by_m=0.5, d_m=0.5)
    a_favor = punching_demand(**comun, offset_x_m=0.40, ex_m=0.40)
    en_contra = punching_demand(**comun, offset_x_m=0.40, ex_m=-0.40)
    centrada = punching_demand(**comun)
    assert a_favor < centrada < en_contra
