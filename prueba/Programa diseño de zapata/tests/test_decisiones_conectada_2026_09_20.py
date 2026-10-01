"""Decisiones 4, 5 y 6 sobre la conectada y la combinada (2026-09-20).

| # | Decisión | Qué se cerró |
|---|---|---|
| 4 | TBD-C1 | Declaración obligatoria del proyectista sobre E.060 §15.2.6, sin valor por defecto. **No** convierte el resultado en conforme por sí sola |
| 5 | TBD-C4 | `APOYA_EN_SUELO` se RECHAZA por validación, no se deja en NO VERIFICADO |
| 6 | C-V | El cortante longitudinal de la combinada queda cerrado con el criterio de CONCRETO SOLO, declarado como límite de alcance |

Las tres comparten una idea: un NO VERIFICADO es la respuesta correcta cuando el motor no
puede demostrar algo **y el resto del resultado sigue siendo el del problema planteado**.
Cuando no es así —porque la pregunta solo puede responderla el proyectista (4), porque el
motor estaría resolviendo otro problema (5), o porque el criterio ya está tomado y lo que
falta es decir hasta dónde llega (6)— el NO VERIFICADO sobra o engaña.
"""

import pytest

from engine.domain.connected_layout import (
    BeamSupportMode,
    StiffnessDeclaration,
    check_beam_support_supported,
)
from engine.results.status import CheckStatus


# =========================================================================
# Decisión 5 — TBD-C4: APOYA_EN_SUELO se rechaza
# =========================================================================


def test_apoya_en_suelo_se_rechaza_por_validacion():
    with pytest.raises(ValueError) as exc:
        check_beam_support_supported(BeamSupportMode.APOYA_EN_SUELO)
    mensaje = str(exc.value)
    # El mensaje tiene que decir POR QUÉ y QUÉ HACER, no solo que no se admite.
    assert "APOYA_EN_SUELO" in mensaje
    assert "SIN_APOYO" in mensaje
    assert "interior" in mensaje.lower()
    assert "TBD-C4" in mensaje


def test_sin_apoyo_sigue_admitiendose():
    check_beam_support_supported(BeamSupportMode.SIN_APOYO)


def test_el_layout_rechaza_la_viga_apoyada():
    """La validación vive en el layout: no hay forma de construir el sistema.

    Es lo que retiró `Z7_viga_apoya_en_suelo` del congelamiento —ese caso ya no se puede
    ni instanciar—, y lo que sustituye su cobertura por una más estricta."""
    from tests.freeze.cases import CONNECTED_CASES

    caso = next(c for c in CONNECTED_CASES if not c.expects_rejection)
    datos = caso.layout.model_dump()
    datos["beam"]["support_mode"] = BeamSupportMode.APOYA_EN_SUELO.value
    with pytest.raises(ValueError, match="APOYA_EN_SUELO"):
        type(caso.layout).model_validate(datos)


def test_el_solver_tambien_lo_rechaza_aunque_se_salte_el_validador():
    """`model_copy(update=…)` de pydantic v2 NO ejecuta validadores.

    Es la misma puerta trasera que obligó a comprobar D1 en tres sitios. Si solo se
    validara al construir, bastaría un `model_copy` para colarlo."""
    import dataclasses

    from tests.freeze.cases import CONNECTED_CASES
    from tests.freeze.test_freeze_connected import _solve

    caso = next(c for c in CONNECTED_CASES if not c.expects_rejection)
    viga_apoyada = caso.layout.beam.model_copy(
        update={"support_mode": BeamSupportMode.APOYA_EN_SUELO}
    )
    colado = caso.layout.model_copy(update={"beam": viga_apoyada})
    assert colado.beam.support_mode is BeamSupportMode.APOYA_EN_SUELO  # se coló
    with pytest.raises(ValueError, match="APOYA_EN_SUELO"):
        _solve(dataclasses.replace(caso, layout=colado))


# =========================================================================
# Decisión 4 — TBD-C1: la declaración del proyectista
# =========================================================================


