"""
06_web.py — genera las imágenes del visor web (web/index.html), tipo Google Earth:
  web/frames/region/AAAA.webp        toda Madre de Dios (120 m), un cuadro por año
  web/frames/<zona>/AAAA.webp        cada zona minera en alta resolución (30 m)
  web/frames/*/sangre_K.webp         etapas del final en sangre
  web/datos.js                       años, límites geográficos, cifras por año

Todo se reproyecta a Web Mercator (EPSG:3857) para calzar con el mapa base.

Uso:  python 06_web.py          (requiere 03_simular.py y 05_descargar_zonas.py)
"""
import csv
import json
import shutil
import time

import numpy as np
import rasterio
from PIL import Image
from rasterio.transform import Affine
from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_bounds
from scipy import ndimage

from comun import DATOS, RAIZ, SALIDA, contaminacion, estaticos, leer, perfil
from final_sangre import FinalSangre

WEB = RAIZ / "web"
FR = WEB / "frames"
MAX_LADO_REGION = 2400
N_SANGRE = 5

S = estaticos()
REG = S["region"]
PERF = perfil()
ANIO_MIN = leer(SALIDA / "anio_mineria.tif")
FIN = int(ANIO_MIN.max())
ANIOS = list(range(1985, FIN + 1))
ULT_LS, ULT_MB = 2025, 2024
ZONAS = json.loads((DATOS / "zonas" / "zonas.json").read_text())

# ---------------- paleta (la misma del video) ----------------
OSCURO = np.array([6, 18, 17], np.float32)
BOSQUE = np.array([40, 86, 72], np.float32)
CREMA = np.array([238, 214, 160], np.float32)
ORO = np.array([214, 160, 70], np.float32)


def gradiente(t, colores):
    t = np.clip(t, 0, 1)
    n = len(colores) - 1
    i = np.minimum((t * n).astype(int), n - 1)
    f = (t * n - i)[..., None]
    c = np.stack(colores)
    return c[i] * (1 - f) + c[i + 1] * f


_cache = {}


def leer_rgb(ruta):
    if ruta not in _cache:
        if len(_cache) > 12:
            _cache.pop(next(iter(_cache)))
        with rasterio.open(ruta) as f:
            a = f.read().astype(np.float32) / 255
        a[:, (a == 0).all(0)] = np.nan          # sin dato
        _cache[ruta] = a
    return _cache[ruta]


def rgb_anio(carpeta, y):
    """Mediana de 3 años (y-1, y, y+1): tapa huecos del satélite y nubes sueltas."""
    y = min(y, ULT_LS)
    vecinos = [a for a in (y - 1, y, y + 1) if 1985 <= a <= ULT_LS]
    pila = np.stack([leer_rgb(carpeta / f"{a}.tif") for a in vecinos])
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return np.nanmedian(pila, axis=0)


def lum_de(rgb):
    return np.nan_to_num(0.3 * rgb[0] + 0.59 * rgb[1] + 0.11 * rgb[2])


def calidez(rgb):
    """Sedimento, tierra removida y pozas son rojizos (R > G); la vegetación es verde."""
    R, G = np.nan_to_num(rgb[0]), np.nan_to_num(rgb[1])
    return np.clip((R - G) / (R + G + 1e-3) * 6, 0, 1)


ANIO_FONDO = 1996          # hasta este año hay pocas imágenes: fondo de bosque de 1997–2001
ANIOS_FONDO = range(1997, 2002)


def fondo_limpio(carpeta):
    pila = np.stack([leer_rgb(carpeta / f"{a}.tif") for a in ANIOS_FONDO])
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return np.nanmedian(pila, axis=0)


