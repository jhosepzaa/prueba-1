/**
 * Escena 3D del visor CIMA — port del prototipo «Cimentación 3D» y de su `three-d-stage.js`.
 *
 * Imperativa y sin React, como el prototipo: un bucle de animación que interpola la
 * geometría, proyecta las etiquetas HTML y dibuja el gizmo cada fotograma. El componente
 * `FoundationViewer` la monta y le pasa órdenes.
 *
 * NO CONOCE REGLAS ESTRUCTURALES. Recibe un `ModeloVisor` ya resuelto (ver `model.ts`) y
 * lo dibuja. Lo que en el prototipo era `buildRebar` —generar el armado desde un diámetro
 * y una separación— aquí no existe: las barras llegan con su posición desde el motor.
 *
 * Diferencias deliberadas con `three-d-stage.js`:
 *   - `preserveDrawingBuffer: true` se conserva: además de las capturas, permite
 *     comprobar la escena renderizada desde las herramientas de verificación.
 *   - No se envía telemetría de exportación al marco padre (`postMessage`): tenía sentido
 *     dentro de la herramienta de diseño, no en este programa.
 */

import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { OBJExporter } from "three/examples/jsm/exporters/OBJExporter.js";
import { GLTFExporter } from "three/examples/jsm/exporters/GLTFExporter.js";
import {
  easeInOutCubic,
  easeOutCubic,
  interpolar,
  nombreTipo,
  ruta,
  type Caja,
  type Clave,
  type ModeloVisor,
} from "./model";

export type Modo = "modelo" | "transparente" | "armadura" | "seccion";
export type EjeSeccion = "long" | "trans";
export type Vista = "iso" | "planta" | "frontal" | "lateral" | "reset";
export interface Banderas { dims: boolean; soil: boolean; axes: boolean; loads: boolean }

/** Estado de la barra de pasos, para que la dibuje React. */
export interface EstadoPasos {
  desde: string;
  hasta: string;
  etiquetas: string[];
  activo: number;
  progreso: number;
  terminado: boolean;
}

// --- Tokens del handoff ------------------------------------------------------
const COL = {
  foot: 0xd6d3cc, col: 0xc3bfb7, beam: 0xa9b5c1,
  steel: 0xc4683f, tie: 0x8f5a44, soil: 0xcdbd9f,
  edge: 0x353b43, acc: 0x2f6fae, ink: 0x22272e,
};
const OPACIDAD_CONCRETO: Record<Modo, number> = { modelo: 1, transparente: 0.2, armadura: 0, seccion: 1 };
const OPACIDAD_ARISTAS: Record<Modo, number> = { modelo: 0.38, transparente: 0.55, armadura: 0.28, seccion: 0.38 };
const DIRS: Record<Exclude<Vista, "reset">, THREE.Vector3> = {
  iso: new THREE.Vector3(1.05, 0.78, 1.4),
  planta: new THREE.Vector3(0, 1, 0.0008),
  frontal: new THREE.Vector3(0, 0.02, 1),
  lateral: new THREE.Vector3(1, 0.02, 0),
};
const SEGMENTO_S = 0.9;
const V = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);
const c01 = (v: number) => Math.min(1, Math.max(0, v));
const ahora = () => performance.now() / 1000;

type ClaseEtiqueta = "dim" | "tag" | "tag vc" | "ntn" | "ax" | "load" | "cut";
interface Etiqueta { p: THREE.Vector3; texto: string; cls: ClaseEtiqueta }

function rayado(bg: string, fg: string, paso = 16): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const x = c.getContext("2d")!;
  x.fillStyle = bg;
  x.fillRect(0, 0, 64, 64);
  x.strokeStyle = fg;
  x.lineWidth = 1.6;
  for (let i = -64; i <= 128; i += paso) {
    x.beginPath(); x.moveTo(i, 64); x.lineTo(i + 64, 0); x.stroke();
  }
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 4;
  return t;
}

export class EscenaCima {
  private renderer: THREE.WebGLRenderer;
  private scene = new THREE.Scene();
  private camera = new THREE.PerspectiveCamera(45, 1, 0.01, 500);
  private controls: OrbitControls;
  private ro: ResizeObserver;

  private modelo = new THREE.Group();
  private concreto = new THREE.Group();
  private armadura = new THREE.Group();
  private entorno = new THREE.Group();
  private anot = new THREE.Group();

  private U = new THREE.BoxGeometry(1, 1, 1);
  private EG = new THREE.EdgesGeometry(this.U);
  private PG = new THREE.PlaneGeometry(1, 1);
  private CY = new THREE.CylinderGeometry(1, 1, 1, 12, 1);

