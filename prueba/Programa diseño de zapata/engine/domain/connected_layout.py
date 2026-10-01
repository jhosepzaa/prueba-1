"""Entidades de la zapata conectada — Fase 4A.

QUÉ ES UNA ZAPATA CONECTADA
===========================
Dos zapatas independientes, cada una con una columna, unidas por una viga que
reparte el par que genera la excentricidad de la zapata de lindero. No es una
zapata combinada: no hay una sola zapata bajo dos columnas, y por eso E.060
§15.10 —«las zapatas que soporten más de una columna»— NO la alcanza. Cada zapata
se verifica con los artículos de la zapata aislada.

POR QUÉ `ColumnPlacement` NO BASTA PARA LA ZAPATA DE LINDERO
===========================================================
`ColumnPlacement` expresa la posición como DESPLAZAMIENTO respecto del centro de la
zapata. Es la representación correcta para una columna cuya posición relativa está
dada, pero NO para una zapata de lindero, donde lo que impone la realidad es otra
cosa: que la CARA de la columna quede al ras del límite de propiedad.

Con B fija las dos descripciones son equivalentes. Durante el BARRIDO de geometrías
no lo son: al crecer B, un desplazamiento constante despega la columna del lindero
y describe una estructura que no es la que el usuario planteó. El propio módulo
`column_placement.py` ya declaraba esta limitación; la zapata conectada es la
primera tipología que la sufre de verdad.

`EdgeAnchor` invierte la dependencia. Declara lo que permanece constante —la
distancia de la cara de la columna al borde— y DERIVA el `ColumnPlacement` para
cada geometría del barrido. `ColumnPlacement` no cambia ni una línea y sigue siendo
lo que el motor de zapata aislada consume.

CONVENCIÓN DE EJES
==================
La misma del resto del motor (E.050 art. 28.1): X es la dirección de B, Y la de L.
`longitudinal_axis` declara sobre cuál de los dos corre la viga de conexión.

EL MODELO DE ANÁLISIS NO TIENE VALOR POR DEFECTO
================================================
Ni E.050, ni E.060, ni E.030 dicen cuál de los dos modelos corresponde. La elección
depende de la magnitud de los momentos de la columna interior, y «momentos
considerables» no está definido en ninguna de las tres. Poner un valor por defecto
equivaldría a que el programa elija el modelo estructural por el ingeniero.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from engine.domain.column import Column
from engine.domain.column_placement import ColumnPlacement
from engine.domain.loads import LoadCaseSet

LongitudinalAxis = Literal["X", "Y"]

# Borde de la zapata contra el que se apoya el lindero, en la convención de ejes
# del motor: X_MIN es el borde de menor x, X_MAX el de mayor x.
EdgeSide = Literal["X_MIN", "X_MAX", "Y_MIN", "Y_MAX"]

_EDGE_AXIS: dict[str, str] = {
    "X_MIN": "X", "X_MAX": "X", "Y_MIN": "Y", "Y_MAX": "Y",
}
# Signo del desplazamiento necesario para acercar la columna a ese borde.
_EDGE_SIGN: dict[str, float] = {
    "X_MIN": -1.0, "X_MAX": +1.0, "Y_MIN": -1.0, "Y_MAX": +1.0,
}


class AnalysisModel(str, Enum):
    """Los dos modelos que el programa debe soportar. Sin valor por defecto.

    Los apuntes CR2-93-134 §3.6 resuelven un problema con cada uno, y en ninguno de
    los dos casos la elección sale de una norma: la declara el proyectista.

    ARTICULADO      Problema de aplicación 1. La viga se une a la zapata interior
                    mediante una articulación y esa zapata actúa de contrapeso.
    CUERPO_RIGIDO   Problema de aplicación 2, que lo declara expresamente: «el modelo
                    de análisis será el de un cuerpo rígido para el conjunto de 2
                    zapatas y la viga de conexión pues la viga lleva esfuerzos de la
                    zapata izquierda a la zapata derecha y viceversa».
    """

    ARTICULADO = "ARTICULADO"
    CUERPO_RIGIDO = "CUERPO_RIGIDO"


class CoupleTransferMode(str, Enum):
    """TBD-C11 — dónde va la rama CERCANA del par que reparte la viga.

    El par que la viga arranca de la zapata de lindero tiene dos ramas, separadas la
    distancia entre ejes de columnas. La rama lejana llega siempre a la zapata
    interior. La cercana admite dos destinos, y la elección cambia los resultados.

    NO TIENE VALOR POR DEFECTO. Ninguna norma lo arbitra: E.060 no tiene artículo para
    la zapata conectada. Los apuntes CR2-93-134 §3.6 usan uno de los dos sin discutir
    el otro, y usarlos como autoridad sería tratarlos como norma.
    """

    EQUILIBRIO_EN_CIMENTACION = "EQUILIBRIO_EN_CIMENTACION"
    """La rama cercana la toma la propia zapata de lindero. El equilibrio vertical
    CIERRA sobre la cimentación sola: lo que una zapata deja de recibir lo recibe la
    otra, y la suma de las cargas corregidas iguala la de las aplicadas.

    Consecuencia: la reacción de la zapata de lindero se amplifica sobre la carga de
    su columna. Es la lectura más exigente para esa zapata."""

    PAR_PURO_EN_ZAPATA = "PAR_PURO_EN_ZAPATA"
    """La viga transmite a la zapata de lindero el PAR que centra su resultante, y la
    rama cercana de ese par la absorbe la columna y el pórtico de arriba, fuera de la
    cimentación.

    DEFINICIÓN (Fase 9c, formulación B*): **la rama transmitida al pórtico corresponde
    exclusivamente al par; las cargas verticales gravitacionales de la viga se
    transmiten mediante sus reacciones.** Sin peso propio de viga modelado, la reacción
    de la zapata de lindero vale exactamente la carga de su columna. Con peso EXPLICITO,
    la viga —apoyada en el nudo de la columna exterior y en la rótula interior— entrega
    a la zapata de lindero su reacción gravitatoria N_a = W_V·(s_corte − x_V)/S, que
    entra como carga de nudo igual que la de la columna, y a la zapata interior el
    resto. Ninguna parte del peso va al pórtico.

    Es el procedimiento de los apuntes CR2-93-134 §3.6, problema 1: R = P + p.p. sin
    amplificar. Los apuntes no modelan el peso de la viga; la extensión B* se deriva por
    cuerpo libre (`docs/fase9ac_peso_propio_viga.md`) y con peso DESPRECIADO coincide
    con el procedimiento del libro bit a bit.

    Consecuencia declarada: **la carga vertical NO se conserva dentro de la
    cimentación**. Faltan exactamente las toneladas de la rama del par, ΔP = −C_Z/S,
    que se suponen recogidas por la estructura; el peso de la viga no falta nunca. Es una hipótesis sobre el comportamiento del
    pórtico, no un error de cálculo, pero deja la zapata interior MÁS aliviada de lo
    que quedaría si la cimentación tuviera que equilibrarse sola."""


def check_couple_mode_compatible(
    analysis_model: "AnalysisModel", couple_transfer_mode: CoupleTransferMode
) -> None:
    """Rechaza `CUERPO_RIGIDO × PAR_PURO_EN_ZAPATA` — Fase 5A, defecto D1.

    NO ES UNA PREFERENCIA: LAS DOS HIPÓTESIS SE EXCLUYEN
    ====================================================
    `PAR_PURO_EN_ZAPATA` se DEFINE por dos condiciones: la reacción de la zapata de
    lindero vale exactamente la carga de su columna (`R_ext = P_ext`), y la carga
    vertical no se conserva dentro de la cimentación porque el pórtico recoge la rama
    cercana del par.

    `CUERPO_RIGIDO` es un sistema estáticamente DETERMINADO: el campo lineal de presión
    lo fijan ΣF = 0 y ΣM = 0 sobre el conjunto, `R_ext` sale de integrar ese campo y la
    carga se conserva por construcción. No queda ningún grado de libertad sobre el que
    imponer `R_ext = P_ext`: hacerlo es añadir una ecuación a un sistema que ya está
    resuelto, y solo se cumpliría por coincidencia.

    Antes de 5A la combinación se aceptaba: el reparto la resolvía como rígida —ignorando
    el modo— y la viga como par puro articulado. Dos equilibrios incompatibles en un
    mismo resultado, mientras la traza afirmaba que el modo «no interviene».

    POR QUÉ SE RECHAZA Y NO SE IGNORA
    =================================
    Tratarla como inerte dejaría declarada en el informe una hipótesis que la salida no
    cumple. `EQUILIBRIO_EN_CIMENTACION` sí es aplicable en cuerpo rígido: enuncia lo que
    ese modelo hace —la cimentación cierra su equilibrio sola—.

    DÓNDE SE LLAMA
    ==============
    Desde el validador de `ConnectedFootingLayout`, y también a la entrada de
    `distribute_couple` y de `solve_connecting_beam`: `model_copy(update=…)` de
    pydantic v2 NO ejecuta validadores, y es un camino habitual para variar un layout.
    Una sola función para los tres puntos, de modo que el criterio no pueda divergir."""
    if (
        analysis_model is AnalysisModel.CUERPO_RIGIDO
        and couple_transfer_mode is CoupleTransferMode.PAR_PURO_EN_ZAPATA
    ):
        raise ValueError(
            "Combinación incompatible: CUERPO_RIGIDO con PAR_PURO_EN_ZAPATA. El modo de "
            "par puro exige que la reacción de la zapata de lindero iguale la carga de su "
            "columna y que la carga no se conserve en la cimentación; el cuerpo rígido "
            "determina esa reacción por equilibrio global y conserva la carga. Las dos "
            "hipótesis se excluyen. En CUERPO_RIGIDO solo es aplicable "
            "EQUILIBRIO_EN_CIMENTACION; para usar el par puro declare ARTICULADO."
        )


def check_beam_support_supported(support_mode: "BeamSupportMode") -> None:
    """Rechaza `APOYA_EN_SUELO` — decisión del proyectista sobre TBD-C4, 2026-09-20.

    POR QUÉ RECHAZAR Y NO DEJARLO EN NO VERIFICADO
    ==============================================
    Un NO VERIFICADO dice «no puedo demostrar esto», y es la respuesta correcta cuando el
    resto del resultado sigue siendo el del problema que el usuario planteó. Aquí no lo
    es: el motor resolvería una viga que salva el vano sin apoyo, que es OTRO problema, y
    entregaría geometrías, esfuerzos y acero de ese otro problema con una nota al pie. El
    error va del lado inseguro en la zapata interior.

    Admitirlo más adelante no es cuestión de levantar esta validación: hay que definir el
    modelo resistente del apoyo y cómo se reparten las acciones entre viga, terreno y
    zapatas. Eso es una decisión de ingeniería nueva, no un pendiente que se cierre solo.

    DÓNDE SE LLAMA. Desde el validador de `ConnectedFootingLayout` y a la entrada del
    solver, por la misma razón que `check_couple_mode_compatible`: `model_copy(update=…)`
    de pydantic v2 no ejecuta validadores."""
    if support_mode is BeamSupportMode.APOYA_EN_SUELO:
        raise ValueError(
            "Modo de apoyo no admitido en esta versión: APOYA_EN_SUELO. Este motor no "
            "modela la reacción del terreno bajo la viga de conexión, e ignorarla "
            "sobrestima ΔP y deja la zapata INTERIOR menos cargada de lo que estaría en "
            "realidad, del lado inseguro. Admitirlo exige definir el modelo resistente de "
            "la viga sobre el terreno y la transferencia de acciones (TBD-C4). Declare "
            "SIN_APOYO, que es la hipótesis que el motor resuelve."
        )


class StiffnessDeclaration(str, Enum):
    """TBD-C1 — declaración del proyectista sobre E.060 §15.2.6 (decisión 4, 2026-09-20).

    QUÉ PREGUNTA, Y POR QUÉ HAY QUE PREGUNTARLA
    ===========================================
    E.060 §15.2.6 **exige** evaluar el comportamiento de las vigas de conexión «de acuerdo
    a su rigidez y la del conjunto suelo-cimentación». Es un requisito normativo real. Lo
    que la norma NO da es método ni umbral, y ninguna fuente del proyecto lo suple: el
    motor no puede responderla por su cuenta sin inventar un criterio.

    Hasta aquí eso dejaba TODA terna conectada en NO VERIFICADO para siempre, sin salida
    posible. La decisión 4 abre la única salida legítima: que la responda quien puede
    responderla, igual que ya declara μ, los FS o el factor de carga muerta del peso de la
    viga. El motor no la evalúa; la **registra**, con su autor y su alcance.

    SIN VALOR POR DEFECTO
    =====================
    Por la misma razón que `BeamSelfWeightMode` y `BeamSupportMode`: un valor por defecto
    respondería la pregunta en silencio. Quien no declare nada obtiene
    `NO_EVALUADA`, que es lo que había antes y deja la terna en NO VERIFICADO.

    LA DECLARACIÓN NO CONVIERTE EL RESULTADO EN CONFORME
    ====================================================
    Solo levanta ESTE bloqueo de aplicabilidad. El resto de las verificaciones siguen
    teniendo que salir PASS o INFO, y cualquier otro TBD abierto —C11 con `PAR_PURO`, por
    ejemplo— sigue impidiendo el CONFORME por su cuenta. Está comprobado en
    `tests/test_tbd_c1_declaracion_rigidez.py`."""

    NO_EVALUADA = "NO_EVALUADA"
    """Nadie se ha pronunciado. La premisa queda NO VERIFICADA, como hasta el 2026-09-20."""

    DECLARADA_POR_PROYECTISTA = "DECLARADA_POR_PROYECTISTA"
    """El proyectista declara, bajo su responsabilidad, que el modelo adoptado para la
    viga de conexión y el conjunto suelo-cimentación satisface la condición de
    comportamiento de E.060 §15.2.6.

    **El motor no lo comprueba y no dice que lo haya comprobado.** Lo que cambia es de
    quién es la afirmación: pasa de ser una hipótesis del programa sin respaldo a ser una
    declaración del profesional responsable, que es exactamente la figura con que la norma
    reparte estas decisiones. La traza lo dice así, y el informe lo reproduce."""


class BeamSelfWeightMode(str, Enum):
    """TBD-C5 — qué se hace con el peso propio de la viga de conexión.

    NO TIENE VALOR POR DEFECTO, y la razón es concreta. El motor de zapata calcula el
    peso propio de CADA ZAPATA, pero nadie calcula el de la VIGA. Un valor por defecto
    de «no incluir» dejaba ese peso sin aparecer en ninguna parte mientras la hipótesis
    afirmaba que quedaba «absorbido en el porcentaje global» —porcentaje que este motor
    no aplica—. Era una omisión presentada como cobertura.

    Las tres alternativas cubren lo que puede hacer un proyectista, y ninguna es
    normativa: E.060 y E.050 no dicen nada sobre cómo contabilizar el peso propio de
    una viga de cimentación.
    """

    EXPLICITO = "EXPLICITO"
    """El motor calcula el peso de la viga POR GEOMETRÍA FÍSICA y lo introduce en el
    equilibrio. Única opción en que el peso de la viga influye sobre el reparto.

    Exige declarar la cota vertical de la viga (`soffit_above_base_m`, z_b), sin valor
    por defecto: el tramo de viga que queda sobre cada zapata solo agrega el volumen que
    no cuentan ya el concreto y el relleno de la zapata, y eso depende de la cota. Se
    descompone en ΔW_e (sobre la huella exterior), W_V (vano libre) y ΔW_i (sobre la
    huella interior). Ver `connected_statics.BeamSelfWeightBreakdown`.

    El relleno que pueda quedar SOBRE la viga en el vano libre NO está incluido: es un
    pendiente declarado (Fase 9a), no un peso propio."""

    EN_CARGAS_DE_COLUMNA = "EN_CARGAS_DE_COLUMNA"
    """El usuario declara que ya lo incluyó en las cargas P que entrega. El motor NO lo
    vuelve a sumar —contarlo dos veces es el error que esta opción evita—."""

    DESPRECIADO = "DESPRECIADO"
    """Se omite deliberadamente. Es admisible y frecuente, pero queda registrado como
    omisión consciente y no como cobertura inexistente."""


class BeamSupportMode(str, Enum):
    """TBD-C4 — si la viga de conexión transmite presión al terreno.

    Sin valor por defecto por la misma razón. Ninguna norma lo prescribe: depende de
    cómo se construya —sobre relleno suelto, con junta, o apoyada—.
    """

    SIN_APOYO = "SIN_APOYO"
    """La viga salva el vano sin reacción del terreno. Es la hipótesis que el motor
    SÍ sabe resolver."""

    APOYA_EN_SUELO = "APOYA_EN_SUELO"
    """La viga se apoya en el terreno. **RECHAZADO POR VALIDACIÓN** desde el 2026-09-20
    (decisión del proyectista sobre TBD-C4).

    Este motor no modela esa reacción, y hasta esa fecha el caso se aceptaba dejando la
    terna en NO VERIFICADO. El problema del NO VERIFICADO aquí es que el resultado sale
    igualmente, con números que describen otro problema: ignorar el apoyo sobrestima ΔP,
    y como la carga corregida de la zapata interior es `P_int − ΔP`, esa zapata queda
    MENOS cargada de lo que estaría en realidad. La exterior queda del lado seguro; la
    interior, no.

    Admitirlo exigiría definir explícitamente el modelo resistente de la viga sobre el
    terreno y la transferencia de acciones entre viga, suelo y zapatas. Mientras eso no
    se decida, el valor se rechaza a la entrada en vez de producir un diseño que nadie
    puede usar. Es el mismo criterio con que D1 rechaza `CUERPO_RIGIDO × PAR_PURO`."""


class EdgeAnchor(BaseModel):
    """Condición geométrica que se MANTIENE durante el barrido de geometrías.

    Lo invariante es `face_clearance_m`, la distancia de la cara de la columna al
    borde de la zapata. Vale cero cuando la cara queda al ras del límite de
    propiedad, que es el caso canónico de la zapata conectada.
    """

    edge: EdgeSide = Field(
        ..., description="Borde de la zapata contra el que se apoya el lindero"
    )
    face_clearance_m: float = Field(
        default=0.0,
        ge=0.0,
        description=(
            "Distancia entre la CARA de la columna y el borde de la zapata [m]. Cero = "
            "cara al ras del lindero. Es lo que permanece constante al variar B y L."
        ),
    )

    @property
    def axis(self) -> str:
        return _EDGE_AXIS[self.edge]

    def axis_distance_to_column_center_m(self, column: Column) -> float:
        """Distancia del borde al EJE de la columna. Es `a` en las ecuaciones de
        equilibrio: la cara más media dimensión de la columna."""
        ancho = column.bx_m if self.axis == "X" else column.by_m
        return self.face_clearance_m + ancho / 2.0

    def placement_for(self, column: Column, B_m: float, L_m: float) -> ColumnPlacement:
        """Deriva el `ColumnPlacement` que corresponde a ESTA geometría.

        Es el punto entero de esta clase: el desplazamiento se recalcula para cada
        (B, L) del barrido, de modo que la condición de borde se conserva en vez de
        romperse en silencio al crecer la zapata."""
        a = self.axis_distance_to_column_center_m(column)
        if self.axis == "X":
            # El eje de la columna queda a distancia `a` del borde; el desplazamiento
            # respecto del CENTRO es la diferencia con B/2, con el signo del borde.
            offset = _EDGE_SIGN[self.edge] * (B_m / 2.0 - a)
            return ColumnPlacement(column=column, offset_x_m=offset, offset_y_m=0.0)
        offset = _EDGE_SIGN[self.edge] * (L_m / 2.0 - a)
        return ColumnPlacement(column=column, offset_x_m=0.0, offset_y_m=offset)

    def offset_sign(self) -> float:
        """Signo del desplazamiento que acerca la columna a este borde.

        Lo necesita la estática para saber hacia qué lado actúa el par que la viga
        transmite a la zapata de lindero."""
        return _EDGE_SIGN[self.edge]

    def fits_in(self, column: Column, B_m: float, L_m: float) -> bool:
        """¿Cabe la columna con esta holgura dentro de la geometría dada?"""
        dim = B_m if self.axis == "X" else L_m
        return dim >= 2.0 * self.axis_distance_to_column_center_m(column) - 1e-9


class ConnectedElement(BaseModel):
    """Una de las dos zapatas del sistema, con su columna y sus cargas.

    `anchor` describe la zapata de LINDERO; la interior lo deja en `None` y se
    resuelve concéntrica, que es el caso habitual."""

    label: str = Field(..., min_length=1)
    column: Column
    loads: LoadCaseSet
    anchor: EdgeAnchor | None = Field(
        default=None,
        description="Condición de borde. None = columna concéntrica sobre su zapata.",
    )
    # 2026-09-28 (campo aditivo). El gancho NUNCA se asume: lo declara el proyectista, por
    # zapata y por dirección. Sin declararlo, barra recta, como hasta ahora. Existe porque
    # E.060 §15.6.2 exige desarrollar la tracción a cada lado de la cara de la columna y,
    # en la zapata de lindero, hacia el lindero solo queda el ancho de la columna: con
    # columnas habituales la barra recta no cabe y en obra se resuelve con gancho.
    hook_type_x: Literal["ninguno", "90", "180"] = Field(
        default="ninguno", description="Gancho declarado en las barras de la dirección X."
    )
    hook_type_y: Literal["ninguno", "90", "180"] = Field(
        default="ninguno", description="Gancho declarado en las barras de la dirección Y."
    )

    def placement_for(self, B_m: float, L_m: float) -> ColumnPlacement:
        if self.anchor is None:
            return ColumnPlacement(column=self.column)
        return self.anchor.placement_for(self.column, B_m, L_m)


class ConnectingBeamSpec(BaseModel):
    """La viga de conexión. Su diseño lo resuelve `beam/connecting_beam.py`; aquí
    solo se declara su geometría y las hipótesis de modelación que la afectan."""

    b_m: float = Field(..., gt=0)
    h_m: float = Field(..., gt=0)
    d_m: float = Field(..., gt=0, description="Peralte efectivo")

    stiffness_declaration: StiffnessDeclaration = Field(
        default=StiffnessDeclaration.NO_EVALUADA,
        description=(
            "TBD-C1: declaración del proyectista sobre E.060 §15.2.6. El defecto es "
            "NO_EVALUADA, que es no declarar nada y deja la premisa en NO VERIFICADO: no "
            "responde la pregunta en silencio, y por eso puede tener defecto."
        ),
    )
    support_mode: BeamSupportMode = Field(
        ..., description="TBD-C4. OBLIGATORIO: ninguna norma lo prescribe."
    )
    self_weight_mode: BeamSelfWeightMode = Field(
        ..., description="TBD-C5. OBLIGATORIO: ninguna norma lo prescribe."
    )
    concrete_unit_weight_kNm3: float = Field(default=24.0, gt=0)
    self_weight_dead_load_factor: float | None = Field(
        default=None,
        ge=0.0,
        description=(
            "TBD-C13, MODO DIRECTO. Factor de CARGA MUERTA que el proyectista declara para el "
            "peso propio de la viga en las combinaciones FACTORIZADAS formadas a mano. SIN "
            "VALOR POR DEFECTO: el motor recibe la combinación ya formada y no puede inferir "
            "con qué factor de CM se armó, y ese factor cambia entre combinaciones (E.060 "
            "§9.2). Si no se declara, la entrada `beam_self_weight_mode` queda NO VERIFICADA. "
            "En el modo de cargas POR CASOS no interviene: el factor sale de la composición."
        ),
    )
    soffit_above_base_m: float | None = Field(
        default=None,
        description=(
            "z_b — altura del FONDO de la viga sobre la base común de cimentación [m]. "
            "OBLIGATORIA con self_weight_mode = EXPLICITO y sin valor por defecto: el motor "
            "no define la cota vertical de la viga, y el peso que la viga agrega sobre las "
            "zapatas depende de ella. No se admite con los otros dos modos."
        ),
    )

    @property
    def models_self_weight(self) -> bool:
        """¿Entra el peso propio de la viga en las ecuaciones de equilibrio?

        Solo con EXPLICITO. En los otros dos casos vale cero en el equilibrio, pero por
        razones DISTINTAS que la traza registra por separado."""
        return self.self_weight_mode is BeamSelfWeightMode.EXPLICITO

    @model_validator(mode="after")
    def _cota_vertical_declarada(self) -> "ConnectingBeamSpec":
        """z_b solo existe con EXPLICITO, y con EXPLICITO es obligatoria (Fase 9a)."""
        if self.self_weight_mode is BeamSelfWeightMode.EXPLICITO:
            if self.soffit_above_base_m is None:
                raise ValueError(
                    "Con peso propio de viga EXPLICITO hay que declarar la cota vertical de "
                    "la viga, z_b = altura de su fondo sobre la base de cimentación. No tiene "
                    "valor por defecto: el peso que la viga agrega sobre cada zapata depende "
                    "de ella."
                )
            if self.soffit_above_base_m < 0.0:
                raise ValueError(
                    f"ENTRADA_INVALIDA: z_b = {self.soffit_above_base_m:.3f} m deja el fondo "
                    f"de la viga por debajo de la base de cimentación. Esa geometría cambia "
                    f"el nivel de apoyo de las zapatas y este modelo no la representa."
                )
        elif self.soffit_above_base_m is not None:
            raise ValueError(
                f"z_b solo se declara con peso propio de viga EXPLICITO; con "
                f"{self.self_weight_mode.value} no interviene en ningún cálculo y admitirla "
                f"sugeriría lo contrario."
            )
        return self

    @model_validator(mode="after")
    def _factor_de_peso_solo_con_explicito(self) -> "ConnectingBeamSpec":
        """TBD-C13. Igual que z_b: el dato solo tiene sentido con EXPLICITO, y admitirlo con
        los otros modos sugeriría que interviene en algún cálculo."""
        if (
            self.self_weight_dead_load_factor is not None
            and self.self_weight_mode is not BeamSelfWeightMode.EXPLICITO
        ):
            raise ValueError(
                f"El factor de carga muerta del peso propio de la viga solo se declara con "
                f"peso propio EXPLICITO; con {self.self_weight_mode.value} el peso no entra "
                f"en el equilibrio y el factor no se aplicaría a nada."
            )
        return self

    @model_validator(mode="after")
    def _peralte_coherente(self) -> "ConnectingBeamSpec":
        if self.d_m >= self.h_m:
            raise ValueError(
                f"El peralte efectivo d = {self.d_m:.3f} m no puede igualar ni superar el "
                f"peralte total h = {self.h_m:.3f} m: la diferencia es el recubrimiento "
                f"hasta el centroide del refuerzo."
            )
        return self


class Footprint(BaseModel):
    """Una huella de apoyo sobre el eje longitudinal.

    `length_m` corre A LO LARGO de la viga; `width_m` es la dimensión transversal.
    Distinguirlas importa: el momento de inercia de la sección compuesta que usa el
    modelo de cuerpo rígido va con el cubo de la longitudinal."""

    length_m: float = Field(..., gt=0, description="Dimensión a lo largo de la viga")
    width_m: float = Field(..., gt=0, description="Dimensión transversal")
    h_m: float = Field(..., gt=0)
    start_m: float = Field(..., description="Coordenada s del borde inicial")

    @property
    def end_m(self) -> float:
        return self.start_m + self.length_m

    @property
    def centroid_m(self) -> float:
        return self.start_m + self.length_m / 2.0

    @property
    def area_m2(self) -> float:
        return self.length_m * self.width_m


class Footprints(BaseModel):
    """Las dos huellas del sistema, ya situadas sobre el eje longitudinal.

    POR QUÉ EXISTE ESTE TIPO
    ========================
    La estrategia ARTICULADA solo necesitaba la longitud de la zapata de lindero: su
    reparto sale de un cuerpo libre que no mira a la huella interior. La de CUERPO
    RÍGIDO necesita las DOS, porque el área de apoyo, su centroide y su momento de
    inercia —que son lo que determina la presión— dependen de ambas.

    Pasarlas juntas, ya situadas, evita que cada estrategia tenga que reconstruir la
    geometría a partir de la geometría de búsqueda, que es donde se cuelan los errores
    de origen de coordenadas."""

    exterior: Footprint
    interior: Footprint

    @property
    def total_area_m2(self) -> float:
        return self.exterior.area_m2 + self.interior.area_m2

    @property
    def centroid_m(self) -> float:
        """Centroide del ÁREA DE APOYO. El vano entre huellas no aporta."""
        return (
            self.exterior.area_m2 * self.exterior.centroid_m
            + self.interior.area_m2 * self.interior.centroid_m
        ) / self.total_area_m2

    @property
    def inertia_m4(self) -> float:
        """Momento de inercia de las dos huellas como una sola sección compuesta.

        Verificado contra los apuntes CR2-93-134 §3.6 problema 2: con las huellas del
        libro sale I = 320,36 m⁴, su valor exacto."""
        x_c = self.centroid_m
        total = 0.0
        for f in (self.exterior, self.interior):
            total += f.width_m * f.length_m**3 / 12.0
            total += f.area_m2 * (x_c - f.centroid_m) ** 2
        return total

    @property
    def start_m(self) -> float:
        return self.exterior.start_m

    @property
    def end_m(self) -> float:
        return self.interior.end_m

    def width_at(self, s_m: float) -> float:
        """Ancho transversal con apoyo en `s`. Cero en el vano entre huellas."""
        for f in (self.exterior, self.interior):
            if f.start_m - 1e-12 <= s_m <= f.end_m + 1e-12:
                return f.width_m
        return 0.0

    @model_validator(mode="after")
    def _huellas_separadas(self) -> "Footprints":
        """Las dos huellas no pueden solaparse ni tocarse.

        NO ES UNA EXIGENCIA NORMATIVA: es el límite de validez de este tipo. Todo lo que
        publica `Footprints` supone dos áreas DISJUNTAS —`total_area_m2` las suma,
        `inertia_m4` las compone como dos rectángulos separados y `width_at` devuelve el
        ancho de la primera que contenga `s`—. Con solape, el área y la inercia salen
        por exceso, la presión del modelo de cuerpo rígido sale por defecto, y el
        resultado sería NO CONSERVADOR sin que nada lo delate. Se corta aquí, en la
        geometría, y no aguas abajo donde el síntoma ya no señala a la causa.

        El contacto exacto tampoco se admite: sin vano no hay viga de conexión que
        salvar, y la tipología deja de ser la que este motor resuelve."""
        vano = self.interior.start_m - self.exterior.end_m
        if vano <= 1e-9:
            raise ValueError(
                f"GEOMETRIA_IMPOSIBLE: las huellas se solapan o se tocan (vano libre = "
                f"{vano:+.3f} m). La zapata de lindero llega a s = {self.exterior.end_m:.3f} m "
                f"y la interior arranca en s = {self.interior.start_m:.3f} m. Acorte la "
                f"zapata de lindero, acorte la interior, o separe más las columnas. Si las "
                f"zapatas han de tocarse, la tipología no es una zapata conectada."
            )
        return self


class ConnectedFootingLayout(BaseModel):
    """El sistema completo: dos zapatas, una viga y un modelo de análisis."""

    analysis_model: AnalysisModel = Field(
        ...,
        description=(
            "OBLIGATORIO, sin valor por defecto. Ninguna norma dice cuál corresponde: "
            "lo elige el ingeniero y queda registrado como hipótesis."
        ),
    )
    exterior: ConnectedElement
    interior: ConnectedElement
    beam: ConnectingBeamSpec

    couple_transfer_mode: CoupleTransferMode = Field(
        ...,
        description=(
            "TBD-C11. OBLIGATORIO: ninguna norma arbitra dónde va la rama cercana del "
            "par. Cambia la reacción de la zapata de lindero y la carga de la interior."
        ),
    )

    axis_distance_m: float = Field(
        ..., gt=0, description="Distancia entre EJES de las dos columnas [m]"
    )
    longitudinal_axis: LongitudinalAxis = Field(
        default="X", description="Eje sobre el que corre la viga de conexión"
    )

    def footprints(
        self, ext_B_m: float, ext_L_m: float, ext_h_m: float,
        int_B_m: float, int_L_m: float, int_h_m: float,
    ) -> Footprints:
        """Sitúa las dos huellas sobre el eje longitudinal.

        Origen en el borde de lindero. La zapata exterior arranca allí; la interior va
        CENTRADA sobre su columna, que es el caso que resuelve el motor —su `anchor` es
        None y `evaluate_candidate` la trata como concéntrica—."""
        longitudinal = self.longitudinal_axis == "X"
        ext_len = ext_B_m if longitudinal else ext_L_m
        ext_wid = ext_L_m if longitudinal else ext_B_m
        int_len = int_B_m if longitudinal else int_L_m
        int_wid = int_L_m if longitudinal else int_B_m

        a = self.exterior.anchor.axis_distance_to_column_center_m(self.exterior.column)
        x_col_int = a + self.axis_distance_m
        return Footprints(
            exterior=Footprint(length_m=ext_len, width_m=ext_wid, h_m=ext_h_m, start_m=0.0),
            interior=Footprint(
                length_m=int_len, width_m=int_wid, h_m=int_h_m,
                start_m=x_col_int - int_len / 2.0,
            ),
        )

    @model_validator(mode="after")
    def _sistema_coherente(self) -> "ConnectedFootingLayout":
        check_couple_mode_compatible(self.analysis_model, self.couple_transfer_mode)
        check_beam_support_supported(self.beam.support_mode)
        if self.exterior.anchor is None:
            raise ValueError(
                "La zapata exterior de un sistema conectado debe declarar su `anchor`: es "
                "la zapata de lindero y su condición de borde es lo que genera el par que "
                "la viga reparte. Sin ella no hay nada que conectar."
            )
        if self.exterior.anchor.axis != self.longitudinal_axis:
            raise ValueError(
                f"El borde declarado ({self.exterior.anchor.edge}) está sobre el eje "
                f"{self.exterior.anchor.axis}, pero la viga corre sobre el eje "
                f"{self.longitudinal_axis}. El par solo se reparte a lo largo de la viga."
            )
        if self.exterior.label == self.interior.label:
            raise ValueError("Las dos zapatas deben tener etiquetas distintas.")
        nombres_ext = {c.name for c in self.exterior.loads.service + self.exterior.loads.factored}
        nombres_int = {c.name for c in self.interior.loads.service + self.interior.loads.factored}
        if nombres_ext != nombres_int:
            faltan = sorted(nombres_ext ^ nombres_int)
            raise ValueError(
                f"Las dos columnas deben declarar las MISMAS combinaciones de carga: el "
                f"reparto del par se resuelve combinación a combinación, no sobre "
                f"envolventes. Sin pareja: {faltan}."
            )
        return self