def graduar(rgb, lo, hi, alto, fondo=None):
    """`fondo` (opcional): RGB limpio para el bosque; la minería/ríos (lo cálido) salen de `rgb`."""
    t = np.clip((lum_de(rgb) - lo) / max(hi - lo, 1e-3), 0, 1) ** 1.15
    t = np.where(alto, np.minimum(t, 0.45), t)       # nubes residuales en lomas
    tf = t if fondo is None else np.where(
        alto, np.minimum(np.clip((lum_de(fondo) - lo) / max(hi - lo, 1e-3), 0, 1) ** 1.15, 0.45),
        np.clip((lum_de(fondo) - lo) / max(hi - lo, 1e-3), 0, 1) ** 1.15)
    if fondo is not None:
        # donde el fondo ya tiene minería/sedimento, manda el brillo real de ese año
        tf = np.where(calidez(fondo) > 0.25, np.minimum(tf, t), tf)
    frio = gradiente(tf, [OSCURO, BOSQUE, BOSQUE * 1.4, CREMA])
    calido = gradiente(np.clip(t * 1.25, 0, 1), [OSCURO, ORO * 0.55, CREMA])
    k = (calidez(rgb) * np.clip(t * 2.5, 0, 1))[..., None]
    return frio * (1 - k) + calido * k


def textura_pozas(shape, semilla, tam_px):
    """Minería simulada con aspecto de minería real: pozas de agua turbia (verde-ocre)
    separadas por arena removida (crema), con bordes claros. `tam_px` = tamaño típico de poza."""
    rng = np.random.default_rng(semilla)
    norm = lambda a: (a - a.mean()) / a.std()
    grande = norm(ndimage.gaussian_filter(rng.normal(size=shape), tam_px))
    fino = norm(ndimage.gaussian_filter(rng.normal(size=shape), max(tam_px / 4, 0.6)))
    agua = np.clip((-0.35 - grande) * 3, 0, 1)[..., None]          # ~35% pozas
    turbia = rng.random(1)[0]
    c_agua = (np.array([46, 70, 52], np.float32) * (1 - turbia * 0.5) +
              ORO * 0.45 * turbia * 0.5)
    c_agua = c_agua * (0.85 + 0.15 * fino[..., None])
    arena = CREMA * np.clip(0.78 + 0.12 * fino + 0.06 * grande, 0.55, 1.0)[..., None]
    orilla = np.exp(-((grande + 0.35) / 0.12) ** 2)[..., None]     # borde claro de la poza
    return arena * (1 - agua) + c_agua * agua + CREMA * orilla * 0.25


def a_mercator(arr, src_t, n_bandas_lin, dst_t, dst_w, dst_h):
    """Reproyecta (bandas, H, W) de UTM 19S a Web Mercator."""
    out = np.zeros((arr.shape[0], dst_h, dst_w), np.float32)
    for b in range(arr.shape[0]):
        reproject(arr[b].astype(np.float32), out[b], src_transform=src_t, src_crs=PERF["crs"],
                  dst_transform=dst_t, dst_crs="EPSG:3857",
                  resampling=Resampling.bilinear if b < n_bandas_lin else Resampling.nearest)
    return out


def guardar_webp(rgb, alfa, ruta, max_lado=None):
    im = Image.fromarray(np.dstack([np.clip(rgb, 0, 255).astype(np.uint8),
                                    np.clip(alfa, 0, 255).astype(np.uint8)]), "RGBA")
    if max_lado and max(im.size) > max_lado:
        k = max_lado / max(im.size)
        im = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    im.save(ruta, "WEBP", quality=80, method=5)


def limites_latlon(t, w, h):
    w_, s_, e_, n_ = transform_bounds("EPSG:3857", "EPSG:4326", t.c, t.f + t.e * h, t.c + t.a * w, t.f)
    return [[s_, w_], [n_, e_]]


# ---------------- preparación región ----------------
H, W = REG.shape
T_REG = PERF["transform"]
dt, dw, dh = calculate_default_transform(PERF["crs"], "EPSG:3857", W, H,
                                         *rasterio.transform.array_bounds(H, W, T_REG))