  private E: Record<keyof Clave, { mesh: THREE.Mesh; mat: THREE.MeshStandardMaterial; em: THREE.LineBasicMaterial; cap: THREE.Mesh }>;
  private suelo: THREE.Mesh;
  private sueloMat: THREE.MeshStandardMaterial;
  private sueloAristas: THREE.LineBasicMaterial;
  private sueloCap: THREE.Mesh;
  private acero = new THREE.MeshStandardMaterial({ name: "acero_principal", color: COL.steel, roughness: 0.42, metalness: 0.3 });
  private estribo = new THREE.MeshStandardMaterial({ name: "acero_estribos", color: COL.tie, roughness: 0.5, metalness: 0.25 });
  private plano = new THREE.Plane(V(0, 0, -1), 0);
  private matsCorte: THREE.Material[];

  private DL: { l: THREE.LineSegments; g: THREE.BufferGeometry; pos: Float32Array; n: number };
  private AL: { l: THREE.LineSegments; g: THREE.BufferGeometry; pos: Float32Array; n: number };
  private flechas: THREE.ArrowHelper[];
  private poolEtiquetas: HTMLDivElement[] = [];
  private tmp = new THREE.Vector3();

  // --- Estado ---
  private actual: ModeloVisor | null = null;
  private S: Clave | null = null;
  private tr: { claves: Clave[]; t0: number; hacia: ModeloVisor; etiquetas: string[]; desde: string } | null = null;
  private pendiente: ModeloVisor | null = null;
  private barras: THREE.Mesh[] = [];
  private revelar = { t0: -1e9, dur: 0 };
  private fundidoAcero = 1;
  private revelando = false;
  private pasos: EstadoPasos | null = null;
  private camTw: { t0: THREE.Vector3; t1: THREE.Vector3; u0: THREE.Vector3; l0: number; u1: THREE.Vector3; l1: number; s: number; dur: number } | null = null;
  private gHits: { x: number; y: number; d: THREE.Vector3 }[] = [];
  private dpr = Math.min(2, window.devicePixelRatio || 1);

  modo: Modo = "transparente";
  eje: EjeSeccion = "long";
  banderas: Banderas = { dims: true, soil: true, axes: true, loads: true };
  onPasos: ((p: EstadoPasos | null) => void) | null = null;

  constructor(
    host: HTMLElement,
    private capaEtiquetas: HTMLElement,
    private gizmo: HTMLCanvasElement,
  ) {
    const r = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
    r.setPixelRatio(this.dpr);
    r.shadowMap.enabled = true;
    r.shadowMap.type = THREE.PCFSoftShadowMap;
    r.localClippingEnabled = true;
    this.renderer = r;
    host.appendChild(r.domElement);
    r.domElement.style.display = "block";
    r.domElement.style.outline = "none";

    this.camera.position.set(3, 2.2, 4);
    this.controls = new OrbitControls(this.camera, r.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.addEventListener("start", () => { this.camTw = null; });

    // Estudio neutro del stage; la luz principal más intensa, como en el prototipo.
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0xd8d2c4, 1.0));
    const key = new THREE.DirectionalLight(0xffffff, 1.9);
    key.position.set(4, 7, 5);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    key.shadow.bias = -0.0002;
    key.shadow.camera.left = key.shadow.camera.bottom = -12;
    key.shadow.camera.right = key.shadow.camera.top = 12;
    this.scene.add(key);
    const fill = new THREE.DirectionalLight(0xfff4e6, 0.5);
    fill.position.set(-5, 3, -4);
    this.scene.add(fill);

    this.modelo.name = "cimentacion";
    this.concreto.name = "concreto";
    this.armadura.name = "armadura";
    this.modelo.add(this.concreto, this.armadura);
    this.scene.add(this.modelo, this.entorno, this.anot);

    const HT = {
      foot: rayado("#bdb9b1", "#8e8981"), col: rayado("#b3aea6", "#86817a"),
      beam: rayado("#9fabb7", "#77838f"), soil: rayado("#d6c8ac", "#b9a887", 10),
    };
    const tapa = (k: keyof typeof HT, opacidad = 1) => {
      const m = new THREE.MeshBasicMaterial({
        map: HT[k].clone(), transparent: opacidad < 1, opacity: opacidad,
        polygonOffset: true, polygonOffsetFactor: k === "soil" ? 0 : -2, polygonOffsetUnits: k === "soil" ? 0 : -2,
        side: THREE.DoubleSide, depthWrite: k !== "soil",
      });
      m.map!.needsUpdate = true;
      const c = new THREE.Mesh(this.PG, m);
      c.visible = false;
      this.anot.add(c);
      return c;
    };

