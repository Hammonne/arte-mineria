"""
comun.py — carga de datos y cálculos compartidos (variables del modelo, contaminación río abajo).
"""
from functools import lru_cache
from pathlib import Path

import numpy as np
import rasterio
from scipy import ndimage

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "datos"
SALIDA = RAIZ / "salida"
KM_PIXEL = 0.12

MINERIA = 30
BOSQUE = {3, 6}                    # bosque, bosque inundable
ANTROPICO = {9, 15, 18, 21, 24}    # plantación, pasto, agricultura, mosaico, urbano
RIO_KM2 = 50                       # área de drenaje mínima para considerar "río"

NOMBRES_VARIABLES = ["dist_mineria_km", "densidad_mineria", "dist_rio_km", "dist_antropico_km",
                     "altura_sobre_rio_m", "elevacion_m", "protegida", "es_bosque", "area_drenaje_log"]


def leer(ruta, banda=1):
    with rasterio.open(ruta) as f:
        return f.read(banda)


def perfil():
    with rasterio.open(DATOS / "estaticos" / "region.tif") as f:
        return f.profile.copy()


@lru_cache
def estaticos():
    e = DATOS / "estaticos"
    upa = leer(e / "area_drenaje_km2.tif")
    rio = upa >= RIO_KM2
    return {
        "region": leer(e / "region.tif") == 1,
        "elev": leer(e / "elevacion.tif").astype(np.float32),
        "hnd": leer(e / "altura_sobre_rio.tif").astype(np.float32),
        "protegida": leer(e / "protegidas.tif").astype(np.float32),
        "upa_log": np.log1p(upa).astype(np.float32),
        "rio": rio,
        "dist_rio": (ndimage.distance_transform_edt(~rio) * KM_PIXEL).astype(np.float32),
        "dir": leer(e / "direccion_agua.tif"),
    }


def clases(anio):
    return leer(DATOS / "mapbiomas" / f"{anio}.tif")


def mineria_acumulada(anios):
    """Minería 'pegajosa': una vez minado, queda minado (la cicatriz no se borra).
    Devuelve dict anio -> máscara booleana."""
    acc = None
    out = {}
    for y in anios:
        m = clases(y) == MINERIA
        acc = m if acc is None else (acc | m)
        out[y] = acc.copy()
    return out


def variables(mineria, antropico, es_bosque, idx=None):
    """Matriz (n_pixeles, n_variables) para los píxeles `idx` (índices planos)."""
    s = estaticos()
    d_min = ndimage.distance_transform_edt(~mineria) * KM_PIXEL
    dens = ndimage.uniform_filter(mineria.astype(np.float32), size=11)
    d_antr = ndimage.distance_transform_edt(~(antropico | mineria)) * KM_PIXEL
    capas = [d_min, dens, s["dist_rio"], d_antr, s["hnd"], s["elev"], s["protegida"],
             es_bosque, s["upa_log"]]
    if idx is None:
        idx = np.arange(mineria.size)
    return np.column_stack([np.asarray(c, np.float32).ravel()[idx] for c in capas])


def probabilidades(modelo, mineria, antropico, es_bosque, region):
    """Probabilidad de volverse minería el próximo año para cada píxel libre."""
    cand = np.flatnonzero(region.ravel() & ~mineria.ravel())
    X = variables(mineria, antropico, es_bosque, cand)
    p = np.empty(len(cand), np.float64)
    for i in range(0, len(cand), 2_000_000):
        p[i:i + 2_000_000] = modelo.predict_proba(X[i:i + 2_000_000])[:, 1]
    return cand, p


def paso(modelo, mineria, antropico, es_bosque, region, n_nuevos, rng, exponente=1.4,
         radio_km=3.0):
    """Un año de simulación (BFS con probabilidades):
    - CUÁNTOS píxeles nuevos: `n_nuevos` (tendencia histórica).
    - DÓNDE: solo en el frente, a <= `radio_km` de minería existente (en 2016–2024
      ~99.8% de la minería nueva apareció a < 5 km), elegidos al azar pesados por la
      probabilidad del modelo (muestreo sin reemplazo de Efraimidis–Spirakis).
    `exponente` afila las probabilidades (p**1.4) para que el avance siga más
    los ríos y zonas bajas que el modelo marca como favorables."""
    frente = ndimage.binary_dilation(mineria, iterations=int(round(radio_km / KM_PIXEL)))
    cand, p = probabilidades(modelo, mineria, antropico, es_bosque, region & frente)
    n = int(min(n_nuevos, len(cand)))
    if n <= 0:
        return mineria.copy()
    clave = np.log(rng.random(len(cand))) / np.maximum(p ** exponente, 1e-300)
    elegidos = cand[np.argpartition(-clave, n - 1)[:n]]
    m = mineria.copy()
    m.ravel()[elegidos] = True
    return m


def idoneidad(modelo, antropico, es_bosque, region):
    """Qué tan favorable es cada píxel para minería SI tuviera minería al lado
    (se fijan las variables de cercanía y se dejan las del terreno: río, altura, etc.)."""
    s = estaticos()
    idx = np.flatnonzero(region.ravel())
    k = len(idx)
    fijo = lambda v: np.full(k, v, np.float32)
    X = np.column_stack([
        fijo(0.24),                         # dist_mineria_km: vecino
        fijo(0.10),                         # densidad_mineria
        s["dist_rio"].ravel()[idx],
        fijo(0.5),                          # dist_antropico_km
        s["hnd"].ravel()[idx], s["elev"].ravel()[idx], s["protegida"].ravel()[idx],
        np.asarray(es_bosque, np.float32).ravel()[idx], s["upa_log"].ravel()[idx],
    ])
    p = np.zeros(region.size, np.float64)
    for i in range(0, k, 2_000_000):
        p[idx[i:i + 2_000_000]] = modelo.predict_proba(X[i:i + 2_000_000])[:, 1]
    return p.reshape(region.shape)


