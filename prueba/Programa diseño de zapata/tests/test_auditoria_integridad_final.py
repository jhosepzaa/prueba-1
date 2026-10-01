"""Auditoría de integridad — invariantes transversales de las tres tipologías.

No verifica ingeniería: verifica que el ANDAMIAJE que hace auditable la ingeniería no tenga
huecos. Son las comprobaciones que, si fallan, dejan al usuario leyendo un resultado que el
programa no puede respaldar.

Qué fija:

1. **`enforced_by` nombra una verificación que existe de verdad.** Una limitación capaz de
   producir un falso PASS declara qué entrada de traza la hace visible; si ese id no
   correspondiera a ninguna entrada real, la neutralización sería nominal.
2. **`open_tbd` solo aparece en entradas NO VERIFICADAS.** Un pendiente marcado sobre una
   entrada que pasa diría que hay un hueco donde no lo hay, y al revés.
3. **Toda entrada de traza está completa**: ecuación, unidad y referencia. Una entrada sin
   ellas no es auditable.
4. **Ninguna alternativa conforme arrastra un pendiente abierto**, en ninguna tipología.
5. **El vocabulario y la regla de aceptación son los mismos en las tres.**
"""

from __future__ import annotations

import pytest

from engine.codes.peru.e060_concrete import E060ConcreteCode
from engine.domain.materials import MaterialConcrete, MaterialSteel
from engine.domain.soil import PressureBasis, SoilProfile
from engine.foundation.combined_solver import solve_combined_footing
from engine.foundation.connected_solver import solve_connected_footing
from engine.integration.typology_catalog import CATALOG, AcceptanceRule
from engine.results.limitations import (
    ENFORCED_BY_CHECKS,
    LIMITATION_REGISTRY,
    check_matches,
    enforcing_checks,
)
from engine.results.status import CheckStatus
from engine.results.vocabulary import STATUS_VOCABULARY
from engine.soil.contact_pressure import FullContactModel, KernCheckModel
from tests.freeze.cases import CASES, COMBINED_CASES, CONNECTED_CASES
from tests.freeze.test_freeze_isolated import _evaluate
from tests.freeze.test_freeze_connected import _solve as _solve_conectada

CODE = E060ConcreteCode()


def _resultados_combinada():
    for c in COMBINED_CASES:
        yield c.name, solve_combined_footing(
            c.layout, c.h_m, soil=c.soil, concrete=c.concrete, steel=c.steel,
            code=CODE, contact_model=KernCheckModel(), top_cover=c.top_cover,
        )


def _con_area_efectiva():
    """Un caso con el modelo de contacto OPCIONAL de E.050 art. 28, y con la resultante
    fuera del núcleo para que ese modelo llegue a gobernar.

    Hace falta aquí porque el universo de ids de verificación no puede ser solo el de la
    configuración por defecto: una limitación que solo se neutraliza bajo un modelo
    opcional parecería nominal, y no lo es. Lo que NO puede pasar es lo contrario —que una
    limitación declare una verificación que nadie emite nunca—, y eso se sigue detectando.
    """
    from engine.domain.column_placement import ColumnPlacement
    from engine.domain.search_parameters import DepthSearchParameters
    from engine.foundation.depth_solver import evaluate_candidate
    from engine.soil.contact_pressure import EffectiveAreaModel

    caso = next(c for c in CASES if c.placement is None or c.placement.is_concentric)
    # Mx/P = 1,20 m sobre B = 3,00: muy por encima de B/6 = 0,50 incluso después de que el
    # peso propio diluya la excentricidad en ex = (Mx + P·offset)/(P + W).
    cargas = caso.load_case_set.model_copy(update={
        "service": [
            c.model_copy(update={"Mx_kNm": 1.20 * c.P_kN}) for c in caso.load_case_set.service
        ],
        "factored": [
            c.model_copy(update={"Mx_kNm": 1.20 * c.P_kN}) for c in caso.load_case_set.factored
        ],
    })
    resultado = evaluate_candidate(
        B_m=3.00, L_m=2.40, h_m=0.70, column=caso.column, soil=caso.soil,
        concrete=caso.concrete, steel=caso.steel, load_case_set=cargas, code=CODE,
        contact_model=EffectiveAreaModel(),
        placement=ColumnPlacement(column=caso.column),
        depth_params=DepthSearchParameters(h_min_m=0.40, h_max_m=1.20, h_step_m=0.05),
    )
    assert resultado.contact_pressure.effective_area_governs, (
        "Este caso existe para que el área efectiva GOBIERNE; si dejara de hacerlo, la "
        "auditoría perdería cobertura sin que nada lo delatara."
    )
    return resultado