REG_LIM = limites_latlon(dt, dw, dh)
ALTO = S["hnd"] > 25
ruido_reg = textura_pozas(REG.shape, 7, 1.0)
FONDO_REG = fondo_limpio(DATOS / "landsat")

# ---------------- preparación zonas ----------------
zonas = []
for z in ZONAS:
    n = z["lado_px"]
    zt = Affine(*z["transform"])
    d = DATOS / "zonas" / z["id"]

    def a_zona(arr, metodo):
        out = np.zeros((n, n), np.float32)
        reproject(arr.astype(np.float32), out, src_transform=T_REG, src_crs=PERF["crs"],
                  dst_transform=zt, dst_crs=PERF["crs"], resampling=metodo)
        return out

    # año de minería suavizado + ruido -> bordes orgánicos a 30 m
    campo = np.where(ANIO_MIN > 0, ANIO_MIN, 2400).astype(np.float32)
    campo_z = a_zona(campo, Resampling.bilinear)
    rng_z = np.random.default_rng(11)
    r1 = ndimage.gaussian_filter(rng_z.normal(size=(n, n)), 14)
    r2 = ndimage.gaussian_filter(rng_z.normal(size=(n, n)), 3)
    campo_z += 3.0 * r1 / r1.std() + 0.8 * r2 / r2.std()   # borde orgánico (manchas, no granulado)
    zdt, zdw, zdh = calculate_default_transform(PERF["crs"], "EPSG:3857", n, n,
                                                *rasterio.transform.array_bounds(n, n, zt))
    yy, xx = np.mgrid[0:n, 0:n]
    borde = np.minimum.reduce([yy, xx, n - 1 - yy, n - 1 - xx]).astype(np.float32)
    zonas.append({
        **z, "n": n, "t": zt, "dir": d, "a_zona": a_zona, "campo": campo_z,
        "alto": a_zona(S["hnd"], Resampling.bilinear) > 25,
        "mb2024": leer(d / "mapbiomas" / f"{ULT_MB}.tif"),
        "pozas": textura_pozas((n, n), 13, 4.0),
        "fondo": fondo_limpio(d / "landsat"),
        "alfa": np.clip(borde / 40, 0, 1) * 255,      # bordes difuminados
        "dt": zdt, "dw": zdw, "dh": zdh, "limites": limites_latlon(zdt, zdw, zdh),
    })


def venas(c, mineria):
    v = np.clip(np.log1p(c) / np.log1p(20000), 0, 1)
    v[mineria & ~S["rio"]] = 0
    return v


def cuadro_region(y, rgb, lo, hi, v):
    img = graduar(rgb, lo, hi, ALTO, FONDO_REG if y <= ANIO_FONDO else None)
    if y > ULT_MB:
        nueva = ((ANIO_MIN > ULT_MB) & (ANIO_MIN <= y)).astype(np.float32)[..., None]
        img = img * (1 - nueva) + ruido_reg * nueva
    brillo = ndimage.gaussian_filter(v, 1.2) * 1.3 + v
    img = img + ORO * np.clip(brillo, 0, 1.2)[..., None] * 0.9
    return img


def cuadro_zona(z, y, lo, hi, v):
    rgb = rgb_anio(z["dir"] / "landsat", y)
    img = graduar(rgb, lo, hi, z["alto"], z["fondo"] if y <= ANIO_FONDO else None)
    mb = leer(z["dir"] / "mapbiomas" / f"{min(y, ULT_MB)}.tif")
    if y > ULT_MB:
        nueva = ((z["campo"] <= y) & (z["mb2024"] != 30)).astype(np.float32)
        nueva = ndimage.gaussian_filter(nueva, 0.7)[..., None]
        img = img * (1 - nueva) + z["pozas"] * nueva
    # la carga contaminante viene de la red de 120 m, pero se pinta sobre el AGUA REAL
    # que se ve a 30 m (los ríos migran y no calzan exacto con la red)
    vz = z["a_zona"](v, Resampling.bilinear)
    vz = ndimage.gaussian_filter(ndimage.maximum_filter(vz, size=31), 4)
    agua = ((mb == 33) | (calidez(rgb) > 0.35)).astype(np.float32)
    agua = ndimage.gaussian_filter(agua, 0.6)
    brillo = vz * agua * 1.5 + ndimage.gaussian_filter(vz * agua, 2.5) * 0.7
    img = img + ORO * np.clip(brillo, 0, 1.2)[..., None] * 0.9
    return img


