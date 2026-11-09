"""
05_descargar_zonas.py — baja las zonas mineras en alta resolución (30 m) para el visor web.

Para cada zona (cuadrado de LADO_KM centrado en un foco minero):
  datos/zonas/<id>/landsat/AAAA.tif     RGB por año 1985–2025
  datos/zonas/<id>/mapbiomas/AAAA.tif   clases por año 1985–2024 (30 = minería, 33 = agua)

Uso:  python 05_descargar_zonas.py
"""
import importlib.util
import json
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import ee
import numpy as np
import rasterio
from rasterio.transform import Affine
from rasterio.warp import transform as tr_coords

warnings.filterwarnings("ignore", category=DeprecationWarning)

# reutiliza el compuesto Landsat y la configuración de 01_descargar.py
_spec = importlib.util.spec_from_file_location(
    "d01", Path(__file__).with_name("01_descargar.py"))
d01 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(d01)

ESCALA = 30
LADO_KM = 36
CRS = d01.CRS
RAIZ = d01.RAIZ / "zonas"

# focos encontrados con la densidad de minería 2024 (ventanas de 30 km); nombres aproximados
ZONAS = [
    {"id": "huepetuhe", "nombre": "Huepetuhe", "lat": -12.933, "lon": -70.508},
    {"id": "la_pampa", "nombre": "La Pampa / Interoceánica", "lat": -12.878, "lon": -70.008},
    {"id": "boca_colorado", "nombre": "Río Madre de Dios (Boca Colorado)", "lat": -12.661, "lon": -70.425},
    {"id": "laberinto", "nombre": "Río Madre de Dios (Laberinto)", "lat": -12.654, "lon": -69.717},
]


def landsat_zona(y):
    """Igual que en 01_descargar.py pero sin recortar al límite regional (contexto alrededor)."""
    col = (d01.landsat.filterDate(f"{y}-05-01", f"{y}-10-31")
           .merge(ee.ImageCollection([d01.vacia])))
    return col.median().unitScale(0, 0.3).clamp(0, 1).multiply(255).unmask(0).toUint8()


def grilla(z):
    x, y = tr_coords("EPSG:4326", CRS, [z["lon"]], [z["lat"]])
    n = int(LADO_KM * 1000 / ESCALA)
    x0 = round((x[0] - n * ESCALA / 2) / ESCALA) * ESCALA
    y0 = round((y[0] + n * ESCALA / 2) / ESCALA) * ESCALA
    return n, Affine(ESCALA, 0, x0, 0, -ESCALA, y0)


def bajar(img, n, t, intentos=4):
    req = {"expression": img, "fileFormat": "NUMPY_NDARRAY",
           "grid": {"dimensions": {"width": n, "height": n},
                    "affineTransform": {"scaleX": t.a, "shearX": 0, "translateX": t.c,
                                        "shearY": 0, "scaleY": t.e, "translateY": t.f},
                    "crsCode": CRS}}
    for k in range(intentos):
        try:
            a = ee.data.computePixels(req)
            return np.stack([a[c] for c in a.dtype.names])
        except Exception as e:
            if k == intentos - 1:
                raise
            print(f"    reintento ({str(e)[:70]})", flush=True)
            time.sleep(8 * (k + 1))


def guardar(img, ruta, n, t, dtype):
    if ruta.exists():
        return
    ruta.parent.mkdir(parents=True, exist_ok=True)
    arr = bajar(img, n, t).astype(dtype)
    tmp = ruta.with_suffix(".tmp.tif")
    with rasterio.open(tmp, "w", driver="GTiff", width=n, height=n, count=arr.shape[0],
                       dtype=dtype, crs=CRS, transform=t, compress="deflate", tiled=True) as f:
        f.write(arr)
    tmp.rename(ruta)


if __name__ == "__main__":
    RAIZ.mkdir(parents=True, exist_ok=True)
    meta = []
    trabajos = []
    mb = ee.Image(d01.MAPBIOMAS)
    for z in ZONAS:
        n, t = grilla(z)
        meta.append({**z, "lado_px": n, "transform": list(t)[:6], "crs": CRS, "escala_m": ESCALA})
        d = RAIZ / z["id"]
        for y in d01.MB_ANIOS:
            trabajos.append((mb.select(f"classification_{y}").unmask(0).toUint8(),
                             d / "mapbiomas" / f"{y}.tif", n, t, "uint8", f"{z['id']} MB {y}"))
        for y in d01.LS_ANIOS:
            trabajos.append((landsat_zona(y), d / "landsat" / f"{y}.tif", n, t, "uint8",
                             f"{z['id']} LS {y}"))
    (RAIZ / "zonas.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))

    def correr(job):
        img, ruta, n, t, dt, nombre = job
        t0 = time.time()
        guardar(img, ruta, n, t, dt)
        print(f"{nombre} ok ({time.time() - t0:.0f}s)", flush=True)

    with ThreadPoolExecutor(6) as ex:
        list(ex.map(correr, trabajos))
    print("LISTO ✔")
