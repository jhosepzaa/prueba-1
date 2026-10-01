"""Rangos de búsqueda automáticos para la zapata COMBINADA y la CONECTADA (2026-09-28).

QUÉ ES Y QUÉ NO ES
==================
Una HEURÍSTICA DE BÚSQUEDA, hermana de `engine/foundation/auto_search_range.py` (la de la
aislada): acota dónde mirar, no decide nada de diseño. Toda geometría del rango se verifica
con las mismas ecuaciones y los mismos criterios que si el proyectista la hubiera escrito a
mano. Un rango mal elegido se nota —no aparecen alternativas, o la mejor queda contra un
borde del rango—, nunca produce una alternativa inválida. No proviene de ninguna norma y
así se dice en la nota que acompaña al resultado.

CRITERIO
========
El área en planta se estima con el equilibrio elemental, sobre la presión DISPONIBLE (qadm
en base neta, con la misma conversión que el verificador):

    A ≈ P_servicio_máx / q_disponible

y el rango se abre con generosidad alrededor de ella, porque la excentricidad, el sismo y
el peso propio empujan hacia arriba (con el sismo del problema 2 de Aragón, la zapata
exterior aceptada tiene casi el doble del área A estimada). Los linderos recortan el rango:
la zapata no puede salir del terreno. El incremento se agranda cuando hace falta para que
la malla quepa en el presupuesto del barrido —más vale recorrer todo el rango con paso
grueso que la mitad con paso fino— y se dice.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from engine.domain.site_limits import SiteLimits
from engine.domain.soil import PressureBasis, SoilProfile
from engine.soil.pressure_basis import convert_pressure

if TYPE_CHECKING:  # pragma: no cover
    from engine.domain.connected_layout import ConnectedFootingLayout
    from engine.optimization.combined_generator import ColumnSpec

# Cotas de sentido común (m), no normativas: evitan mallas absurdas.
DIM_MAX_M = 15.0
H_MIN_M = 0.50
H_MAX_M = 2.50
LADDER_M = (0.10, 0.20, 0.25, 0.50, 1.00)
H_LADDER_M = (0.05, 0.10, 0.20)


def _redondear_arriba(v: float, paso: float) -> float:
    return math.ceil(v / paso - 1e-9) * paso


def _redondear_abajo(v: float, paso: float) -> float:
    return math.floor(v / paso + 1e-9) * paso


def _puntos(lo: float, hi: float, paso: float) -> int:
    return int(round((hi - lo) / paso)) + 1 if hi >= lo else 0


def _presion_disponible(soil: SoilProfile) -> float:
    return convert_pressure(
        soil.qadm_kPa, soil.pressure_basis, PressureBasis.NETA, soil.gamma_kNm3, soil.Df_m
    )


def _rango(lo: float, hi: float, paso: float) -> tuple[float, float]:
    lo = max(_redondear_abajo(lo, paso), paso)
    hi = max(_redondear_arriba(hi, paso), lo)
    return round(lo, 6), round(hi, 6)


def _ajustar_pasos(ejes: list[tuple[float, float]], presupuesto: int) -> list[float]:
    """El paso más fino de la escala, igual para los ejes en planta, que deja el producto
    de puntos dentro del presupuesto."""
    for paso in LADDER_M:
        total = 1
        for lo, hi in ejes:
            total *= max(_puntos(_redondear_abajo(lo, paso), _redondear_arriba(hi, paso), paso), 1)
        if total <= presupuesto:
            return [paso] * len(ejes)
    return [LADDER_M[-1]] * len(ejes)


def _peralte(h_hi: float, Df: float, grueso: bool = False) -> tuple[float, float, float]:
    """Peralte de 0,50 m hasta una fracción del lado, sin pasar de Df: la cara superior de
    la zapata no puede quedar por encima del terreno. En la pasada gruesa, cada 0,20 m."""
    tope = min(H_MAX_M, max(Df, H_MIN_M + 0.30)) if Df > 0 else H_MAX_M
    hi = min(max(h_hi, 1.20), tope)
    paso = 0.20 if grueso else (0.10 if hi - H_MIN_M > 1.0 else 0.05)
    lo, hi = H_MIN_M, round(_redondear_arriba(hi, paso), 6)
    return lo, hi, paso


# =========================================================================
# Zapata combinada
# =========================================================================

def estimate_combined_search(
    specs: "list[ColumnSpec]",
    soil: SoilProfile,
    longitudinal_direction: str,
    limits: SiteLimits | None,
    presupuesto: int,
    grueso: bool = False,
) -> tuple[dict, str]:
    """Rango de longitud, ancho y peralte para la zapata combinada.

    `grueso`: primera pasada de la búsqueda en dos pasadas, con el peralte a 0,20 m.

    Devuelve los campos de `CombinedSearchParameters` (sin la posición, que la decide el
    generador) y la nota que lo explica."""
    X = longitudinal_direction == "X"

    def semi(sp) -> tuple[float, float]:
        return (sp.column.bx_m / 2, sp.column.by_m / 2) if X else (sp.column.by_m / 2, sp.column.bx_m / 2)

    n_combos = len(specs[0].loads.service)
    P_max = max((sum(sp.loads.service[i].P_kN for sp in specs) for i in range(n_combos)), default=0.0)
    q = _presion_disponible(soil)
    A = P_max / q if (P_max > 0 and q > 0) else 0.0

    primera = specs[0]
    ultima = max(specs, key=lambda sp: sp.distance_from_first_m)
    cubre = ultima.distance_from_first_m + semi(ultima)[0] + semi(primera)[0]
    caras_neg = min(sp.transverse_offset_m - semi(sp)[1] for sp in specs)
    caras_pos = max(sp.transverse_offset_m + semi(sp)[1] for sp in specs)
    ancho_columnas = caras_pos - caras_neg

    L_lo = cubre + 0.20
    L_hi = max(L_lo + 2.0, cubre + 2.0 * max(1.0, 0.75 * math.sqrt(A)))
    if limits is not None and limits.start_clearance_m is not None and limits.end_clearance_m is not None:
        L_hi = min(L_hi, cubre + limits.start_clearance_m + limits.end_clearance_m)
        L_lo = min(L_lo, L_hi)
    L_hi = min(L_hi, DIM_MAX_M)

    W_lo = max(ancho_columnas + 0.20, 0.60 * A / L_hi if A else 0.0)
    W_hi = max(W_lo + 1.0, 1.60 * A / max(L_lo, 1.0) if A else W_lo + 2.0)
    if limits is not None and limits.side_neg_clearance_m is not None and limits.side_pos_clearance_m is not None:
        W_hi = min(W_hi, ancho_columnas + limits.side_neg_clearance_m + limits.side_pos_clearance_m)
        W_lo = min(W_lo, W_hi)
    W_hi = min(W_hi, DIM_MAX_M)

    h_lo, h_hi, h_paso = _peralte(0.25 * W_hi + 0.30, soil.Df_m, grueso)
    n_h = _puntos(h_lo, h_hi, h_paso)
    paso_L, paso_W = _ajustar_pasos([(L_lo, L_hi), (W_lo, W_hi)], max(presupuesto // max(n_h, 1), 1))
    L_lo, L_hi = _rango(L_lo, L_hi, paso_L)
    W_lo, W_hi = _rango(W_lo, W_hi, paso_W)

    campos = dict(
        length_min_m=L_lo, length_max_m=L_hi, length_step_m=paso_L,
        width_min_m=W_lo, width_max_m=W_hi, width_step_m=paso_W,
        h_min_m=h_lo, h_max_m=h_hi, h_step_m=h_paso,
    )
    nota = (
        f"Rango de búsqueda estimado por el programa: A ≈ ΣP/q_disponible = {P_max:.1f}/{q:.1f} "
        f"= {A:.2f} m². Longitud de {L_lo:.2f} a {L_hi:.2f} m (paso {paso_L:.2f}), ancho de "
        f"{W_lo:.2f} a {W_hi:.2f} m (paso {paso_W:.2f}), peralte de {h_lo:.2f} a {h_hi:.2f} m "
        f"(paso {h_paso:.2f})"
        + (", recortados por los linderos" if limits is not None else "")
        + ". Heurística de búsqueda, no criterio de diseño: cada geometría se verifica con los "
        "mismos criterios normativos. Si la mejor alternativa queda contra un borde del rango, "
        "ajústelo a mano."
    )
    return campos, nota


# =========================================================================
# Zapata conectada
# =========================================================================

def estimate_connected_search(
    layout: "ConnectedFootingLayout",
    soil: SoilProfile,
    limits: SiteLimits | None,
    presupuesto: int,
    grueso: bool = False,
) -> tuple[dict, str]:
    """Rango de las dos plantas y del peralte para la conectada.

    Las zapatas de la conectada se modelan centradas lateralmente sobre su columna, de modo
    que un lindero lateral limita el ANCHO a la columna más dos veces la holgura menor."""
    X = layout.longitudinal_axis == "X"

    def dims(el) -> tuple[float, float]:
        c = el.column
        return (c.bx_m, c.by_m) if X else (c.by_m, c.bx_m)

    def p_max(el) -> float:
        return max((c.P_kN for c in el.loads.service), default=0.0)

    q = _presion_disponible(soil)
    A_e = p_max(layout.exterior) / q if q > 0 else 0.0
    A_i = p_max(layout.interior) / q if q > 0 else 0.0
    (el_col, et_col), (il_col, it_col) = dims(layout.exterior), dims(layout.interior)
    holgura_lindero = layout.exterior.anchor.face_clearance_m if layout.exterior.anchor else 0.0

    lado_e, lado_i = math.sqrt(A_e), math.sqrt(A_i)
    # Exterior: corta sobre la viga (menos excentricidad), ancha en la transversal.
    el_lo = el_col + holgura_lindero + 0.30
    el_hi = max(el_lo + 1.0, 1.6 * lado_e)
    et_lo = max(et_col + 0.40, 0.6 * lado_e)
    et_hi = max(et_lo + 1.0, 2.2 * lado_e)
    # Interior: sin restricción de forma de partida.
    il_lo = max(il_col + 0.40, 0.6 * lado_i)
    il_hi = max(il_lo + 1.0, 2.2 * lado_i)
    it_lo = max(it_col + 0.40, 0.6 * lado_i)
    it_hi = max(it_lo + 1.0, 2.2 * lado_i)

    # Que la interior no invada la exterior de partida: su mitad sobre la viga cabe entre
    # los ejes menos la zapata exterior más corta.
    a = holgura_lindero + el_col / 2.0
    il_hi = min(il_hi, max(il_lo, 2.0 * (layout.axis_distance_m + a - el_lo)))

    notas_linderos = []
    if limits is not None:
        laterales = [v for v in (limits.side_neg_clearance_m, limits.side_pos_clearance_m) if v is not None]
        if laterales:
            menor = min(laterales)
            et_hi = min(et_hi, et_col + 2.0 * menor)
            it_hi = min(it_hi, it_col + 2.0 * menor)
            et_lo, it_lo = min(et_lo, et_hi), min(it_lo, it_hi)
            notas_linderos.append(
                "los linderos laterales limitan el ancho de cada zapata a su columna más dos "
                "veces la holgura menor, porque el modelo de la conectada las supone centradas "
                "sobre su columna en la dirección transversal"
            )
        if limits.end_clearance_m is not None:
            il_hi = min(il_hi, il_col + 2.0 * limits.end_clearance_m)
            il_lo = min(il_lo, il_hi)
            notas_linderos.append("el lindero del fondo limita el largo de la zapata interior")

    el_hi, et_hi, il_hi, it_hi = (min(v, DIM_MAX_M) for v in (el_hi, et_hi, il_hi, it_hi))

    h_lo, h_hi, h_paso = _peralte(0.30 * max(el_hi, it_hi, il_hi), soil.Df_m, grueso)
    n_h = _puntos(h_lo, h_hi, h_paso)
    pasos = _ajustar_pasos(
        [(el_lo, el_hi), (et_lo, et_hi), (il_lo, il_hi), (it_lo, it_hi)],
        max(presupuesto // max(n_h, 1), 1),
    )
    (el_lo, el_hi), (et_lo, et_hi), (il_lo, il_hi), (it_lo, it_hi) = (
        _rango(lo, hi, p) for (lo, hi), p in zip(
            [(el_lo, el_hi), (et_lo, et_hi), (il_lo, il_hi), (it_lo, it_hi)], pasos)
    )
    campos = dict(
        ext_long_min_m=el_lo, ext_long_max_m=el_hi, ext_long_step_m=pasos[0],
        ext_transv_min_m=et_lo, ext_transv_max_m=et_hi, ext_transv_step_m=pasos[1],
        int_long_min_m=il_lo, int_long_max_m=il_hi, int_long_step_m=pasos[2],
        int_transv_min_m=it_lo, int_transv_max_m=it_hi, int_transv_step_m=pasos[3],
        h_min_m=h_lo, h_max_m=h_hi, h_step_m=h_paso,
    )
    nota = (
        f"Rango de búsqueda estimado por el programa: A_ext ≈ {A_e:.2f} m² y A_int ≈ {A_i:.2f} m² "
        f"(P de servicio máxima / q_disponible = {q:.1f} kPa). Exterior {el_lo:.2f}–{el_hi:.2f} m "
        f"sobre la viga × {et_lo:.2f}–{et_hi:.2f} m; interior {il_lo:.2f}–{il_hi:.2f} × "
        f"{it_lo:.2f}–{it_hi:.2f} m; paso {pasos[0]:.2f} m; peralte {h_lo:.2f}–{h_hi:.2f} m"
        + (". " + "; ".join(notas_linderos).capitalize() if notas_linderos else "")
        + ". Heurística de búsqueda, no criterio de diseño: cada terna se verifica con los "
        "mismos criterios normativos. Si la mejor alternativa queda contra un borde del rango, "
        "ajústelo a mano."
    )
    return campos, nota


# =========================================================================
# Búsqueda automática en DOS pasadas (2026-09-28)
# =========================================================================
#
# Un rango automático tiene que ser ancho —no se sabe dónde está la solución— y un rango
# ancho con presupuesto acotado obliga a un paso grueso. Medido en el problema 2 de Aragón:
# paso de 1,00 m, 46 660 ternas y la mejor contra el borde del rango. La segunda pasada
# resuelve las dos cosas: toma la mejor alternativa de la primera y barre alrededor de ella
# con paso fino, un paso grueso a cada lado, lo que además la saca del borde si había
# quedado en él. Sigue siendo búsqueda: la óptima lo es dentro de lo explorado, y el aviso
# de borde lo sigue diciendo.

PASOS_FINOS_M = (0.05, 0.10, 0.20, 0.25, 0.50)
PRESUPUESTO_GRUESO = 2500
PRESUPUESTO_FINO = 3000


def refine_around(
    campos: dict, centro: dict[str, float], ejes: list[str], presupuesto: int, h_tope: float
) -> dict:
    """Rango fino alrededor de `centro`: un paso grueso a cada lado de cada eje, con el paso
    más fino de la escala que cabe en el presupuesto. El peralte se afina a 0,05 m."""
    h_p = campos["h_step_m"]
    h_lo = max(H_MIN_M, centro["h"] - h_p)
    h_hi = min(max(centro["h"] + h_p, h_lo), h_tope)
    n_h = _puntos(h_lo, h_hi, 0.05)
    for paso in PASOS_FINOS_M:
        nuevos, total = {}, n_h
        for eje in ejes:
            grueso = campos[f"{eje}_step_m"]
            lo = _redondear_abajo(max(centro[eje] - grueso, paso), paso)
            hi = _redondear_arriba(min(centro[eje] + grueso, DIM_MAX_M), paso)
            nuevos.update({f"{eje}_min_m": round(lo, 6), f"{eje}_max_m": round(hi, 6), f"{eje}_step_m": paso})
            total *= _puntos(lo, hi, paso)
        if total <= presupuesto or paso == PASOS_FINOS_M[-1]:
            nuevos.update(h_min_m=round(h_lo, 6), h_max_m=round(_redondear_arriba(h_hi, 0.05), 6), h_step_m=0.05)
            return {**campos, **nuevos}
    return campos  # pragma: no cover


def _nota_refino(campos: dict, ejes: list[str]) -> str:
    return (
        " Segunda pasada, alrededor de la mejor de la primera, con paso "
        f"{campos[f'{ejes[0]}_step_m']:.2f} m en planta y 0,05 m en peralte."
    )


def auto_connected_search(layout, soil, limits, ejecutar, rank) -> tuple[object, str]:
    """Búsqueda automática de la conectada: estimación, pasada gruesa y pasada fina.

    `ejecutar(campos)` corre un barrido con esos rangos y devuelve el conjunto;
    `rank(aceptadas)` las ordena (el mismo ordenamiento que presenta la API). Si la pasada
    fina no encuentra nada —no debería, porque contiene a la mejor de la gruesa en su
    vecindad— se devuelve la gruesa."""
    campos, nota = estimate_connected_search(layout, soil, limits, PRESUPUESTO_GRUESO, grueso=True)
    grueso = ejecutar(campos)
    if not grueso.accepted:
        return grueso, nota + " La pasada gruesa no encontró alternativas y no se refinó."
    g = rank(grueso.accepted)[0].alternative.geometry
    X = layout.longitudinal_axis == "X"
    centro = {
        "ext_long": g.exterior_B_m if X else g.exterior_L_m,
        "ext_transv": g.exterior_L_m if X else g.exterior_B_m,
        "int_long": g.interior_B_m if X else g.interior_L_m,
        "int_transv": g.interior_L_m if X else g.interior_B_m,
        "h": g.exterior_h_m,
    }
    ejes = ["ext_long", "ext_transv", "int_long", "int_transv"]
    fino_campos = refine_around(campos, centro, ejes, PRESUPUESTO_FINO, campos["h_max_m"] + campos["h_step_m"])
    fino = ejecutar(fino_campos)
    if not fino.accepted:
        return grueso, nota + " La pasada fina no mejoró la gruesa."
    return fino, nota + _nota_refino(fino_campos, ejes)


def auto_combined_search(specs, soil, direction, limits, ejecutar, rank) -> tuple[object, dict, str]:
    """Lo mismo para la combinada. Devuelve el conjunto, los rangos de la pasada que se
    entrega (para el aviso de borde) y la nota."""
    from engine.optimization.combined_generator import MAX_COMBINED_GEOMETRIES

    campos, nota = estimate_combined_search(specs, soil, direction, limits, MAX_COMBINED_GEOMETRIES, grueso=True)
    grueso = ejecutar(campos)
    if not grueso.valid:
        return grueso, campos, nota + " La pasada gruesa no encontró alternativas y no se refinó."
    a = rank(grueso.valid)[0].alternative
    centro = {"length": a.length_m, "width": a.width_m, "h": a.h_m}
    fino_campos = refine_around(
        campos, centro, ["length", "width"], MAX_COMBINED_GEOMETRIES, campos["h_max_m"] + campos["h_step_m"]
    )
    fino = ejecutar(fino_campos)
    if not fino.valid:
        return grueso, campos, nota + " La pasada fina no mejoró la gruesa."
    return fino, fino_campos, nota + _nota_refino(fino_campos, ["length"])