def avance_dijkstra(modelo, mineria0, antropico, es_bosque, region, cuotas, anio0, rng,
                    fuerza=2.0, ruido=0.6):
    """BFS con pesos (Dijkstra): la minería avanza desde `mineria0` por los caminos
    de menor costo. Costo de cruzar un píxel = (idoneidad máxima / idoneidad)^fuerza,
    así los corredores favorables (orillas de río, zonas bajas) se recorren primero
    y forman 'dedos'. `ruido` agrega irregularidad orgánica (ruido suavizado).
    `cuotas[i]` = cuántos píxeles nuevos en el año anio0 + i.
    Devuelve raster con el año de llegada (0 = no llega)."""
    from skimage.graph import MCP_Geometric
    p = idoneidad(modelo, antropico, es_bosque, region)
    pmax = p[region].max()
    costo = (pmax / np.maximum(p, pmax * 1e-6)) ** fuerza
    if ruido > 0:
        r = ndimage.gaussian_filter(rng.normal(size=p.shape), 3)
        costo *= np.exp(ruido * r / r.std())
    costo[~region] = -1          # negativo = intransitable en skimage.graph
    mcp = MCP_Geometric(costo, fully_connected=True)
    dist, _ = mcp.find_costs(np.argwhere(mineria0 & region))
    dist = dist.ravel()
    libres = np.flatnonzero(region.ravel() & ~mineria0.ravel() & np.isfinite(dist))
    orden = libres[np.argsort(dist[libres], kind="stable")]
    anio = np.zeros(region.size, np.uint16)
    pos = 0
    for i, n in enumerate(cuotas):
        anio[orden[pos:pos + n]] = anio0 + i
        pos += n
    return anio.reshape(region.shape)


# ---------------- contaminación río abajo ----------------
D8 = {1: (0, 1), 2: (1, 1), 4: (1, 0), 8: (1, -1), 16: (0, -1), 32: (-1, -1), 64: (-1, 0), 128: (-1, 1)}


@lru_cache
def red_de_flujo():
    """Para cada píxel: a qué píxel le manda el agua (-1 = sale de la región).
    Devuelve (abajo, niveles) donde niveles es la lista de grupos de píxeles en
    orden topológico (todo lo de arriba se procesa antes que lo de abajo)."""
    # El agua va al vecino (de los 8) con MÁS área de drenaje que uno mismo.
    # Como el área siempre crece río abajo, no puede haber bucles.
    # (Las direcciones D8 de MERIT vienen a 90 m y al pasarlas a 120 m forman bucles.)
    s = estaticos()
    upa = leer(DATOS / "estaticos" / "area_drenaje_km2.tif").astype(np.float64)
    H, W = upa.shape
    # desempate (al remuestrear, vecinos pueden quedar con área idéntica):
    # ranking estricto por (área, -elevación, posición)
    orden = np.lexsort((np.arange(H * W), -s["elev"].ravel(), upa.ravel()))
    rango = np.empty(H * W, np.float64)
    rango[orden] = np.arange(H * W)
    upa = rango.reshape(H, W)
    pad = np.pad(upa, 1, constant_values=-np.inf)
    mejor = upa.copy()
    abajo = np.full(H * W, -1, dtype=np.int64)
    flat = np.arange(H * W).reshape(H, W)
    for dr, dc in D8.values():
        vec = pad[1 + dr:1 + dr + H, 1 + dc:1 + dc + W]
        gana = vec > mejor
        mejor[gana] = vec[gana]
        r2 = np.clip(np.arange(H)[:, None] + dr, 0, H - 1)
        c2 = np.clip(np.arange(W)[None, :] + dc, 0, W - 1)
        destino = flat[r2, c2]
        abajo[gana.ravel()] = destino[gana]
    reg = s["region"].ravel()
    abajo[~reg] = -1
    abajo[(abajo >= 0) & ~reg[np.maximum(abajo, 0)]] = -1

    # Kahn por niveles
    validos = abajo >= 0
    grado = np.bincount(abajo[validos], minlength=H * W)
    frente = np.flatnonzero(reg & (grado == 0))
    niveles = []
    while frente.size:
        niveles.append(frente)
        d = abajo[frente]
        d = d[d >= 0]
        np.subtract.at(grado, d, 1)
        d = np.unique(d)
        frente = d[grado[d] == 0]
    return abajo, niveles


def contaminacion(mineria, decaimiento=0.998):
    """Cuánta 'carga minera' pasa por cada píxel siguiendo el agua río abajo.
    Cada píxel minado aporta 1; la carga se atenúa un poco cada 120 m
    (0.998 por píxel ≈ queda ~20% a 100 km)."""
    abajo, niveles = red_de_flujo()
    c = mineria.ravel().astype(np.float32).copy()
    for nodos in niveles:
        d = abajo[nodos]
        ok = d >= 0
        np.add.at(c, d[ok], c[nodos[ok]] * decaimiento)
    return c.reshape(mineria.shape)
