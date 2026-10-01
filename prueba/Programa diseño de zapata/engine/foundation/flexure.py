"""Diseño a flexión en la sección crítica (cara de columna, E.060 §15.4.2).

Convención de direcciones (coherente con engine/soil/eccentricity.py):
    - "Dirección X": voladizo de longitud (B - bx)/2 a cada lado de la columna,
      a lo largo del eje X. El acero que resiste este momento corre PARALELO al
      eje X (igual que el refuerzo principal de una losa en voladizo corre en la
      dirección del voladizo). El momento depende solo de `ex` (el término de
      `ey` se cancela al integrar sobre el ancho completo L, ver docstring de
      `net_pressure_per_length_x`).
    - "Dirección Y": análogo, voladizo (L - by)/2 a lo largo de Y, acero paralelo
      a Y, momento depende solo de `ey`.

Presión usada: la presión NETA FACTORIZADA producida únicamente por la reacción
del suelo ante las cargas amplificadas de columna (Pu, Mux, Muy), SIN incluir el
peso propio de la zapata ni el relleno. Esto es una simplificación estándar de
diseño de zapatas (no una ecuación normativa numerada): el peso propio y el
relleno se autoequilibran localmente con la reacción del suelo bajo esa misma
área y no producen cortante ni momento neto en la sección de concreto -- ver
justificación en docs/normativa/ (a documentar formalmente si el usuario lo
requiere). Fundamento indirecto: E.060 §15.2 exige diseñar "para resistir las
cargas amplificadas ... y las reacciones inducidas".
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

from engine.codes.base import IConcreteCode
from engine.foundation.unilateral_contact import (
    ContactFieldImpossible,
    solve_unilateral_contact,
)
from engine.results.status import CheckStatus
from engine.units.si_units import kn_to_n, m_to_mm, mm_to_m


class FlexureResult(BaseModel):
    Mu_kNm: float
    cantilever_m: float
    As_required_m2: float
    As_min_m2: float
    As_design_m2: float
    rho_min: float
    rho_min_reference: str
    status: CheckStatus
    note: str


class NetPressureField(BaseModel):
    """Campo de presión neta factorizada q'(s) [kN/m] a lo largo de una dirección.

    `s` se mide desde el borde de MAYOR presión hacia el interior, y el campo ya está
    integrado sobre todo el ancho perpendicular: por eso ese ancho no aparece y el
    resultado queda en kN por metro de `dim_m`. El término de la excentricidad
    perpendicular se cancela por simetría al integrar sobre el ancho completo (ver el
    docstring del módulo).

    DOS REGÍMENES, Y POR QUÉ HAY DOS
    ================================
    **Contacto total** (`e <= dim/6`): la resultante cae en el núcleo central y el campo
    lineal clásico vale en toda la huella.

        q'(0) = (Pu/dim)·(1 + 6e/dim)        q'(dim) = (Pu/dim)·(1 − 6e/dim)

    **Contacto parcial** (`e > dim/6`): parte de la zapata se levanta. E.060 §15.2.3 no
    admite tracciones, de modo que la zapata solo apoya sobre una longitud

        a = 3·(dim/2 − e)

    y el bloque es TRIANGULAR, con el vértice en el borde comprimido:

        q'(0) = 2·Pu/a        q'(s) = q'(0)·(1 − s/a)        q'(s > a) = 0

    Las dos expresiones salen de imponer equilibrio —la resultante vale Pu y pasa por el
    punto excéntrico—, no de ninguna prescripción: es estática.

    QUÉ ESTABA MAL ANTES (decisión B, 2026-09-19)
    =============================================
    Hasta aquí el motor usaba SIEMPRE el campo lineal y recortaba a cero las presiones
    negativas. Esa recortada **no equilibra la carga**: su resultante es menor que Pu y
    está peor situada, de modo que Mu y Vu quedaban SUBESTIMADOS justo en los casos más
    exigentes. Ocurría también con el modelo de contacto por defecto, porque la
    excentricidad que gobierna el diseño se calcula con las cargas FACTORIZADAS y sin
    peso propio, y puede salirse del núcleo aunque la de servicio no lo haga.

    Detalle en `docs/area_efectiva_e050_art28.md` §6."""

    q_high_kN_m: float = Field(..., description="q' en el borde de mayor presión, s = 0")
    slope_kN_m2: float = Field(..., description="dq'/ds, siempre <= 0")
    contact_length_m: float = Field(..., description="Longitud comprimida desde s = 0")
    dim_m: float
    full_contact: bool = Field(..., description="False si parte de la huella se levanta")
    equilibrium_possible: bool = Field(
        default=True,
        description=(
            "False si e >= dim/2: la resultante cae fuera de la huella y no hay ningún "
            "campo de presiones que la equilibre. El campo se devuelve nulo y quien llama "
            "obtiene Mu = Vu = 0; el candidato ya está descartado por la presión de "
            "contacto, en cualquiera de los dos modelos."
        ),
    )

    def q_at(self, s_m: float) -> float:
        """q'(s) [kN/m], con s medido desde el borde de mayor presión.

        La comparación es ESTRICTA (`s > a`): en `s = a` el borde del bloque triangular
        vale cero por la propia recta, y con contacto total `a = dim`, de modo que un
        `>=` habría anulado la presión en el borde opuesto y roto el equilibrio. Lo
        detectó la comprobación de que la resultante vale Pu."""
        if s_m > self.contact_length_m:
            return 0.0
        return max(self.q_high_kN_m + self.slope_kN_m2 * max(s_m, 0.0), 0.0)

    def force_and_moment(
        self, s_from_m: float, s_to_m: float, s_face_m: float
    ) -> tuple[float, float]:
        """(F [kN], M [kN·m]) de la presión sobre [s_from, s_to], tomando momentos en
        `s_face`. Integración exacta de un trapecio, truncado donde acaba el contacto.

        El centroide de un trapecio de ordenadas q1 y q2 sobre una longitud ℓ está a
        ℓ·(q1 + 2·q2)/(3·(q1 + q2)) del extremo de q1. Con q2 = 0 da ℓ/3, que es el
        centroide del triángulo; con q1 = q2 da ℓ/2. Las dos comprobaciones están en
        `tests/test_bloque_triangular_diseno.py`."""
        lo = max(s_from_m, 0.0)
        hi = min(s_to_m, self.contact_length_m)
        if hi <= lo:
            return 0.0, 0.0
        q1, q2 = self.q_at(lo), self.q_at(hi)
        largo = hi - lo
        fuerza = (q1 + q2) / 2.0 * largo
        suma = q1 + q2
        centroide = lo + (largo * (q1 + 2.0 * q2) / (3.0 * suma) if suma > 0 else largo / 2.0)
        return fuerza, fuerza * abs(centroide - s_face_m)


def net_pressure_field(
    P_u_column_kN: float, e_m: float, dim_along_e_m: float
) -> NetPressureField:
    """Campo q'(s) de la presión neta factorizada. `e_m` es la excentricidad en valor
    absoluto; `s` se mide desde el borde hacia el que se desplaza la resultante."""
    e = abs(e_m)
    dim = dim_along_e_m
    if e <= dim / 6.0 + 1e-12:
        q_avg = P_u_column_kN / dim
        q_high = q_avg * (1.0 + 6.0 * e / dim)
        q_low = q_avg * (1.0 - 6.0 * e / dim)
        return NetPressureField(
            q_high_kN_m=q_high, slope_kN_m2=(q_low - q_high) / dim,
            contact_length_m=dim, dim_m=dim, full_contact=True,
        )
    a = 3.0 * (dim / 2.0 - e)
    if a <= 0.0:
        return NetPressureField(
            q_high_kN_m=0.0, slope_kN_m2=0.0, contact_length_m=0.0, dim_m=dim,
            full_contact=False, equilibrium_possible=False,
        )
    q_high = 2.0 * P_u_column_kN / a
    return NetPressureField(
        q_high_kN_m=q_high, slope_kN_m2=-q_high / a,
        contact_length_m=a, dim_m=dim, full_contact=False,
    )


def _campo_biaxial(
    P_u_column_kN: float, e_m: float, dim_along_e_m: float,
    e_transverse_m: float, dim_transverse_m: float | None,
):
    """El campo unilateral, SOLO si hace falta: `None` en los regímenes cerrados.

    Devolver `None` no es una optimización. En contacto total y en despegue uniaxial la
    marginal del campo unilateral ES `NetPressureField`, y la fórmula del trapecio es su
    integral exacta; usar ahí la ruta del polígono daría el mismo número con otra
    aritmética de punto flotante y movería resultados que no tienen por qué moverse."""
    if dim_transverse_m is None or abs(e_transverse_m) <= 1e-12:
        return None
    try:
        campo = solve_unilateral_contact(
            P_u_column_kN, dim_along_e_m, dim_transverse_m, e_m, e_transverse_m
        )
    except ContactFieldImpossible:
        # El llamador ya trata la imposibilidad por su cuenta (presión de contacto); aquí
        # se cae a la ruta 1-D, que declara lo suyo.
        return None
    if campo.full_contact or campo.uniaxial:
        return None
    return campo


def _rango_del_voladizo(
    dim_along_e_m: float, cantilever_m: float, e_m: float, near_high_edge: bool
) -> tuple[float, float, float]:
    """(x_lo, x_hi, x_cara) del voladizo, en la coordenada centrada del campo.

    `near_high_edge` se refiere al borde de MAYOR presión, que depende del signo de la
    excentricidad; `s` del campo 1-D se mide desde ese borde. Aquí se traduce a la
    coordenada con origen en el centroide, que es la del campo común."""
    semi = dim_along_e_m / 2.0
    en_coordenada_alta = (e_m >= 0.0) == near_high_edge
    if en_coordenada_alta:
        return semi - cantilever_m, semi, semi - cantilever_m
    return -semi, -semi + cantilever_m, -semi + cantilever_m


def _momento_biaxial(campo, e_m, dim_along_e_m, cantilever_m, near_high_edge) -> float:
    x_lo, x_hi, x_cara = _rango_del_voladizo(
        dim_along_e_m, cantilever_m, e_m, near_high_edge
    )
    semi_t = campo.L_m / 2.0
    return campo.moment_about_x_face(x_lo, x_hi, -semi_t, semi_t, x_cara)


def _cortante_biaxial(campo, e_m, dim_along_e_m, c_shear, near_high_edge) -> float:
    x_lo, x_hi, _ = _rango_del_voladizo(dim_along_e_m, c_shear, e_m, near_high_edge)
    semi_t = campo.L_m / 2.0
    return campo.force_over_rectangle(x_lo, x_hi, -semi_t, semi_t)


def moment_at_critical_section(
    P_u_column_kN: float, e_m: float, dim_along_e_m: float, cantilever_m: float,
    near_high_edge: bool,
    e_transverse_m: float = 0.0, dim_transverse_m: float | None = None,
) -> float:
    """Momento [kN*m] en la sección crítica (cara de columna) producido por la
    presión neta factorizada trapezoidal actuando sobre el voladizo de longitud
    `cantilever_m`. `near_high_edge=True` si el voladizo analizado está del lado
    del borde de mayor presión (x=dim), False si es del lado de menor presión (x=0).
    Por simetría de la columna centrada, ambos lados tienen el mismo `cantilever_m`;
    se evalúa el lado más desfavorable (mayor presión) para el diseño.

    Integración de la carga en voladizo (resistencia de materiales estándar, no una cita
    normativa numerada): `M_cara = ∫ q'(s)·|s − s_cara| ds` sobre el voladizo, con el
    campo `NetPressureField`, que resuelve los dos regímenes —contacto total y bloque
    triangular con despegue— y trunca donde acaba el contacto.

    Con contacto total se reduce a la fórmula de siempre, `M = (c²/6)·(2·q_borde +
    q_cara)`, y hay un test que lo comprueba término a término. Con despegue ya NO
    coincide, y esa es justamente la corrección: antes se recortaban a cero las presiones
    negativas del campo lineal, que no equilibra la carga y subestima Mu.

    EL CAMPO ES COMÚN (decisión del proyectista, 2026-09-20)
    ========================================================
    `engine/foundation/unilateral_contact.py` resuelve `q⁺ = max(a + b·u + c·v, 0)` por
    equilibrio, y es el MISMO campo que usan el punzonamiento y las otras direcciones. Con
    excentricidad transversal declarada:

      - si el campo está en un régimen CERRADO —contacto total, o despegue en una sola
        dirección— su marginal es exactamente `NetPressureField` y se integra con la
        fórmula del trapecio, que es la integral exacta de ese mismo campo. No es un
        segundo modelo: es evaluar analíticamente lo que si no habría que recortar;
      - si hay despegue BIAXIAL la marginal ya no es un campo 1-D, y se integra el campo
        real sobre la franja del voladizo, recortada contra la zona comprimida.

    Sin excentricidad transversal declarada los dos caminos coinciden, y se toma el
    cerrado.
    """
    biaxial = _campo_biaxial(
        P_u_column_kN, e_m, dim_along_e_m, e_transverse_m, dim_transverse_m
    )
    if biaxial is not None:
        return _momento_biaxial(biaxial, e_m, dim_along_e_m, cantilever_m, near_high_edge)
    campo = net_pressure_field(P_u_column_kN, e_m, dim_along_e_m)
    c = cantilever_m
    if near_high_edge:
        # El voladizo arranca en el borde de mayor presión: s de 0 a c, cara en s = c.
        _, momento = campo.force_and_moment(0.0, c, c)
    else:
        # El voladizo está en el otro extremo: s de dim−c a dim, cara en s = dim−c.
        _, momento = campo.force_and_moment(dim_along_e_m - c, dim_along_e_m, dim_along_e_m - c)
    return momento


def design_flexure(
    Mu_kNm: float,
    b_m: float,
    h_m: float,
    d_m: float,
    cantilever_m: float,
    fc_MPa: float,
    fy_MPa: float,
    bar_type: str,
    code: IConcreteCode,
) -> FlexureResult:
    """Diseño de sección simplemente reforzada (E.060 §10.2: bloque rectangular
    0.85f'c, phi=0.90 por E.060 §9.3.2). As_min por E.060 §9.7 (ver
    docs/normativa/as_min_zapatas.md), NO por Mcr (§10.5.1 excluye zapatas)."""
    phi = code.phi_factors().flexion
    rho_min, rho_ref = code.rho_min_temperature(fy_MPa, bar_type)
    As_min_m2 = rho_min * b_m * h_m

    if Mu_kNm <= 0:
        As_required_m2 = 0.0
    else:
        b_mm = m_to_mm(b_m)
        d_mm = m_to_mm(d_m)
        Mu_Nmm = kn_to_n(Mu_kNm) * 1000.0  # kN*m -> N*m -> N*mm
        Mn_req_Nmm = Mu_Nmm / phi
        # T^2 - 1.7*fc*b*d*T + 1.7*fc*b*Mn = 0  (T = As*fy, en N)
        a_coef = 1.0
        b_coef = -1.7 * fc_MPa * b_mm * d_mm
        c_coef = 1.7 * fc_MPa * b_mm * Mn_req_Nmm
        discriminant = b_coef**2 - 4 * a_coef * c_coef
        if discriminant < 0:
            return FlexureResult(
                Mu_kNm=Mu_kNm,
                cantilever_m=cantilever_m,
                As_required_m2=float("nan"),
                As_min_m2=As_min_m2,
                As_design_m2=float("nan"),
                rho_min=rho_min,
                rho_min_reference=rho_ref,
                status=CheckStatus.FAIL,
                note="Sección insuficiente: discriminante negativo, ni con As->infinito se alcanza Mn=Mu/phi. Aumentar h.",
            )
        T = (-b_coef - math.sqrt(discriminant)) / (2 * a_coef)  # raíz físicamente válida (menor)
        As_required_mm2 = T / fy_MPa
        As_required_m2 = As_required_mm2 / 1_000_000.0

    As_design_m2 = max(As_required_m2, As_min_m2)
    status = CheckStatus.PASS
    note = "As gobernado por flexión." if As_required_m2 >= As_min_m2 else "As gobernado por cuantía mínima (E.060 §9.7)."
    return FlexureResult(
        Mu_kNm=Mu_kNm,
        cantilever_m=cantilever_m,
        As_required_m2=As_required_m2,
        As_min_m2=As_min_m2,
        As_design_m2=As_design_m2,
        rho_min=rho_min,
        rho_min_reference=rho_ref,
        status=status,
        note=note,
    )