def _todas_las_trazas():
    """(etiqueta, traza) de un caso de cada tipología, con sus variantes."""
    for c in CASES:
        yield f"aislada/{c.name}", _evaluate(c).trace
    for nombre, r in _resultados_combinada():
        yield f"combinada/{nombre}", r.trace
    for c in CONNECTED_CASES:
        if c.expects_rejection:
            continue
        yield f"conectada/{c.name}", _solve_conectada(c).trace
    yield "aislada/area_efectiva_e050_art28", _con_area_efectiva().trace


@pytest.fixture(scope="module")
def trazas():
    return list(_todas_las_trazas())


@pytest.fixture(scope="module")
def ids_de_verificacion(trazas):
    return {e.id for _, t in trazas for e in t.entries}


# =========================================================================
# 1. `enforced_by` nombra una verificación real
# =========================================================================


def test_toda_limitacion_neutralizada_nombra_una_verificacion_que_existe(ids_de_verificacion):
    """El invariante de `test_limitations.py` exige que exista `enforced_by`. Este exige
    algo más fuerte: que ese id sea el de una entrada de traza que el motor emite de
    verdad. Un nombre que no corresponda a ninguna entrada haría nominal la
    neutralización."""
    for lim in LIMITATION_REGISTRY:
        if not lim.enforced_by:
            continue
        patrones = enforcing_checks(lim)
        assert patrones, f"«{lim.id}»: `enforced_by` no se expande a ninguna verificación"
        huerfanos = [
            p for p in patrones
            if not any(check_matches(p, i) for i in ids_de_verificacion)
        ]
        assert not huerfanos, (
            f"«{lim.id}» dice estar neutralizada por {sorted(patrones)}, y {huerfanos} no "
            f"corresponde a ninguna entrada de traza que el motor emita."
        )


def test_la_expansion_de_enforced_by_no_tiene_entradas_muertas(ids_de_verificacion):
    """Cada patrón de la tabla de expansión tiene que casar con alguna entrada real. Uno
    muerto ahí volvería a hacer nominal la neutralización sin que nada lo delatara."""
    for grupo, patrones in ENFORCED_BY_CHECKS.items():
        assert patrones, grupo
        for p in patrones:
            assert any(check_matches(p, i) for i in ids_de_verificacion), (grupo, p)


def test_todo_enforced_by_declarado_esta_en_la_tabla_de_expansion():
    """Una limitación con un `enforced_by` que no esté en la tabla caería en el caso por
    defecto —id exacto— sin que nadie lo hubiera revisado."""
    declarados = {lim.enforced_by for lim in LIMITATION_REGISTRY if lim.enforced_by}
    assert declarados <= set(ENFORCED_BY_CHECKS), declarados - set(ENFORCED_BY_CHECKS)


def test_ninguna_limitacion_puede_producir_falso_pass_sin_neutralizar():
    for lim in LIMITATION_REGISTRY:
        if lim.can_cause_false_pass:
            assert lim.enforced_by, lim.id


# =========================================================================
# 2. `open_tbd` solo donde el motor no puede pronunciarse
# =========================================================================


def test_open_tbd_solo_aparece_en_entradas_no_verificadas(trazas):
    """`CLAUDE.md` §6: el marcador señala un hueco del motor o de la norma. Sobre una
    entrada que pasa diría que hay un hueco donde no lo hay."""
    for etiqueta, t in trazas:
        for e in t.entries:
            if e.open_tbd:
                assert e.status is CheckStatus.NOT_VERIFIED, f"{etiqueta}/{e.id}: {e.open_tbd}"