    const DEF: Record<keyof Clave, [string, "foot" | "col" | "beam"]> = {
      foot1: ["zapata_Z1", "foot"], foot2: ["zapata_Z2", "foot"],
      col1: ["columna_C1", "col"], col2: ["columna_C2", "col"], beam: ["viga_conexion_VC1", "beam"],
    };
    this.E = {} as typeof this.E;
    for (const id of Object.keys(DEF) as (keyof Clave)[]) {
      const [nombre, k] = DEF[id];
      const mat = new THREE.MeshStandardMaterial({
        name: "concreto_" + nombre, color: COL[k], roughness: 0.92, metalness: 0,
        polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1,
      });
      const mesh = new THREE.Mesh(this.U, mat);
      mesh.name = nombre;
      mesh.castShadow = mesh.receiveShadow = true;
      const em = new THREE.LineBasicMaterial({ color: COL.edge, transparent: true, opacity: 0.4 });
      const ed = new THREE.LineSegments(this.EG, em);
      ed.userData.noExport = true;
      ed.name = nombre + "_aristas";
      mesh.add(ed);
      this.concreto.add(mesh);
      this.E[id] = { mesh, mat, em, cap: tapa(k) };
    }

    this.sueloMat = new THREE.MeshStandardMaterial({ color: COL.soil, roughness: 1, transparent: true, opacity: 0.16, depthWrite: false });
    this.suelo = new THREE.Mesh(this.U, this.sueloMat);
    this.suelo.renderOrder = 2;
    this.sueloAristas = new THREE.LineBasicMaterial({ color: 0xa8987a, transparent: true, opacity: 0.55 });
    this.suelo.add(new THREE.LineSegments(this.EG, this.sueloAristas));
    this.entorno.add(this.suelo);
    this.sueloCap = tapa("soil", 0.8);
    this.sueloCap.renderOrder = 3;

    const grid = new THREE.GridHelper(40, 80, 0xc3c8ce, 0xd7dbe0);
    grid.position.set(3, 0.004, 0);
    const gm = grid.material as THREE.Material;
    gm.transparent = true; gm.opacity = 0.75; gm.depthWrite = false;
    this.entorno.add(grid);

    this.matsCorte = [
      ...Object.values(this.E).flatMap((e) => [e.mat, e.em]),
      this.sueloMat, this.sueloAristas, this.acero, this.estribo,
    ];

    const lineas = (max: number, mat: THREE.LineBasicMaterial) => {
      const pos = new Float32Array(max * 6);
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
      const l = new THREE.LineSegments(g, mat);
      l.frustumCulled = false;
      this.anot.add(l);
      return { l, g, pos, n: 0 };
    };
    this.DL = lineas(200, new THREE.LineBasicMaterial({ color: COL.acc, transparent: true, opacity: 0.95, depthTest: false }));
    this.DL.l.renderOrder = 20;
    this.AL = lineas(40, new THREE.LineDashedMaterial({ color: COL.acc, dashSize: 0.14, gapSize: 0.08, transparent: true, opacity: 0.6 }));
    this.flechas = [0, 1].map(() => {
      const a = new THREE.ArrowHelper(V(0, -1, 0), V(0, 0, 0), 1, COL.ink, 0.14, 0.08);
      this.anot.add(a);
      return a;
    });

    this.gizmo.width = this.gizmo.height = 96 * this.dpr;
    this.gizmo.addEventListener("click", this.alClicGizmo);