def _resolver(caso, declaracion=None):
    import dataclasses

    from tests.freeze.test_freeze_connected import _solve

    if declaracion is None:
        return _solve(caso)
    viga = caso.layout.beam.model_copy(update={"stiffness_declaration": declaracion})
    layout = caso.layout.model_copy(update={"beam": viga})
    return _solve(dataclasses.replace(caso, layout=layout))


def _caso():
    from tests.freeze.cases import CONNECTED_CASES

    return next(c for c in CONNECTED_CASES if not c.expects_rejection)


def _premisa(resultado):
    for e in resultado.trace.entries:
        if e.id in ("uniform_pressure_premise", "rigid_body_premise"):
            return e
    raise AssertionError("la terna no emite la premisa de §15.2.6")


def test_sin_declarar_la_premisa_sigue_no_verificada():
    """El comportamiento anterior se conserva intacto: no declarar es no responder."""
    entrada = _premisa(_resolver(_caso()))
    assert entrada.status is CheckStatus.NOT_VERIFIED
    assert entrada.open_tbd == "TBD-C1"
    assert any("NO DECLARADA" in h for h in entrada.hypotheses)


def test_el_valor_por_defecto_no_responde_la_pregunta():
    assert (
        _caso().layout.beam.stiffness_declaration is StiffnessDeclaration.NO_EVALUADA
    )


def test_declarada_levanta_el_bloqueo_y_dice_de_quien_es_la_afirmacion():
    entrada = _premisa(
        _resolver(_caso(), StiffnessDeclaration.DECLARADA_POR_PROYECTISTA)
    )
    assert entrada.status is CheckStatus.INFO
    assert entrada.open_tbd is None
    # Y la traza dice explícitamente que el motor NO lo comprobó.
    texto = " ".join(entrada.hypotheses)
    assert "EL MOTOR NO LO HA COMPROBADO" in texto
    assert "§15.2.6" in texto
    assert "no convierte el resultado en conforme" in texto


def test_la_declaracion_no_cambia_ni_un_numero():
    """Registra una responsabilidad; no toca el cálculo.

    Si moviera un número sería otra cosa: un criterio de diseño encubierto."""
    sin = _resolver(_caso())
    con = _resolver(_caso(), StiffnessDeclaration.DECLARADA_POR_PROYECTISTA)
    from tests.freeze.snapshot import snapshot_connected

    assert snapshot_connected(sin)["numeros"] == snapshot_connected(con)["numeros"]


def test_declarar_no_basta_para_conforme_si_queda_otro_pendiente():
    """El punto que la decisión 4 subraya: levanta ESTE bloqueo y ninguno más.

    Se toma una terna con `PAR_PURO_EN_ZAPATA`, que arrastra TBD-C11 por su cuenta, y se
    declara la rigidez. La premisa de §15.2.6 pasa a INFO, pero la terna sigue sin poder
    presentarse como conforme porque C11 sigue abierto."""
    from tests.freeze.cases import CONNECTED_CASES

    candidatos = [
        c for c in CONNECTED_CASES
        if not c.expects_rejection
        and any(
            e.open_tbd == "TBD-C11"
            for e in _resolver(c).trace.entries
        )
    ]
    if not candidatos:
        pytest.skip("ninguna terna congelada arrastra TBD-C11")
    caso = candidatos[0]
    r = _resolver(caso, StiffnessDeclaration.DECLARADA_POR_PROYECTISTA)
    assert _premisa(r).status is CheckStatus.INFO
    abiertos = {e.open_tbd for e in r.trace.entries if e.open_tbd}
    assert "TBD-C1" not in abiertos
    assert abiertos, "la terna debería seguir con algún pendiente abierto"


# =========================================================================
# Decisión 6 — C-V: el alcance queda declarado
# =========================================================================