def test_el_marcador_es_una_cadena_con_forma_de_tbd(trazas):
    for etiqueta, t in trazas:
        for e in t.entries:
            if e.open_tbd is not None:
                assert isinstance(e.open_tbd, str), f"{etiqueta}/{e.id}"
                assert e.open_tbd.startswith("TBD-"), f"{etiqueta}/{e.id}: {e.open_tbd}"


# =========================================================================
# 3. Toda entrada de traza es auditable
# =========================================================================


def test_toda_entrada_declara_ecuacion_unidad_y_referencia(trazas):
    """Sin ecuación sustituida no se puede reconstruir el número; sin referencia no se sabe
    de dónde sale el criterio."""
    for etiqueta, t in trazas:
        for e in t.entries:
            assert e.description.strip(), f"{etiqueta}/{e.id}: sin descripción"
            assert e.equation_symbolic.strip(), f"{etiqueta}/{e.id}: sin ecuación simbólica"
            assert e.equation_substituted.strip(), f"{etiqueta}/{e.id}: sin sustitución"
            assert e.result_unit.strip(), f"{etiqueta}/{e.id}: sin unidad"
            assert e.code_name.strip(), f"{etiqueta}/{e.id}: sin norma"
            assert e.code_reference.strip(), f"{etiqueta}/{e.id}: sin referencia"


def test_las_entradas_son_unicas_por_ambito_e_id(trazas):
    """`CLAUDE.md` §7: la clave es (scope, id). Dos entradas con la misma clave harían
    ambiguo el informe y el congelamiento."""
    for etiqueta, t in trazas:
        claves = [(e.scope, e.id) for e in t.entries]
        assert len(claves) == len(set(claves)), f"{etiqueta}: claves repetidas"


def test_una_entrada_degradada_explica_por_que(trazas):
    """Un NO VERIFICADO o un FAIL sin ninguna hipótesis que lo explique deja al usuario sin
    saber qué hacer."""
    for etiqueta, t in trazas:
        for e in t.entries:
            if e.status in (CheckStatus.NOT_VERIFIED, CheckStatus.FAIL, CheckStatus.WARNING):
                assert e.hypotheses, f"{etiqueta}/{e.id}: degradada y sin explicación"


# =========================================================================
# 4. Conforme nunca arrastra un pendiente
# =========================================================================


def test_ningun_resultado_conforme_arrastra_un_pendiente_abierto(trazas):
    """`CLAUDE.md` §6: `overall_status` nunca llega a conforme mientras un TBD afecte la
    verificación. Se comprueba sobre la traza, que es de donde sale el estado."""
    for etiqueta, t in trazas:
        con_tbd = [e for e in t.entries if e.open_tbd]
        if not con_tbd:
            continue
        peor = CheckStatus.worst([e.status for e in t.entries])
        assert peor not in (CheckStatus.PASS, CheckStatus.INFO), (
            f"{etiqueta}: estado conforme con pendientes {[e.open_tbd for e in con_tbd]}"
        )


def test_el_peor_estado_de_la_traza_manda(trazas):
    """El estado global no puede ser mejor que la peor de sus entradas."""
    for etiqueta, t in trazas:
        peor = CheckStatus.worst([e.status for e in t.entries])
        assert t.overall_status() is peor, etiqueta


# =========================================================================
# 5. Las tres tipologías comparten criterio y vocabulario
# =========================================================================


def test_las_tres_comparten_regla_de_aceptacion_y_vocabulario():
    assert {t.acceptance_rule for t in CATALOG.typologies} == {AcceptanceRule.NO_FAIL}
    for t in CATALOG.typologies:
        assert t.status_vocabulary == STATUS_VOCABULARY, t.id