    const ajustar = () => {
      const w = host.clientWidth || 1, h = host.clientHeight || 1;
      r.setSize(w, h);
      this.camera.aspect = w / h;
      this.camera.updateProjectionMatrix();
    };
    ajustar();
    this.ro = new ResizeObserver(ajustar);
    this.ro.observe(host);
    r.setAnimationLoop(this.bucle);
  }

  // ---------------------------------------------------------------------------
  // API
  // ---------------------------------------------------------------------------

  /** Muestra un modelo. Con uno anterior, recorre la ruta de transición del handoff. */
  setModelo(m: ModeloVisor) {
    if (!this.actual || !this.S) {
      this.actual = m;
      this.S = { ...m };
      this.construirArmadura(m, true);
      this.encuadrar(this.bbox(m), DIRS.iso, 0);
      return;
    }
    if (this.tr) { this.pendiente = m; return; }
    const r = ruta(this.actual, m);
    const desde = this.actual.tipo === m.tipo ? (this.actual.id ?? "Esquema") : nombreTipo(this.actual.tipo);
    const hasta = this.actual.tipo === m.tipo ? (m.id ?? "Esquema") : nombreTipo(m.tipo);
    this.tr = { claves: r.claves, t0: ahora(), hacia: m, etiquetas: r.etiquetas, desde };
    this.pasos = {
      desde, hasta,
      etiquetas: m.barras.length ? [...r.etiquetas, "Armadura"] : r.etiquetas,
      activo: 0, progreso: 0, terminado: false,
    };
    this.onPasos?.(this.pasos);
    this.encuadrar(this.bbox(m), null, 1.4);
  }

  setModo(m: Modo) {
    const eraSeccion = this.modo === "seccion";
    this.modo = m;
    if (eraSeccion !== (m === "seccion")) {
      const on = m === "seccion";
      this.matsCorte.forEach((mat) => { mat.clippingPlanes = on ? [this.plano] : []; mat.needsUpdate = true; });
      this.acero.side = this.estribo.side = on ? THREE.DoubleSide : THREE.FrontSide;
    }
  }

  setVista(v: Vista) {
    const m = this.tr ? this.tr.hacia : this.actual;
    if (!m) return;
    this.encuadrar(this.bbox(m), DIRS[v === "reset" ? "iso" : v], 0.9);
  }

  /** Grupo exportable, sin lo invisible ni lo marcado `noExport` (como el stage). */
  private podar(): () => void {
    const quitar: [THREE.Object3D, THREE.Object3D][] = [];
    this.modelo.traverse((o) => {
      if (o !== this.modelo && (o.visible === false || o.userData?.noExport)) quitar.push([o, o.parent!]);
    });
    quitar.forEach(([o, p]) => p.remove(o));
    return () => quitar.forEach(([o, p]) => p.add(o));
  }

  async exportarOBJ(base: string) {
    const restaurar = this.podar();
    try {
      const obj = "mtllib " + base + ".mtl\n" + new OBJExporter().parse(this.modelo);
      const mats = new Set<THREE.MeshStandardMaterial>();
      this.modelo.traverse((o) => {
        if ((o as THREE.Mesh).isMesh) mats.add((o as THREE.Mesh).material as THREE.MeshStandardMaterial);
      });
      let mtl = "# Exportado por CIMA\n";
      mats.forEach((m) => {
        const c = m.color;
        mtl += `newmtl ${m.name}\nKd ${c.r.toFixed(4)} ${c.g.toFixed(4)} ${c.b.toFixed(4)}\n`;
        mtl += `Ks 0.2000 0.2000 0.2000\nNs ${Math.round((1 - (m.roughness ?? 0.5)) * 200)}\nd ${(m.opacity ?? 1).toFixed(4)}\n\n`;
      });
      descargar(new Blob([obj], { type: "text/plain" }), base + ".obj");
      descargar(new Blob([mtl], { type: "text/plain" }), base + ".mtl");
    } finally {
      restaurar();
    }
  }

  async exportarGLB(base: string) {
    const restaurar = this.podar();
    try {
      const buf = (await new GLTFExporter().parseAsync(this.modelo, { binary: true })) as ArrayBuffer;
      descargar(new Blob([buf], { type: "model/gltf-binary" }), base + ".glb");
    } finally {
      restaurar();
    }
  }

  dispose() {
    this.renderer.setAnimationLoop(null);
    this.ro.disconnect();
    this.gizmo.removeEventListener("click", this.alClicGizmo);
    this.controls.dispose();
    this.renderer.dispose();
    this.renderer.domElement.remove();
    this.poolEtiquetas.forEach((e) => e.remove());
  }

  // ---------------------------------------------------------------------------
  // Armadura: las barras del motor, con la aparición animada del handoff
  // ---------------------------------------------------------------------------

  private construirArmadura(m: ModeloVisor, animar: boolean) {
    while (this.armadura.children.length) this.armadura.remove(this.armadura.children[0]);
    this.barras = [];
    const g = new THREE.Group();
    g.name = "armadura_Z1";
    this.armadura.add(g);
    const arriba = V(0, 1, 0);
    for (const b of m.barras) {
      const a = V(...b.a), c = V(...b.b);
      const dir = c.clone().sub(a);
      const largo = dir.length();
      if (largo <= 0.005) continue;
      const mesh = new THREE.Mesh(this.CY, b.estribo ? this.estribo : this.acero);
      mesh.name = b.nombre;
      mesh.position.copy(a).add(c).multiplyScalar(0.5);
      mesh.quaternion.setFromUnitVectors(arriba, dir.normalize());
      mesh.scale.set(b.diametro / 2, largo, b.diametro / 2);
      mesh.userData = { largo, retardo: b.retardo };
      mesh.castShadow = true;
      g.add(mesh);
      this.barras.push(mesh);
    }
    this.revelar.t0 = animar ? ahora() : -1e9;
    this.revelar.dur = this.barras.length
      ? Math.max(...this.barras.map((x) => x.userData.retardo as number)) + 0.35
      : 0;
    if (!animar) this.barras.forEach((x) => { x.visible = true; x.scale.y = x.userData.largo; });
  }

  // ---------------------------------------------------------------------------
  // Bucle
  // ---------------------------------------------------------------------------

  private bucle = () => {
    const t = ahora();
    if (!this.S || !this.actual) {
      this.renderer.render(this.scene, this.camera);
      return;
    }
    let S: Clave = this.S;
    if (this.tr) {
      const n = this.tr.claves.length - 1;
      const T = t - this.tr.t0;
      const i = Math.floor(T / SEGMENTO_S);
      this.fundidoAcero = Math.max(0, 1 - T / 0.3);
      if (i >= n) {
        S = { ...this.tr.hacia };
        this.actual = this.tr.hacia;
        this.tr = null;
        this.fundidoAcero = 1;
        this.construirArmadura(this.actual, true);
        this.revelando = true;
      } else {
        S = interpolar(this.tr.claves[i], this.tr.claves[i + 1], easeInOutCubic(c01((T - i * SEGMENTO_S) / SEGMENTO_S)));
        if (this.pasos) {
          this.pasos = { ...this.pasos, activo: i, progreso: (T - i * SEGMENTO_S) / SEGMENTO_S };
          this.onPasos?.(this.pasos);
        }
      }
      this.S = S;
    }
    if (this.revelando && this.pasos) {
      const p = this.revelar.dur ? (t - this.revelar.t0) / this.revelar.dur : 1;
      if (p >= 1) {
        this.revelando = false;
        this.pasos = { ...this.pasos, activo: this.pasos.etiquetas.length, progreso: 0, terminado: true };
        this.onPasos?.(this.pasos);
        if (this.pendiente) { const sig = this.pendiente; this.pendiente = null; this.setModelo(sig); }
      } else {
        this.pasos = { ...this.pasos, activo: this.pasos.etiquetas.length - 1, progreso: p };
        this.onPasos?.(this.pasos);
      }
    }

    this.aplicar(S, t);
    this.pasoCamara(t);
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
    this.anotar(S);
    this.dibujarGizmo();
  };

  private cajaSuelo(S: Clave): Caja {
    const fs = [S.foot1, S.foot2, S.beam].filter((f) => f.o > 0.5 && f.sx > 0.02);
    const base = fs.length ? fs : [S.col1];
    const x0 = Math.min(...base.map((f) => f.cx - f.sx / 2)) - 1.3;
    const x1 = Math.max(...base.map((f) => f.cx + f.sx / 2), S.col2.o > 0.5 ? S.col2.cx : -1e9) + 1.3;
    const zh = Math.max(...base.map((f) => f.sz / 2 + Math.abs(f.cz))) + 1.3;
    const fondo = Math.min(...base.map((f) => f.cy - f.sy / 2)) - 0.9;
    return { cx: (x0 + x1) / 2, cy: fondo / 2, cz: 0, sx: x1 - x0, sy: -fondo, sz: zh * 2, o: 1 };
  }

  private aplicar(S: Clave, t: number) {
    const sec = this.modo === "seccion";
    let corteX = 0;
    const zCorte = S.col1.cz;
    if (sec && this.eje === "trans") corteX = S.col2.o > 0.5 ? S.col2.cx : S.col1.cx;
    if (sec) {
      if (this.eje === "long") this.plano.set(V(0, 0, -1), zCorte);
      else this.plano.set(V(-1, 0, 0), corteX);
    }
    const colocar = (s: Caja, mesh: THREE.Mesh, cap: THREE.Mesh) => {
      const vis = s.o > 0.01 && s.sx > 0.005 && s.sy > 0.005 && s.sz > 0.005;
      mesh.visible = vis;
      mesh.position.set(s.cx, s.cy, s.cz);
      mesh.scale.set(Math.max(s.sx, 1e-3), Math.max(s.sy, 1e-3), Math.max(s.sz, 1e-3));
      let cv = false;
      if (sec && vis && s.o > 0.5) {
        if (this.eje === "long" && s.cz - s.sz / 2 < zCorte && s.cz + s.sz / 2 > zCorte) {
          cap.position.set(s.cx, s.cy, zCorte); cap.rotation.set(0, 0, 0); cap.scale.set(s.sx, s.sy, 1); cv = true;
        }
        if (this.eje === "trans" && s.cx - s.sx / 2 < corteX && s.cx + s.sx / 2 > corteX) {
          cap.position.set(corteX, s.cy, s.cz); cap.rotation.set(0, Math.PI / 2, 0); cap.scale.set(s.sz, s.sy, 1); cv = true;
        }
        if (cv) (cap.material as THREE.MeshBasicMaterial).map!.repeat.set(cap.scale.x / 0.16, cap.scale.y / 0.16);
      }
      cap.visible = cv;
    };
    for (const id of Object.keys(this.E) as (keyof Clave)[]) {
      const e = this.E[id], s = S[id];
      colocar(s, e.mesh, e.cap);
      const op = s.o * OPACIDAD_CONCRETO[this.modo];
      e.mat.visible = op > 0.002;
      e.mat.opacity = op;
      e.mat.transparent = op < 0.999;
      e.mat.depthWrite = op >= 0.999;
      e.em.opacity = s.o * OPACIDAD_ARISTAS[this.modo];
    }
    this.suelo.visible = this.banderas.soil;
    colocar(this.cajaSuelo(S), this.suelo, this.sueloCap);
    this.sueloCap.visible = this.sueloCap.visible && this.banderas.soil;
    this.sueloMat.opacity = sec ? 0.1 : this.modo === "armadura" ? 0.08 : 0.16;

    this.armadura.visible = this.modo !== "modelo";
    for (const m of [this.acero, this.estribo]) {
      m.opacity = this.fundidoAcero;
      m.transparent = this.fundidoAcero < 0.999;
      m.depthWrite = this.fundidoAcero > 0.5;
    }
    if (t < this.revelar.t0 + this.revelar.dur + 0.2) {
      const rt = t - this.revelar.t0;
      for (const m of this.barras) {
        const f = c01((rt - m.userData.retardo) / 0.3);
        m.visible = f > 0;
        m.scale.y = m.userData.largo * Math.max(easeOutCubic(f), 0.001);
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Anotaciones
  // ---------------------------------------------------------------------------

  private seg(B: { pos: Float32Array; n: number }, a: THREE.Vector3, b: THREE.Vector3) {
    if ((B.n + 1) * 6 > B.pos.length) return;
    B.pos.set([a.x, a.y, a.z, b.x, b.y, b.z], B.n * 6);
    B.n++;
  }

  /** Cota del handoff: línea, dos testigos y marcas oblicuas a 45°. */
  private cota(a: THREE.Vector3, b: THREE.Vector3, texto: string, etiquetas: Etiqueta[]) {
    const dir = b.clone().sub(a).normalize();
    const n = Math.abs(dir.y) > 0.9 ? V(1, 0, 0) : V(0, 1, 0);
    this.seg(this.DL, a, b);
    const tk = dir.clone().add(n).normalize().multiplyScalar(0.05);
    this.seg(this.DL, a.clone().sub(tk), a.clone().add(tk));
    this.seg(this.DL, b.clone().sub(tk), b.clone().add(tk));
    etiquetas.push({ p: a.clone().add(b).multiplyScalar(0.5), texto, cls: "dim" });
  }

  private anotar(S: Clave) {
    this.DL.n = 0;
    this.AL.n = 0;
    const et: Etiqueta[] = [];
    const m = this.tr ? this.tr.hacia : this.actual!;
    const enTransicion = !!this.tr;
    const f1 = S.foot1, c1 = S.col1, c2 = S.col2;
    const c2on = c2.o > 0.5 && c2.sx > 0.02;
    const cols = [c1].concat(c2on ? [c2] : []);
    const so = this.cajaSuelo(S);

    if (this.banderas.dims && !enTransicion) {
      for (const c of m.cotas) this.cota(V(...c.a), V(...c.b), c.texto, et);
      for (const e of m.etiquetas) et.push({ p: V(...e.p), texto: e.texto, cls: e.clase });
      if (this.banderas.soil) et.push({ p: V(so.cx - so.sx / 2 + 0.45, 0.02, so.cz + so.sz / 2), texto: "NTN ±0.00", cls: "ntn" });
      if (this.modo === "seccion" && m.recubrimiento != null) {
        const r = m.recubrimiento;
        et.push({
          p: this.eje === "long" ? V(f1.cx - f1.sx / 2 + 0.28, f1.cy - f1.sy / 2 + r / 2, c1.cz) : V(c1.cx, f1.cy - f1.sy / 2 + r / 2, f1.cz - f1.sz / 2 + 0.3),
          texto: `r = ${Math.round(r * 1000)} mm`, cls: "dim",
        });
      }
    }
    if (this.modo === "seccion") {
      const lx = this.eje === "long" ? so.cx + so.sx / 2 - 0.5 : (c2on ? c2.cx : c1.cx);
      et.push({
        p: V(lx, 0.25, this.eje === "long" ? c1.cz : so.cz + so.sz / 2 - 0.4),
        texto: this.eje === "long" ? "CORTE A–A" : (c2on ? "CORTE 2–2" : "CORTE 1–1"), cls: "cut",
      });
    }
    if (this.banderas.axes && m.tipo !== "viga") {
      const ext = f1.sz / 2 + Math.abs(f1.cz) + 0.95;
      cols.forEach((c, i) => {
        this.seg(this.AL, V(c.cx, 0.006, ext), V(c.cx, 0.006, -ext));
        this.seg(this.AL, V(c.cx, f1.cy - f1.sy / 2 - 0.2, c.cz), V(c.cx, c.cy + c.sy / 2 + 0.28, c.cz));
        et.push({ p: V(c.cx, 0.006, -ext - 0.26), texto: String(i + 1), cls: "ax" });
      });
      const f2on = S.foot2.o > 0.5 && S.foot2.sx > 0.02;
      const xa = f1.cx - f1.sx / 2 - 0.95;
      const xb = Math.max(f1.cx + f1.sx / 2, f2on ? S.foot2.cx + S.foot2.sx / 2 : -99) + 0.95;
      this.seg(this.AL, V(xa, 0.006, c1.cz), V(xb, 0.006, c1.cz));
      et.push({ p: V(xa - 0.26, 0.006, c1.cz), texto: "A", cls: "ax" });
    }
    this.flechas.forEach((a) => (a.visible = false));
    if (this.banderas.loads) {
      // Las flechas siguen a las columnas durante la transición; el valor es el del modelo.
      m.cargas.slice(0, 2).forEach((q, i) => {
        const c = i === 0 ? c1 : c2;
        if (i === 1 && !c2on) return;
        const a = this.flechas[i];
        const largo = 0.3 + Math.min(q.kN, 5000) / 1000 * 0.5;
        const yTip = c.cy + c.sy / 2 + 0.06;
        a.visible = true;
        a.position.set(c.cx, yTip + largo, c.cz);
        a.setLength(largo, 0.14, 0.08);
        et.push({ p: V(c.cx, yTip + largo + 0.13, c.cz), texto: q.texto, cls: "load" });
      });
    }
    this.DL.l.visible = this.DL.n > 0;
    this.DL.g.setDrawRange(0, this.DL.n * 2);
    (this.DL.g.attributes.position as THREE.BufferAttribute).needsUpdate = true;
    this.AL.l.visible = this.AL.n > 0;
    this.AL.g.setDrawRange(0, this.AL.n * 2);
    (this.AL.g.attributes.position as THREE.BufferAttribute).needsUpdate = true;
    if (this.AL.n) this.AL.l.computeLineDistances();
    this.pintarEtiquetas(et);
  }

  private pintarEtiquetas(lista: Etiqueta[]) {
    const w = this.capaEtiquetas.clientWidth, h = this.capaEtiquetas.clientHeight;
    lista.forEach((it, i) => {
      let el = this.poolEtiquetas[i] as HTMLDivElement & { _c?: string; _t?: string };
      if (!el) {
        el = document.createElement("div");
        this.capaEtiquetas.appendChild(el);
        this.poolEtiquetas.push(el);
      }
      if (el._c !== it.cls) { el.className = "lbl " + it.cls; el._c = it.cls; }
      if (el._t !== it.texto) { el.textContent = it.texto; el._t = it.texto; }
      this.tmp.copy(it.p).project(this.camera);
      const vis = this.tmp.z < 1 && this.tmp.z > -1;
      el.style.display = vis ? "" : "none";
      if (vis) {
        el.style.transform =
          `translate(${(((this.tmp.x + 1) / 2) * w).toFixed(1)}px,${(((1 - this.tmp.y) / 2) * h).toFixed(1)}px) translate(-50%,-50%)`;
      }
    });
    for (let i = lista.length; i < this.poolEtiquetas.length; i++) this.poolEtiquetas[i].style.display = "none";
  }

  // ---------------------------------------------------------------------------
  // Cámara
  // ---------------------------------------------------------------------------

  private bbox(m: ModeloVisor): THREE.Box3 {
    const b = new THREE.Box3();
    (["foot1", "foot2", "col1", "col2", "beam"] as const).forEach((k) => {
      const s = m[k];
      if (s.o > 0.5 && s.sx > 0.01) {
        b.expandByPoint(V(s.cx - s.sx / 2, s.cy - s.sy / 2, s.cz - s.sz / 2));
        b.expandByPoint(V(s.cx + s.sx / 2, s.cy + s.sy / 2, s.cz + s.sz / 2));
      }
    });
    if (b.isEmpty()) b.expandByPoint(V(0, 0, 0));
    b.max.y += 0.9; b.min.x -= 1.1; b.max.x += 0.6; b.max.z += 0.6;
    return b;
  }

  private encuadrar(box: THREE.Box3, dir: THREE.Vector3 | null, dur: number) {
    const centro = box.getCenter(V(0, 0, 0));
    const r = box.getBoundingSphere(new THREE.Sphere()).radius;
    const vf = (this.camera.fov * Math.PI) / 180;
    const hf = 2 * Math.atan(Math.tan(vf / 2) * this.camera.aspect);
    const dist = (r / Math.sin(Math.min(vf, hf) / 2)) * 1.12;
    const d = (dir ?? this.camera.position.clone().sub(this.controls.target)).clone().normalize();
    const p1 = centro.clone().addScaledVector(d, dist);
    this.camera.near = Math.max(dist / 100, 0.01);
    this.camera.far = dist * 100;
    this.camera.updateProjectionMatrix();
    if (!dur) {
      this.camera.position.copy(p1);
      this.controls.target.copy(centro);
      this.camTw = null;
      return;
    }
    const off0 = this.camera.position.clone().sub(this.controls.target);
    this.camTw = {
      t0: this.controls.target.clone(), t1: centro, u0: off0.clone().normalize(), l0: off0.length(),
      u1: d, l1: dist, s: ahora(), dur,
    };
  }

  private pasoCamara(t: number) {
    const tw = this.camTw;
    if (!tw) return;
    const e = easeInOutCubic(c01((t - tw.s) / tw.dur));
    const q = new THREE.Quaternion().setFromUnitVectors(tw.u0, tw.u1);
    const qe = new THREE.Quaternion().slerp(q, e);
    const u = tw.u0.clone().applyQuaternion(qe);
    this.controls.target.lerpVectors(tw.t0, tw.t1, e);
    this.camera.position.copy(this.controls.target).addScaledVector(u, tw.l0 + (tw.l1 - tw.l0) * e);
    if (e >= 1) this.camTw = null;
  }

  // ---------------------------------------------------------------------------
  // Gizmo de orientación (Z hacia arriba, convención de ingeniería)
  // ---------------------------------------------------------------------------

  private GAX = [
    { v: V(1, 0, 0), c: "#c4533f", l: "X" },
    { v: V(0, 0, -1), c: "#4f9a5b", l: "Y" },
    { v: V(0, 1, 0), c: "#3a74b3", l: "Z" },
  ];

  private dibujarGizmo() {
    const gx = this.gizmo.getContext("2d");
    if (!gx) return;
    const q = this.camera.quaternion.clone().invert(), c = 48, R = 30;
    gx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    gx.clearRect(0, 0, 96, 96);
    const items = this.GAX.flatMap((a) => {
      const p = a.v.clone().applyQuaternion(q);
      return [{ ...a, p, pos: true }, { ...a, p: p.clone().negate(), pos: false }];
    }).sort((a, b) => a.p.z - b.p.z);
    this.gHits = [];
    gx.font = '600 10px "IBM Plex Mono", monospace';
    gx.textAlign = "center";
    gx.textBaseline = "middle";
    for (const it of items) {
      const x = c + it.p.x * R, y = c - it.p.y * R;
      if (it.pos) {
        gx.strokeStyle = it.c; gx.lineWidth = 2;
        gx.beginPath(); gx.moveTo(c, c); gx.lineTo(x, y); gx.stroke();
        gx.fillStyle = it.c; gx.beginPath(); gx.arc(x, y, 8.5, 0, 7); gx.fill();
        gx.fillStyle = "#fff"; gx.fillText(it.l, x, y + 0.5);
      } else {
        gx.strokeStyle = it.c; gx.globalAlpha = 0.45; gx.lineWidth = 1.5;
        gx.beginPath(); gx.arc(x, y, 5, 0, 7); gx.stroke(); gx.globalAlpha = 1;
      }
      this.gHits.push({ x, y, d: it.v.clone().multiplyScalar(it.pos ? 1 : -1) });
    }
  }

  private alClicGizmo = (e: MouseEvent) => {
    const r = this.gizmo.getBoundingClientRect();
    const mx = e.clientX - r.left, my = e.clientY - r.top;
    let mejor: { d: THREE.Vector3 } | null = null, bd = 14;
    this.gHits.forEach((h) => { const d = Math.hypot(h.x - mx, h.y - my); if (d < bd) { bd = d; mejor = h; } });
    const m = this.tr ? this.tr.hacia : this.actual;
    if (!m) return;
    if (mejor) {
      const d = (mejor as { d: THREE.Vector3 }).d.clone();
      if (Math.abs(d.y) > 0.9) d.z = 0.0008;
      this.encuadrar(this.bbox(m), d, 0.8);
    } else {
      this.setVista("iso");
    }
  };
}

function descargar(blob: Blob, nombre: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nombre;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}
