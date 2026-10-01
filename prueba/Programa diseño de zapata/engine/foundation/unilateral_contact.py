"""Contacto unilateral de la zapata rectangular: el campo de presión de DISEÑO.

QUÉ RESUELVE
============
El suelo no tracciona. La distribución de presiones bajo una zapata rígida es un plano
**truncado en cero**:

    q⁺(x, y) = max(a + b·u + c·v, 0)        u = x/(B/2),  v = y/(L/2)

y los tres coeficientes se determinan por EQUILIBRIO con la resultante de diseño:

    ∫∫ q⁺ dA = Pu          ∫∫ x·q⁺ dA = Pu·ex          ∫∫ y·q⁺ dA = Pu·ey

Tres ecuaciones, tres incógnitas. `x` e `y` se miden desde el CENTROIDE de la zapata, que
es el origen de `engine/soil/eccentricity.py` y de la sección crítica de punzonamiento.

POR QUÉ ESTO Y NO UNA SUPERPOSICIÓN (decisión del proyectista, 2026-09-20)
==========================================================================
Hasta aquí el campo 2-D se construía superponiendo los dos campos unidireccionales. Esa
superposición es EXACTA con contacto total y con despegue en una sola dirección, pero con
excentricidad biaxial **no resuelve el contacto, solo lo describe**: su parte positiva
entregaba 1,61·Pu en el régimen de `17_columna_de_esquina`, y el alivio del punzonamiento
salía 397,5 kN donde el valor exacto es 836,5 kN. Medido en
`docs/freeze_zona_contacto_y_proporcion.md` §2.1.

Este módulo es el **campo común** de punzonamiento, flexión y cortante unidireccional. No
hay una segunda representación del contacto de diseño.

LOS TRES REGÍMENES, Y POR QUÉ DOS SON CERRADOS
==============================================
La solución del sistema es única, y en dos regímenes se escribe sola:

1. **Contacto total** —la resultante dentro del núcleo, que en un rectángulo es el ROMBO
   `|6·ex/B| + |6·ey/L| ≤ 1`—: el truncamiento no actúa y el plano es el lineal clásico
   `q = q_avg·(1 + 12·ex·x/B² + 12·ey·y/L²)`.
2. **Despegue en una sola dirección** —`ey = 0` y `|ex| > B/6`, o al revés—: el bloque
   triangular de `NetPressureField`, repartido uniformemente en la dirección perpendicular.
3. **Excentricidad biaxial con despegue**: sin forma cerrada. Se resuelve por Newton.

En 1 y 2 **no se itera**: se escribe la solución. No es un atajo ni un segundo modelo —es
la misma solución, evaluada en forma cerrada en vez de numéricamente—, y así las
geometrías que no están en el régimen 3 no se mueven ni un bit por el cambio de método.

EL JACOBIANO ES EXACTO, Y ESO ES LO QUE HACE DÓCIL A NEWTON
===========================================================
Al derivar `F(a,b,c) = ∫_{P} (a + b·u + c·v) dA` respecto de cada coeficiente, el término
de frontera de Leibniz **se anula**: la frontera libre se mueve, pero el integrando vale
cero justo sobre ella. Queda

    J = [[ A,   Su,   Sv  ],
         [ Su,  Iuu,  Iuv ],
         [ Sv,  Iuv,  Ivv ]]

es decir la matriz de Gram de `{1, u, v}` sobre el polígono comprimido: **simétrica y
definida positiva** mientras el polígono tenga área. No es una aproximación del jacobiano:
es el jacobiano.

Los momentos del polígono se calculan en forma cerrada (fórmulas del cordón), de modo que
tanto el residuo como el jacobiano son exactos y Newton converge cuadráticamente.

EXISTENCIA
==========
Una distribución no negativa sobre el rectángulo tiene su resultante dentro del propio
rectángulo. Si `|ex| ≥ B/2` o `|ey| ≥ L/2` **no existe campo posible** y se declara
imposible, igual que hacía el bloque triangular con `e ≥ dim/2`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# Tolerancias. `RESIDUO_REL` se mide contra Pu y contra Pu·(semilado), que son las
# escalas naturales de las tres ecuaciones.
RESIDUO_REL = 1e-13
MAX_ITERACIONES = 60

Punto = tuple[float, float]
Poligono = list[Punto]


# =========================================================================
# Geometría: recorte y momentos del polígono
# =========================================================================


def clip_half_plane(poligono: Poligono, a: float, b: float, c: float) -> Poligono:
    """Recorta un polígono CONVEXO contra el semiplano `a + b·u + c·v >= 0`.

    Sutherland-Hodgman. El valor es afín, de modo que la interpolación lineal sobre cada
    arista da el punto de corte exacto. Un convexo recortado por un semiplano sigue siendo
    convexo, y por eso basta una pasada."""
    salida: Poligono = []
    n = len(poligono)
    for i in range(n):
        u1, v1 = poligono[i]
        u2, v2 = poligono[(i + 1) % n]
        f1 = a + b * u1 + c * v1
        f2 = a + b * u2 + c * v2
        if f1 >= 0.0:
            salida.append((u1, v1))
        if (f1 > 0.0 and f2 < 0.0) or (f1 < 0.0 and f2 > 0.0):
            t = f1 / (f1 - f2)
            salida.append((u1 + t * (u2 - u1), v1 + t * (v2 - v1)))
    return salida


class MomentosPoligono(BaseModel):
    """Momentos de área de orden 0, 1 y 2 de un polígono, en sus propias coordenadas.

    `A = ∫dA`, `Su = ∫u dA`, `Sv = ∫v dA`, `Iuu = ∫u² dA`, `Iuv = ∫uv dA`,
    `Ivv = ∫v² dA`. Son lo único que hace falta: la integral de cualquier función AFÍN
    sobre el polígono, y la de esa función por `u` o por `v`, se escriben con ellos."""

    A: float = 0.0
    Su: float = 0.0
    Sv: float = 0.0
    Iuu: float = 0.0
    Iuv: float = 0.0
    Ivv: float = 0.0

    @property
    def degenerado(self) -> bool:
        return self.A <= 0.0


def momentos_poligono(poligono: Poligono) -> MomentosPoligono:
    """Fórmulas del cordón (shoelace) extendidas a los momentos de segundo orden.

    Se toman valores absolutos del área para no depender de la orientación del contorno;
    los momentos se dividen por el doble del área CON signo, de modo que el signo se
    cancela solo. Con menos de tres vértices el recorte dejó fuera todo: se devuelven
    ceros, que es lo que corresponde donde el suelo no toca."""
    n = len(poligono)
    if n < 3:
        return MomentosPoligono()
    a2 = su = sv = iuu = iuv = ivv = 0.0
    for i in range(n):
        u1, v1 = poligono[i]
        u2, v2 = poligono[(i + 1) % n]
        cruz = u1 * v2 - u2 * v1
        a2 += cruz
        su += (u1 + u2) * cruz
        sv += (v1 + v2) * cruz
        iuu += (u1 * u1 + u1 * u2 + u2 * u2) * cruz
        ivv += (v1 * v1 + v1 * v2 + v2 * v2) * cruz
        iuv += (u1 * v2 + 2.0 * u1 * v1 + 2.0 * u2 * v2 + u2 * v1) * cruz
    if abs(a2) < 1e-300:
        return MomentosPoligono()
    signo = 1.0 if a2 > 0.0 else -1.0
    return MomentosPoligono(
        A=abs(a2) / 2.0,
        Su=signo * su / 6.0,
        Sv=signo * sv / 6.0,
        Iuu=signo * iuu / 12.0,
        Ivv=signo * ivv / 12.0,
        Iuv=signo * iuv / 24.0,
    )


def _resolver_3x3(M: list[list[float]], r: list[float]) -> list[float]:
    """Gauss con pivoteo parcial. Tres incógnitas: no hace falta nada más."""
    A = [fila[:] + [r[i]] for i, fila in enumerate(M)]
    for i in range(3):
        p = max(range(i, 3), key=lambda k: abs(A[k][i]))
        if abs(A[p][i]) < 1e-300:
            raise ZeroDivisionError("sistema singular")
        A[i], A[p] = A[p], A[i]
        for k in range(i + 1, 3):
            f = A[k][i] / A[i][i]
            for m in range(i, 4):
                A[k][m] -= f * A[i][m]
    x = [0.0, 0.0, 0.0]
    for i in (2, 1, 0):
        x[i] = (A[i][3] - sum(A[i][m] * x[m] for m in range(i + 1, 3))) / A[i][i]
    return x


# =========================================================================
# El campo
# =========================================================================


class ContactFieldImpossible(ValueError):
    """La resultante cae fuera de la huella: ninguna distribución no negativa la produce."""


class UnilateralContactField(BaseModel):
    """`q⁺(x,y) = max(a + b·u + c·v, 0)` en equilibrio con (Pu, ex, ey).

    Las coordenadas NORMALIZADAS `u = x/(B/2)`, `v = y/(L/2)` no son cosmética: con ellas
    la matriz de Gram tiene todas sus entradas del mismo orden y el sistema de Newton está
    bien condicionado sea cual sea el tamaño de la zapata."""

    a_kPa: float = Field(..., description="Término independiente del plano, en kPa")
    b_kPa: float = Field(..., description="Pendiente respecto de u = x/(B/2), en kPa")
    c_kPa: float = Field(..., description="Pendiente respecto de v = y/(L/2), en kPa")
    B_m: float
    L_m: float
    P_u_kN: float
    ex_m: float
    ey_m: float
    full_contact: bool = Field(
        ..., description="La huella entera comprime: el truncamiento no actúa"
    )
    uniaxial: bool = Field(
        ..., description="El despegue, si lo hay, afecta a una sola dirección"
    )
    iterations: int = Field(0, description="Iteraciones de Newton; 0 en los regímenes cerrados")

    # ---------------------------------------------------------------- lectura

    def _u(self, x_m: float) -> float:
        return x_m / (self.B_m / 2.0)

    def _v(self, y_m: float) -> float:
        return y_m / (self.L_m / 2.0)

    def plane_at(self, x_m: float, y_m: float) -> float:
        """El plano SIN truncar. Puede ser negativo: es donde el suelo no toca."""
        return self.a_kPa + self.b_kPa * self._u(x_m) + self.c_kPa * self._v(y_m)

    def q_at(self, x_m: float, y_m: float) -> float:
        """La presión [kPa]. Nunca negativa, por definición del contacto unilateral."""
        return max(self.plane_at(x_m, y_m), 0.0)

    def in_contact(self, x_m: float, y_m: float) -> bool:
        return self.plane_at(x_m, y_m) > 0.0

    @property
    def partial_contact(self) -> bool:
        return not self.full_contact

    # ------------------------------------------------------------- integrales

    def _poligono_normalizado(
        self, x_lo_m: float, x_hi_m: float, y_lo_m: float, y_hi_m: float
    ) -> Poligono:
        """El rectángulo pedido, recortado a la zona comprimida, en coordenadas (u, v)."""
        rect: Poligono = [
            (self._u(x_lo_m), self._v(y_lo_m)),
            (self._u(x_hi_m), self._v(y_lo_m)),
            (self._u(x_hi_m), self._v(y_hi_m)),
            (self._u(x_lo_m), self._v(y_hi_m)),
        ]
        if self.full_contact:
            return rect
        return clip_half_plane(rect, self.a_kPa, self.b_kPa, self.c_kPa)

    def resultants_over_rectangle(
        self, x_lo_m: float, x_hi_m: float, y_lo_m: float, y_hi_m: float
    ) -> tuple[float, float, float]:
        """`(F, Mx, My)` de la presión sobre un rectángulo: fuerza [kN] y momentos [kN·m]
        respecto del CENTROIDE de la zapata, `Mx = ∫x·q dA`, `My = ∫y·q dA`.

        Exacta, no una cuadratura: se recorta el rectángulo contra la zona comprimida y se
        evalúan los momentos del polígono en forma cerrada. `q` es afín donde vale, de modo
        que `∫q dA`, `∫u·q dA` y `∫v·q dA` se escriben con `A`, `Su`, `Sv`, `Iuu`, `Iuv` y
        `Ivv` y nada más."""
        if x_hi_m <= x_lo_m or y_hi_m <= y_lo_m:
            return 0.0, 0.0, 0.0
        m = momentos_poligono(self._poligono_normalizado(x_lo_m, x_hi_m, y_lo_m, y_hi_m))
        if m.degenerado:
            return 0.0, 0.0, 0.0
        a, b, c = self.a_kPa, self.b_kPa, self.c_kPa
        # Jacobiano del cambio de variable: dA = (B/2)·(L/2)·du·dv.
        jac = (self.B_m / 2.0) * (self.L_m / 2.0)
        F = (a * m.A + b * m.Su + c * m.Sv) * jac
        Mu = (a * m.Su + b * m.Iuu + c * m.Iuv) * jac
        Mv = (a * m.Sv + b * m.Iuv + c * m.Ivv) * jac
        return F, Mu * (self.B_m / 2.0), Mv * (self.L_m / 2.0)

    def force_over_rectangle(
        self, x_lo_m: float, x_hi_m: float, y_lo_m: float, y_hi_m: float
    ) -> float:
        return self.resultants_over_rectangle(x_lo_m, x_hi_m, y_lo_m, y_hi_m)[0]

    def moment_about_x_face(
        self, x_lo_m: float, x_hi_m: float, y_lo_m: float, y_hi_m: float, x_face_m: float
    ) -> float:
        """`∫∫ q·|x_cara − x| dA` [kN·m] sobre un rectángulo situado A UN SOLO LADO de la
        cara, que es el caso del voladizo de una zapata. Fuera de esa hipótesis el valor
        absoluto no sale de la integral y el resultado no significaría nada."""
        F, Mx, _ = self.resultants_over_rectangle(x_lo_m, x_hi_m, y_lo_m, y_hi_m)
        return abs(x_face_m * F - Mx)

    def moment_about_y_face(
        self, x_lo_m: float, x_hi_m: float, y_lo_m: float, y_hi_m: float, y_face_m: float
    ) -> float:
        F, _, My = self.resultants_over_rectangle(x_lo_m, x_hi_m, y_lo_m, y_hi_m)
        return abs(y_face_m * F - My)

    @property
    def contact_area_m2(self) -> float:
        m = momentos_poligono(
            self._poligono_normalizado(-self.B_m / 2, self.B_m / 2, -self.L_m / 2, self.L_m / 2)
        )
        return m.A * (self.B_m / 2.0) * (self.L_m / 2.0)

    def equilibrium_residual(self) -> tuple[float, float, float]:
        """`(ΣF − Pu, ΣMx − Pu·ex, ΣMy − Pu·ey)`. Debe ser cero por construcción; se
        expone para poder comprobarlo desde fuera en vez de confiar en que lo sea."""
        F, Mx, My = self.resultants_over_rectangle(
            -self.B_m / 2, self.B_m / 2, -self.L_m / 2, self.L_m / 2
        )
        return (
            F - self.P_u_kN,
            Mx - self.P_u_kN * self.ex_m,
            My - self.P_u_kN * self.ey_m,
        )


# =========================================================================
# La solución
# =========================================================================


def _dentro_del_rombo(B_m: float, L_m: float, ex_m: float, ey_m: float) -> bool:
    """Núcleo central de un RECTÁNGULO: `|6·ex/B| + |6·ey/L| <= 1`, que es un rombo.

    No es el producto de los dos núcleos unidireccionales. Confundirlos fue un defecto
    real: con cada excentricidad dentro de su sexto pero sumando más de uno, la esquina
    está traccionada."""
    return abs(6.0 * ex_m / B_m) + abs(6.0 * ey_m / L_m) <= 1.0 + 1e-12


def _plano_lineal(B_m: float, L_m: float, P_u_kN: float, ex_m: float, ey_m: float):
    """Régimen 1: el plano lineal clásico, en coordenadas normalizadas."""
    q_avg = P_u_kN / (B_m * L_m)
    return q_avg, q_avg * 6.0 * ex_m / B_m, q_avg * 6.0 * ey_m / L_m


def _plano_triangular(dim_m: float, otra_dim_m: float, P_u_kN: float, e_m: float):
    """Régimen 2: el bloque triangular, escrito como plano truncado.

    `a = 3·(dim/2 − |e|)` es la longitud comprimida y `q(0) = 2·Pu/a` la presión en el
    borde cargado, que es exactamente `NetPressureField`. Aquí se expresa como la recta
    que vale `q(0)` en ese borde y cero a la distancia `a`: truncada en cero, es el mismo
    campo. Devuelve (termino_independiente, pendiente) en coordenada normalizada, con el
    signo ya puesto según hacia dónde se desplaza la resultante."""
    largo = 3.0 * (dim_m / 2.0 - abs(e_m))
    q_borde = 2.0 * P_u_kN / (largo * otra_dim_m)
    # Recta en la coordenada normalizada w del eje: vale q_borde en w = signo y cero en
    # w = signo·(1 − 2·largo/dim).
    signo = 1.0 if e_m >= 0.0 else -1.0
    w_cero = signo * (1.0 - 2.0 * largo / dim_m)
    pendiente = q_borde / (signo - w_cero)
    return -pendiente * w_cero, pendiente


def solve_unilateral_contact(
    P_u_kN: float, B_m: float, L_m: float, ex_m: float, ey_m: float
) -> UnilateralContactField:
    """El campo de presión de diseño. **Única forma de construirlo.**

    Lanza `ContactFieldImpossible` si la resultante cae fuera de la huella, porque entonces
    ninguna distribución no negativa puede equilibrarla."""
    if P_u_kN <= 0.0:
        raise ContactFieldImpossible(
            f"Pu = {P_u_kN:.4f} kN: sin carga de compresión no hay campo de contacto."
        )
    if abs(ex_m) >= B_m / 2.0 - 1e-12 or abs(ey_m) >= L_m / 2.0 - 1e-12:
        raise ContactFieldImpossible(
            f"La resultante de diseño cae fuera de la huella: ex = {ex_m:+.4f} m sobre "
            f"B/2 = {B_m / 2.0:.4f} m, ey = {ey_m:+.4f} m sobre L/2 = {L_m / 2.0:.4f} m. "
            f"Ninguna distribución de presiones no negativa puede equilibrarla."
        )

    comun = dict(B_m=B_m, L_m=L_m, P_u_kN=P_u_kN, ex_m=ex_m, ey_m=ey_m)

    # --- Régimen 1: contacto total -------------------------------------
    if _dentro_del_rombo(B_m, L_m, ex_m, ey_m):
        a, b, c = _plano_lineal(B_m, L_m, P_u_kN, ex_m, ey_m)
        return UnilateralContactField(
            a_kPa=a, b_kPa=b, c_kPa=c, full_contact=True, uniaxial=True, **comun
        )

    # --- Régimen 2: despegue en una sola dirección ---------------------
    if abs(ey_m) <= 1e-12:
        a, b = _plano_triangular(B_m, L_m, P_u_kN, ex_m)
        return UnilateralContactField(
            a_kPa=a, b_kPa=b, c_kPa=0.0, full_contact=False, uniaxial=True, **comun
        )
    if abs(ex_m) <= 1e-12:
        a, c = _plano_triangular(L_m, B_m, P_u_kN, ey_m)
        return UnilateralContactField(
            a_kPa=a, b_kPa=0.0, c_kPa=c, full_contact=False, uniaxial=True, **comun
        )

    # --- Régimen 3: biaxial con despegue. Newton -----------------------
    return _resolver_newton(P_u_kN, B_m, L_m, ex_m, ey_m, comun)


def _resolver_newton(
    P_u_kN: float, B_m: float, L_m: float, ex_m: float, ey_m: float, comun: dict
) -> UnilateralContactField:
    """Newton con jacobiano exacto (la matriz de Gram) y búsqueda de línea.

    ARRANQUE. El plano lineal, que es la solución exacta del problema SIN truncar. Está
    siempre del lado de dar una zona comprimida demasiado grande, que es el lado bueno:
    el jacobiano no degenera en el primer paso.

    BÚSQUEDA DE LÍNEA. El paso de Newton puede sobrepasar y dejar el polígono vacío, donde
    el sistema es singular y el residuo deja de estar definido. Se reduce el paso a la
    mitad hasta que el polígono tenga área y el residuo no empeore. Es lo que hace que el
    método no dependa de lo cerca que esté la resultante de la esquina."""
    semi_b, semi_l = B_m / 2.0, L_m / 2.0
    objetivo = (P_u_kN, P_u_kN * ex_m / semi_b, P_u_kN * ey_m / semi_l)
    # Escalas de cada ecuación, para medir el residuo sin mezclar unidades.
    escala = (P_u_kN, P_u_kN, P_u_kN)
    rect: Poligono = [(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)]
    jac = semi_b * semi_l

    def momentos(v: list[float]) -> MomentosPoligono:
        return momentos_poligono(clip_half_plane(rect, v[0], v[1], v[2]))

    def residuo(v: list[float], m: MomentosPoligono) -> list[float]:
        a, b, c = v
        F = (a * m.A + b * m.Su + c * m.Sv) * jac
        Mu = (a * m.Su + b * m.Iuu + c * m.Iuv) * jac
        Mv = (a * m.Sv + b * m.Iuv + c * m.Ivv) * jac
        return [F - objetivo[0], Mu - objetivo[1], Mv - objetivo[2]]

    def norma(r: list[float]) -> float:
        return max(abs(r[i]) / escala[i] for i in range(3))

    v = list(_plano_lineal(B_m, L_m, P_u_kN, ex_m, ey_m))
    m = momentos(v)
    r = residuo(v, m)
    iteraciones = 0
    for _ in range(MAX_ITERACIONES):
        if norma(r) <= RESIDUO_REL:
            break
        iteraciones += 1
        J = [
            [m.A * jac, m.Su * jac, m.Sv * jac],
            [m.Su * jac, m.Iuu * jac, m.Iuv * jac],
            [m.Sv * jac, m.Iuv * jac, m.Ivv * jac],
        ]
        try:
            paso = _resolver_3x3(J, [-x for x in r])
        except ZeroDivisionError as exc:  # pragma: no cover - defensivo
            raise ContactFieldImpossible(
                f"El contacto unilateral degeneró para ex = {ex_m:+.4f}, ey = {ey_m:+.4f}."
            ) from exc
        alfa = 1.0
        for _ in range(60):
            cand = [v[i] + alfa * paso[i] for i in range(3)]
            m_cand = momentos(cand)
            if not m_cand.degenerado:
                r_cand = residuo(cand, m_cand)
                if norma(r_cand) < norma(r) or norma(r_cand) <= RESIDUO_REL:
                    v, m, r = cand, m_cand, r_cand
                    break
            alfa /= 2.0
        else:  # pragma: no cover - defensivo
            break
    else:  # pragma: no cover - defensivo
        pass

    if norma(r) > 1e-8:  # pragma: no cover - defensivo
        raise ContactFieldImpossible(
            f"El contacto unilateral no convergió para ex = {ex_m:+.4f} m, "
            f"ey = {ey_m:+.4f} m sobre {B_m:.3f} x {L_m:.3f} m (residuo {norma(r):.3e})."
        )
    return UnilateralContactField(
        a_kPa=v[0], b_kPa=v[1], c_kPa=v[2],
        full_contact=False, uniaxial=False, iterations=iteraciones, **comun
    )
