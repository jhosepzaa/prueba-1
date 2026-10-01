"""Auditoría del mapa de unidades de la API (2026-09-23).

Dos cosas que no se pueden comprobar leyendo:

1. QUE NO FALTE NINGÚN CAMPO. Se recorren los campos numéricos de las cuatro
   peticiones y se exige que cada uno esté clasificado: o tiene magnitud, o está
   exento con su motivo escrito. Un campo nuevo sin clasificar rompe el test.

2. QUE EL VALOR FÍSICO NO CAMBIE. Es el invariante del encargo: reescribir una
   petición a otras unidades y volver a construir los objetos del motor tiene que
   dar los MISMOS valores SI. Se comprueba contra `api.mapping`, que es quien
   convierte de verdad, y no contra la reescritura misma.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel
from typing import get_args, get_origin

from api import mapping, schemas
from api.unit_fields import EXEMPT_FIELDS, UNIT_FIELDS, rewrite_units
from engine.units.unit_registry import KIND_TABLES

PETICIONES = {
    "DesignRequest": schemas.DesignRequest,
    "CombinedDesignRequest": schemas.CombinedDesignRequest,
    "ConnectedDesignRequest": schemas.ConnectedDesignRequest,
    "BeamDesignRequest": schemas.BeamDesignRequest,
}


def _submodelo(anotacion) -> tuple[type[BaseModel] | None, bool]:
    """El modelo anidado que cuelga de una anotación, y si viene dentro de una lista.

    Hay que distinguir `SoilInput` de `list[LoadCaseInput] | None`: el primero es una
    rama de la ruta (`soil.`) y el segundo un tramo con lista (`load_cases[].`)."""
    if isinstance(anotacion, type) and issubclass(anotacion, BaseModel):
        return anotacion, False
    origen, argumentos = get_origin(anotacion), get_args(anotacion)
    if origen is list:
        for a in argumentos:
            if isinstance(a, type) and issubclass(a, BaseModel):
                return a, True
        return None, False
    for a in argumentos:  # Optional / Union
        modelo, lista = _submodelo(a)
        if modelo is not None:
            return modelo, lista
    return None, False


def _campos_numericos(modelo: type[BaseModel], prefijo: str = "") -> set[str]:
    """Rutas de todos los campos numéricos, bajando por modelos anidados y listas."""
    rutas: set[str] = set()
    for nombre, info in modelo.model_fields.items():
        anotacion = info.annotation
        ruta = f"{prefijo}{nombre}"
        anidado, es_lista = _submodelo(anotacion)
        if anidado is not None:
            rutas |= _campos_numericos(anidado, f"{ruta}[]." if es_lista else f"{ruta}.")
        elif any(t in str(anotacion) for t in ("float", "int")) and "bool" not in str(anotacion):
            rutas.add(ruta)
    return rutas


# --- 1. Ningún campo sin clasificar --------------------------------------------

@pytest.mark.parametrize("nombre", sorted(PETICIONES))
def test_todo_campo_numerico_esta_clasificado(nombre):
    declarados = set(UNIT_FIELDS[nombre]) | set(EXEMPT_FIELDS[nombre])
    reales = _campos_numericos(PETICIONES[nombre])
    sin_clasificar = reales - declarados
    assert not sin_clasificar, (
        f"Campos numéricos de {nombre} sin clasificar: {sorted(sin_clasificar)}. "
        "Añádalos a UNIT_FIELDS con su magnitud, o a EXEMPT_FIELDS con el motivo."
    )


@pytest.mark.parametrize("nombre", sorted(PETICIONES))
def test_el_mapa_no_nombra_campos_que_no_existen(nombre):
    reales = _campos_numericos(PETICIONES[nombre])
    declarados = set(UNIT_FIELDS[nombre]) | set(EXEMPT_FIELDS[nombre])
    assert not declarados - reales, f"Rutas inexistentes en {nombre}: {sorted(declarados - reales)}"


@pytest.mark.parametrize("nombre", sorted(PETICIONES))
def test_ningun_campo_esta_a_la_vez_convertido_y_exento(nombre):
    assert not set(UNIT_FIELDS[nombre]) & set(EXEMPT_FIELDS[nombre])


@pytest.mark.parametrize("nombre", sorted(PETICIONES))
def test_las_magnitudes_declaradas_existen_en_el_registro(nombre):
    for ruta, magnitud in UNIT_FIELDS[nombre].items():
        assert magnitud in KIND_TABLES, f"{nombre}.{ruta}: magnitud desconocida {magnitud}"


@pytest.mark.parametrize("nombre", sorted(PETICIONES))
def test_todo_exento_lleva_motivo_escrito(nombre):
    for ruta, motivo in EXEMPT_FIELDS[nombre].items():
        assert len(motivo) > 15, f"{nombre}.{ruta}: el motivo tiene que explicar algo"


# --- 2. El valor físico no cambia ----------------------------------------------

def _peticion_aislada() -> schemas.DesignRequest:
    return schemas.DesignRequest(
        project_name="unidades",
        column=schemas.ColumnInput(shape="rectangular", bx_m=0.40, by_m=0.60, offset_x_m=0.10),
        materials=schemas.MaterialsInput(fc_MPa=21.0, fy_MPa=420.0, concrete_unit_weight_kNm3=24.0),
        soil=schemas.SoilInput(
            qadm_kPa=150.0, gamma_kNm3=18.0, Df_m=1.5,
            mu_friction_soil_concrete=0.45, cohesion_kPa=10.0,
        ),
        search=schemas.SearchInput(
            B_min_m=1.0, B_max_m=3.0, B_step_m=0.1,
            L_min_m=1.0, L_max_m=3.0, L_step_m=0.1,
            h_min_m=0.4, h_max_m=0.9, h_step_m=0.05,
        ),
        combinations=[
            schemas.LoadCombinationInput(
                name="S1", type="SERVICIO", P_kN=800.0, Mx_kNm=120.0, My_kNm=40.0,
                Hx_kN=30.0, Hy_kN=15.0,
            ),
            schemas.LoadCombinationInput(
                name="U1", type="FACTORIZADA", P_kN=1120.0, Mx_kNm=168.0, My_kNm=56.0,
            ),
        ],
    )


OTRAS_UNIDADES = schemas.UnitsInput(
    force="tonf", moment="tonf·m", pressure="kgf/cm²",
    strength="kgf/cm²", length="cm", unit_weight="tonf/m³",
)


def test_el_valor_fisico_no_cambia_al_reescribir_la_peticion():
    """Invariante del encargo: lo que llega al motor es lo mismo en kN que en tonf."""
    original = _peticion_aislada()
    reescrita = rewrite_units(original, OTRAS_UNIDADES)

    assert reescrita.units.strength == "kgf/cm²"
    # 21 MPa son 214,14 kgf/cm², no 210.
    assert reescrita.materials.fc_MPa == pytest.approx(214.14, abs=5e-3)

    for constructor in (
        lambda p: mapping.build_column(p.column, p.units),
        lambda p: mapping.build_placement(p.column, p.units),
        lambda p: mapping.build_materials(p.materials, p.units),
        lambda p: mapping.build_soil(p.soil, p.units),
    ):
        antes, despues = constructor(original), constructor(reescrita)
        assert _valores(antes) == pytest.approx(_valores(despues), rel=1e-5)

    cargas_antes = mapping.build_loads(original.combinations, original.units)
    cargas_despues = mapping.build_loads(reescrita.combinations, reescrita.units)
    for a, b in zip(cargas_antes.service + cargas_antes.factored,
                    cargas_despues.service + cargas_despues.factored):
        assert (a.P_kN, a.Mx_kNm, a.My_kNm, a.Hx_kN, a.Hy_kN) == pytest.approx(
            (b.P_kN, b.Mx_kNm, b.My_kNm, b.Hx_kN, b.Hy_kN), rel=1e-5
        )


def _valores(objeto) -> list[float]:
    if isinstance(objeto, tuple):
        return [v for o in objeto for v in _valores(o)]
    datos = objeto.model_dump() if hasattr(objeto, "model_dump") else vars(objeto)
    return [v for v in datos.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]


def test_la_ida_y_vuelta_devuelve_los_numeros_de_partida():
    original = _peticion_aislada()
    vuelta = rewrite_units(rewrite_units(original, OTRAS_UNIDADES), original.units)

    assert vuelta.units.model_dump() == original.units.model_dump()
    assert vuelta.materials.fc_MPa == pytest.approx(21.0, rel=1e-5)
    assert vuelta.materials.fy_MPa == pytest.approx(420.0, rel=1e-5)
    assert vuelta.soil.qadm_kPa == pytest.approx(150.0, rel=1e-5)
    assert vuelta.column.bx_m == pytest.approx(0.40, rel=1e-5)
    assert vuelta.combinations[0].P_kN == pytest.approx(800.0, rel=1e-5)
    assert vuelta.combinations[0].Mx_kNm == pytest.approx(120.0, rel=1e-5)


def test_los_campos_exentos_no_se_tocan():
    original = _peticion_aislada()
    reescrita = rewrite_units(original, OTRAS_UNIDADES)

    assert reescrita.soil.mu_friction_soil_concrete == 0.45
    assert reescrita.soil.FS_sliding_required == original.soil.FS_sliding_required
    assert reescrita.search.max_LB_ratio == original.search.max_LB_ratio
    assert reescrita.top_n == original.top_n


def test_reescribir_a_las_mismas_unidades_no_altera_nada():
    original = _peticion_aislada()
    igual = rewrite_units(original, original.units)
    assert igual.model_dump() == original.model_dump()


def test_los_none_siguen_siendo_none():
    """Un límite de búsqueda omitido se queda omitido: no se convierte un hueco."""
    original = _peticion_aislada()
    original.search.B_min_m = None
    original.soil.cohesion_kPa = None
    reescrita = rewrite_units(original, OTRAS_UNIDADES)
    assert reescrita.search.B_min_m is None
    assert reescrita.soil.cohesion_kPa is None


def test_las_cuatro_tipologias_tienen_mapa():
    assert set(UNIT_FIELDS) == set(PETICIONES) == set(EXEMPT_FIELDS)