def test_las_diferencias_abiertas_del_catalogo_estan_documentadas():
    """Una diferencia abierta tiene que decir qué decisión falta; una resuelta, qué se
    decidió. Ninguna puede quedarse sin ninguna de las dos."""
    for k in CATALOG.known_differences:
        assert k.decision_needed.strip(), k.id
        if not k.is_open:
            assert k.resolution and k.resolution.strip(), k.id


def test_el_alcance_de_cada_tipologia_esta_declarado():
    for t in CATALOG.typologies:
        assert t.normative_basis, t.id
        assert t.acceptance_note.strip(), t.id
        assert t.vocabulary_note.strip(), t.id
        assert set(t.capabilities) == {
            "tabla_comparativa", "frente_pareto", "vista_3d", "esquema_2d",
            "memoria_html", "explicacion_descartes",
        }, t.id


# =========================================================================
# 6. Ninguna tipología se queda sin las verificaciones del alcance declarado
# =========================================================================


def test_la_combinada_verifica_lo_que_su_alcance_declara():
    """Paridad: presión de contacto, flexión, cortante, punzonamiento y franjas. La
    estabilidad solo cuando hay fuerza horizontal (pendiente 7)."""
    for nombre, r in _resultados_combinada():
        ids = {e.id for e in r.trace.entries}
        for obligatoria in ("contact_pressure", "flexure_bottom", "shear_longitudinal",
                            "shape_ratio", "foundation_depth"):
            assert obligatoria in ids, f"{nombre}: falta {obligatoria}"
        assert any(i.startswith("punching_") for i in ids), nombre
        assert any(i.startswith("transverse_strip_") for i in ids), nombre


def test_la_combinada_sin_fuerza_horizontal_no_emite_estabilidad():
    """Alcance declarado del pendiente 7: sin H el momento queda acotado por el núcleo
    central y no se añade ninguna entrada. Es lo que mantiene K1–K4 intactos."""
    for nombre, r in _resultados_combinada():
        ids = {e.id for e in r.trace.entries}
        assert ids.isdisjoint({"sliding", "overturning_x", "overturning_y"}), nombre
        assert r.stability is None, nombre


def test_la_reduccion_sismica_y_el_incremento_tienen_una_sola_implementacion():
    """Las dos disposiciones de E.060 §15.2 viven en `depth_solver` y las tres tipologías
    las consumen desde ahí."""
    import pathlib

    for constante in ("SEISMIC_REDUCTION_FACTOR =", "TEMPORARY_INCREASE_FACTOR ="):
        archivos = [
            p.name for p in pathlib.Path("engine").rglob("*.py")
            if constante in p.read_text(encoding="utf-8")
        ]
        assert archivos == ["depth_solver.py"], (constante, archivos)


def test_las_tres_tipologias_usan_el_mismo_perfil_de_suelo():
    """Un `SoilProfile` común es lo que hace que μ, los FS y las dos disposiciones de
    §15.2 signifiquen lo mismo en las tres."""
    import inspect

    import engine.foundation.combined_solver as comb
    import engine.foundation.connected_solver as con
    import engine.foundation.depth_solver as dep

    for modulo in (comb, con, dep):
        assert "SoilProfile" in inspect.getsource(modulo), modulo.__name__


def test_el_suelo_no_inventa_ningun_parametro_geotecnico():
    """`CLAUDE.md` §1: μ, FS y cohesión son datos del proyectista. Sin valor por defecto
    distinto de None, el motor no puede suponerlos."""
    for campo in ("mu_friction_soil_concrete", "cohesion_kPa",
                  "FS_sliding_required", "FS_overturning_required"):
        assert SoilProfile.model_fields[campo].default is None, campo


def test_un_suelo_sin_parametros_no_impide_construirlo():
    """Faltar un dato no es un error de entrada: es un NO VERIFICADO más adelante."""
    s = SoilProfile(qadm_kPa=200.0, pressure_basis=PressureBasis.BRUTA,
                    gamma_kNm3=18.0, Df_m=1.20)
    assert s.mu_friction_soil_concrete is None
    assert s.allow_temporary_increase_30pct is False
    assert s.allow_seismic_reduction_80pct is False