def test_el_criterio_dice_que_NO_es_una_verificacion_completa_de_e060():
    """Lo que la decisión 6 obliga a decir.

    El criterio de concreto solo es más estricto que E.060, de modo que no puede aceptar
    una geometría que la norma rechace. Lo que no puede hacerse es presentarlo como
    «cumple §11»: la norma admite Vn = Vc + Vs y el motor no lo implementa."""
    from engine.foundation.combined_solver import CONCRETE_ONLY_SHEAR_CRITERION

    texto = CONCRETE_ONLY_SHEAR_CRITERION
    assert "NO ES UNA VERIFICACIÓN COMPLETA DEL MODELO DE CORTANTE DE E.060" in texto
    assert "Vn = Vc + Vs" in texto
    assert "FUERA DEL ALCANCE" in texto
    assert "más estricto que la norma" in texto
    # Y sigue sin presentarse como prohibición normativa.
    assert "Criterio del programa" in texto


def test_el_criterio_viaja_en_la_traza_de_la_verificacion():
    from tests.freeze.cases import COMBINED_CASES
    from tests.freeze.test_freeze_isolated import _solve_combined
    from engine.foundation.combined_solver import CONCRETE_ONLY_SHEAR_CRITERION

    r = _solve_combined(COMBINED_CASES[0])
    entrada = r.trace.by_id("shear_longitudinal")
    assert entrada is not None
    assert CONCRETE_ONLY_SHEAR_CRITERION in entrada.hypotheses


def test_no_hay_refuerzo_de_cortante_implementado():
    """El alcance declarado tiene que coincidir con el código: si algún día apareciera un
    `shear_reinforcement` calculado, esta nota pasaría a ser falsa."""
    from tests.freeze.cases import COMBINED_CASES
    from tests.freeze.test_freeze_isolated import _solve_combined

    for caso in COMBINED_CASES:
        r = _solve_combined(caso)
        assert getattr(r, "shear_reinforcement", None) is None


def test_el_rotulo_CONFORME_exige_la_declaracion_Y_todo_lo_demas():
    """La semántica completa de la decisión 4, fijada sobre el rótulo presentable.

    `CLAUDE.md` §5 decía que CONFORME estaba «hoy vacío en conectada por TBD-C1». Desde la
    decisión 4 deja de estarlo, y conviene que el cambio quede clavado en las dos
    direcciones, porque es justo donde un descuido se convertiría en un falso conforme:

      - sin declarar          → NO VERIFICADA, siempre;
      - declarando, con otro pendiente abierto → NO VERIFICADA todavía;
      - declarando, con TODO lo demás en PASS o INFO → CONFORME.

    La tercera línea es la que la decisión autoriza explícitamente —«las verificaciones
    restantes deben estar PASS»—; la segunda es la que impide leerla de más."""
    import dataclasses

    from engine.results.vocabulary import ESTADO_CONFORME, ESTADO_NO_VERIFICADA, status_label
    from tests.freeze.cases import CONNECTED_CASES
    from tests.freeze.test_freeze_connected import _solve

    def rotulo(nombre, declaracion):
        caso = next(c for c in CONNECTED_CASES if c.name == nombre)
        viga = caso.layout.beam.model_copy(update={"stiffness_declaration": declaracion})
        r = _solve(dataclasses.replace(caso, layout=caso.layout.model_copy(update={"beam": viga})))
        abiertos = tuple(e.open_tbd for e in r.trace.entries if e.open_tbd)
        return status_label(r.overall_status, abiertos), abiertos

    # Z1: todo lo demás pasa. Es la terna donde la declaración SÍ desbloquea.
    etq, abiertos = rotulo("Z1_articulado_equilibrio", StiffnessDeclaration.NO_EVALUADA)
    assert etq == ESTADO_NO_VERIFICADA and abiertos == ("TBD-C1",)

    etq, abiertos = rotulo(
        "Z1_articulado_equilibrio", StiffnessDeclaration.DECLARADA_POR_PROYECTISTA
    )
    assert etq == ESTADO_CONFORME and abiertos == ()

    # Z2: arrastra TBD-C11 por su cuenta. Declarar C1 NO la vuelve conforme.
    etq, abiertos = rotulo(
        "Z2_articulado_par_puro", StiffnessDeclaration.DECLARADA_POR_PROYECTISTA
    )
    assert etq == ESTADO_NO_VERIFICADA
    assert "TBD-C1" not in abiertos and "TBD-C11" in abiertos