if __name__ == "__main__":
    import sys
    solo = [int(a) for a in sys.argv[1:]]          # p.ej. "python 06_web.py 1985 1996" = solo ese rango
    if not solo and FR.exists():
        shutil.rmtree(FR)
    t0 = time.time()
    finales = {}
    for y in ANIOS:
        if solo and not (solo[0] <= y <= solo[-1]) and y != ANIOS[-1]:
            continue
        mineria = (ANIO_MIN > 0) & (ANIO_MIN <= y)
        v = venas(contaminacion(mineria), mineria)
        rgb_reg = rgb_anio(DATOS / "landsat", y)
        lum = lum_de(FONDO_REG if y <= ANIO_FONDO else rgb_reg)
        lo, hi = np.percentile(lum[REG], 2), np.percentile(lum[REG], 99.7)

        img = cuadro_region(y, rgb_reg, lo, hi, v)
        img[~REG] = 0
        merc = a_mercator(np.concatenate([np.moveaxis(img, -1, 0), REG[None] * 255.0]),
                          T_REG, 3, dt, dw, dh)
        rgb, alfa = np.moveaxis(merc[:3], 0, -1), merc[3]
        guardar_webp(rgb, alfa, FR / "region" / f"{y}.webp", MAX_LADO_REGION)
        finales["region"] = (rgb, alfa, MAX_LADO_REGION)

        for z in zonas:
            zi = cuadro_zona(z, y, lo, hi, v)
            merc = a_mercator(np.concatenate([np.moveaxis(zi, -1, 0), z["alfa"][None]]),
                              z["t"], 4, z["dt"], z["dw"], z["dh"])
            rgb, alfa = np.moveaxis(merc[:3], 0, -1), merc[3]
            guardar_webp(rgb, alfa, FR / z["id"] / f"{y}.webp")
            finales[z["id"]] = (rgb, alfa, None)
        print(y, f"({time.time() - t0:.0f}s)", end="  ", flush=True)

    print("\nFinal en sangre...", flush=True)
    for clave, (rgb, alfa, ml) in finales.items():
        fx = FinalSangre(np.clip(rgb, 0, 255).astype(np.uint8), con_texto=False)
        for k in range(1, N_SANGRE + 1):
            guardar_webp(fx.cuadro(k / N_SANGRE), alfa, FR / clave / f"sangre_{k}.webp", ml)

    resumen = {}
    with open(SALIDA / "resumen.csv") as f:
        for r in csv.DictReader(f):
            resumen[int(r["anio"])] = {"km2": float(r["mineria_km2"]),
                                       "rios": float(r["pct_rios_contaminados"])}
    datos = {
        "anios": ANIOS, "ultimoReal": ULT_MB, "nSangre": N_SANGRE,
        "region": {"limites": REG_LIM},
        "zonas": [{"id": z["id"], "nombre": z["nombre"], "limites": z["limites"],
                   "centro": [z["lat"], z["lon"]]} for z in zonas],
        "resumen": resumen,
    }
    (WEB / "datos.js").write_text("window.DATOS = " + json.dumps(datos, ensure_ascii=False) + ";\n")
    total = sum(p.stat().st_size for p in FR.rglob("*.webp")) / 1e6
    print(f"Listo: web/  ({total:.0f} MB de imágenes)")
