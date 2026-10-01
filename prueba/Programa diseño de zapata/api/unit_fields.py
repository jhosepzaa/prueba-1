"""Qué campo de cada petición está expresado en qué magnitud.

POR QUÉ EXISTE ESTE MAPA
El usuario elige las unidades en que quiere escribir y leer sus datos. Cuando las
cambia, los números que ya escribió tienen que convertirse: 21 MPa pasan a 214,14
kgf/cm², y el valor FÍSICO no cambia. Para eso hay que saber qué campo es una
fuerza, cuál una longitud y cuál no tiene unidad.

Ese conocimiento estaba disperso en `api/mapping.py` y `api/server.py`, en cada
llamada a `length_to_m(...)`. Aquí queda enumerado en un solo sitio y, sobre todo,
queda AUDITADO: `tests/test_api_unit_fields.py` comprueba que todo campo numérico
de cada petición está o bien en el mapa de magnitudes, o bien en la lista de
exentos con su motivo escrito. Un campo nuevo que nadie clasifique rompe el test,
en vez de convertirse en silencio o quedarse sin convertir.

NO DECIDE NADA DE INGENIERÍA: solo dice en qué unidad viene un número. La tabla de
equivalencias sigue siendo única y vive en `engine/units/unit_registry.py`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from engine.units.unit_registry import convert_for_display

# Cargas de una columna, en los dos modos de entrada (§9 de CLAUDE.md).
_CARGAS = {
    "P_kN": "force",
    "Mx_kNm": "moment",
    "My_kNm": "moment",
    "Hx_kN": "force",
    "Hy_kN": "force",
}


def _con_prefijo(prefijo: str, campos: dict[str, str]) -> dict[str, str]:
    return {f"{prefijo}.{k}": v for k, v in campos.items()}


def _bloque_cargas(prefijo: str) -> dict[str, str]:
    """Combinaciones directas y casos sin factorizar cuelgan del mismo sitio."""
    return {
        **_con_prefijo(f"{prefijo}combinations[]", _CARGAS),
        **_con_prefijo(f"{prefijo}load_cases[]", _CARGAS),
    }


_MATERIALES = {
    "materials.fc_MPa": "strength",
    "materials.fy_MPa": "strength",
    "materials.concrete_unit_weight_kNm3": "unit_weight",
}

_SUELO = {
    "soil.qadm_kPa": "pressure",
    "soil.gamma_kNm3": "unit_weight",
    "soil.Df_m": "length",
    "soil.cohesion_kPa": "pressure",
}


# --- Mapa de magnitudes por petición -------------------------------------------

UNIT_FIELDS: dict[str, dict[str, str]] = {
    "DesignRequest": {
        "column.bx_m": "length",
        "column.by_m": "length",
        "column.offset_x_m": "length",
        "column.offset_y_m": "length",
        **_MATERIALES,
        **_SUELO,
        "search.B_min_m": "length",
        "search.B_max_m": "length",
        "search.B_step_m": "length",
        "search.L_min_m": "length",
        "search.L_max_m": "length",
        "search.L_step_m": "length",
        "search.h_min_m": "length",
        "search.h_max_m": "length",
        "search.h_step_m": "length",
        **_bloque_cargas(""),
    },
    "CombinedDesignRequest": {
        "columns[].bx_m": "length",
        "columns[].by_m": "length",
        "columns[].distance_from_first_m": "length",
        "columns[].transverse_offset_m": "length",
        **_bloque_cargas("columns[]."),
        **_MATERIALES,
        **_SUELO,
        "search.length_min_m": "length",
        "search.length_max_m": "length",
        "search.length_step_m": "length",
        "search.width_min_m": "length",
        "search.width_max_m": "length",
        "search.width_step_m": "length",
        "search.h_min_m": "length",
        "search.h_max_m": "length",
        "search.h_step_m": "length",
        "search.first_column_edge_distance_m": "length",
        "site_limits.start_clearance_m": "length",
        "site_limits.end_clearance_m": "length",
        "site_limits.side_neg_clearance_m": "length",
        "site_limits.side_pos_clearance_m": "length",
    },
    "ConnectedDesignRequest": {
        "exterior.bx_m": "length",
        "exterior.by_m": "length",
        **_bloque_cargas("exterior."),
        "interior.bx_m": "length",
        "interior.by_m": "length",
        **_bloque_cargas("interior."),
        "anchor.face_clearance_m": "length",
        "beam.b_m": "length",
        "beam.h_m": "length",
        "beam.d_m": "length",
        "beam.soffit_above_base_m": "length",
        "beam.concrete_unit_weight_kNm3": "unit_weight",
        "axis_distance_m": "length",
        **_MATERIALES,
        **_SUELO,
        "search.ext_long_min_m": "length",
        "search.ext_long_max_m": "length",
        "search.ext_long_step_m": "length",
        "search.ext_transv_min_m": "length",
        "search.ext_transv_max_m": "length",
        "search.ext_transv_step_m": "length",
        "search.int_long_min_m": "length",
        "search.int_long_max_m": "length",
        "search.int_long_step_m": "length",
        "search.int_transv_min_m": "length",
        "search.int_transv_max_m": "length",
        "search.int_transv_step_m": "length",
        "search.h_min_m": "length",
        "search.h_max_m": "length",
        "search.h_step_m": "length",
        "site_limits.start_clearance_m": "length",
        "site_limits.end_clearance_m": "length",
        "site_limits.side_neg_clearance_m": "length",
        "site_limits.side_pos_clearance_m": "length",
    },
    "BeamDesignRequest": {
        "b_m": "length",
        "h_m": "length",
        "d_m": "length",
        "clear_span_m": "length",
        "Mu_negative_kNm": "moment",
        "Mu_positive_kNm": "moment",
        "Vu_kN": "force",
        "sum_Pu_kN": "force",
        "fyt_MPa": "strength",
        **_MATERIALES,
        **_SUELO,
    },
}


# --- Campos numéricos que NO se convierten, y por qué ---------------------------
# Cada motivo se comprueba contra el código: o el campo es adimensional, o su
# unidad es FIJA y no depende de lo que el usuario elija en los desplegables.

_ADIMENSIONALES_SUELO = {
    "soil.mu_friction_soil_concrete": "coeficiente de fricción, adimensional (E.020 art. 22.2)",
    "soil.FS_sliding_required": "factor de seguridad, adimensional",
    "soil.FS_overturning_required": "factor de seguridad, adimensional",
}
_PESOS = {
    f"weights.{k}": "peso del criterio de optimización, adimensional"
    for k in ("w_concrete_volume", "w_steel_mass", "w_max_dimension", "w_constructive_complexity")
}

EXEMPT_FIELDS: dict[str, dict[str, str]] = {
    "DesignRequest": {
        **_ADIMENSIONALES_SUELO,
        **_PESOS,
        "search.max_LB_ratio": "cociente de dos longitudes, adimensional",
        "search.cover_override_mm": "recubrimiento SIEMPRE en mm (E.060 §7.7); no pasa por units.length",
        "top_n": "número de alternativas a devolver",
        "combination_definitions[].factors": "factores de combinación declarados por el usuario, adimensionales (E.060 §9.2)",
    },
    "CombinedDesignRequest": {
        **_ADIMENSIONALES_SUELO,
        "top_cover.explicit_mm": "recubrimiento superior SIEMPRE en mm (E.060 §7.7.1)",
        "top_n": "número de alternativas a devolver",
        "combination_definitions[].factors": "factores de combinación, adimensionales",
    },
    "ConnectedDesignRequest": {
        **_ADIMENSIONALES_SUELO,
        "beam.self_weight_dead_load_factor": "factor de carga muerta declarado por el proyectista, adimensional (TBD-C13)",
        "search.max_systems": "tope de sistemas evaluados, un conteo",
        "top_n": "número de alternativas a devolver",
        "combination_definitions[].factors": "factores de combinación, adimensionales",
    },
    "BeamDesignRequest": {
        **_ADIMENSIONALES_SUELO,
        "longitudinal_db_mm": "diámetro de barra SIEMPRE en mm (designación comercial)",
        "stirrup_diameter_mm": "diámetro de estribo SIEMPRE en mm (designación comercial)",
        "n_legs": "número de ramas del estribo, un conteo",
        "seismic.seismic_zone": "zona sísmica (E.030), un identificador",
    },
}


# --- Reescritura de una petición a otras unidades -------------------------------


def _aplicar(obj: Any, segmentos: list[str], fn) -> None:
    """Recorre la ruta y sustituye el valor de la hoja. `[]` recorre una lista."""
    if obj is None:
        return
    cabeza, resto = segmentos[0], segmentos[1:]
    if cabeza.endswith("[]"):
        for elemento in getattr(obj, cabeza[:-2], None) or []:
            _aplicar(elemento, resto, fn)
        return
    if resto:
        _aplicar(getattr(obj, cabeza, None), resto, fn)
        return
    valor = getattr(obj, cabeza, None)
    if valor is None:
        return
    setattr(obj, cabeza, fn(valor))


def rewrite_units(request: BaseModel, target: BaseModel) -> BaseModel:
    """Devuelve la petición con sus números expresados en las unidades `target`.

    El valor FÍSICO no cambia: cada número se convierte con el factor exacto del
    registro y se redondea a las cifras significativas declaradas allí. El bloque
    `units` de la petición devuelta es `target`.

    `target` es un `schemas.UnitsInput`; se pide por duck typing para no importar
    `api.schemas` desde aquí y evitar el ciclo."""
    nombre = type(request).__name__
    if nombre not in UNIT_FIELDS:
        raise ValueError(f"No hay mapa de unidades para {nombre}.")

    origen = request.units
    nueva = request.model_copy(deep=True)

    for ruta, magnitud in UNIT_FIELDS[nombre].items():
        desde = getattr(origen, magnitud)
        hasta = getattr(target, magnitud)
        if desde == hasta:
            continue
        _aplicar(
            nueva,
            ruta.split("."),
            lambda v, m=magnitud, a=desde, b=hasta: convert_for_display(v, m, a, b),
        )

    nueva.units = target.model_copy(deep=True)
    return nueva
