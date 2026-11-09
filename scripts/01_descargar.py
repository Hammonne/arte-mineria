"""
01_descargar.py — baja todo Madre de Dios desde Earth Engine a datos/

Capas (todas en la misma grilla: UTM 19S, 120 m por píxel):
  datos/mapbiomas/AAAA.tif     clases de MapBiomas Perú por año (30 = minería, 33 = agua, 3 = bosque...)
  datos/landsat/AAAA.tif       imagen satelital RGB por año (temporada seca), para el video
  datos/estaticos/*.tif        región, elevación, ríos (acumulación y dirección del agua), áreas protegidas

Uso:
  conda activate mineria
  python scripts/01_descargar.py            # baja todo (si se corta, vuelve a correrlo: retoma)
  python scripts/01_descargar.py --prueba   # solo 2 años, para probar rápido
"""
import json
import math
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import ee
import numpy as np
import rasterio
from rasterio.transform import Affine
from rasterio.warp import transform_bounds

warnings.filterwarnings("ignore", category=DeprecationWarning)

PROYECTO = "mineria-mmd-514207"
CRS = "EPSG:32719"
ESCALA = 120          # metros por píxel
TILE = 1024           # píxeles por lado de cada pedazo que se pide a Earth Engine
HILOS = 6             # descargas en paralelo
MB_ANIOS = range(1985, 2025)        # MapBiomas colección 3: 1985–2024
LS_ANIOS = range(1985, 2026)        # Landsat: 1985–2025
MAPBIOMAS = ("projects/mapbiomas-public/assets/peru/collection3/"
             "mapbiomas_peru_collection3_integration_v1")

RAIZ = Path(__file__).resolve().parent.parent / "datos"

ee.Initialize(project=PROYECTO)

region_fc = (ee.FeatureCollection("FAO/GAUL/2015/level1")
             .filter(ee.Filter.eq("ADM1_NAME", "Madre de Dios")))
region = region_fc.geometry()

# ---------------- grilla común ----------------
lon_lat = region.bounds().coordinates().getInfo()[0]
lons = [c[0] for c in lon_lat]
lats = [c[1] for c in lon_lat]
xmin, ymin, xmax, ymax = transform_bounds("EPSG:4326", CRS, min(lons), min(lats),
                                          max(lons), max(lats), densify_pts=50)
X0 = math.floor(xmin / ESCALA) * ESCALA
Y0 = math.ceil(ymax / ESCALA) * ESCALA
ANCHO = math.ceil((xmax - X0) / ESCALA)
ALTO = math.ceil((Y0 - ymin) / ESCALA)
TRANSFORM = Affine(ESCALA, 0, X0, 0, -ESCALA, Y0)


def bajar_tile(img, fila, col, w, h, intentos=4):
    req = {
        "expression": img,
        "fileFormat": "NUMPY_NDARRAY",
        "grid": {
            "dimensions": {"width": w, "height": h},
            "affineTransform": {
                "scaleX": ESCALA, "shearX": 0, "translateX": X0 + col * ESCALA,
                "shearY": 0, "scaleY": -ESCALA, "translateY": Y0 - fila * ESCALA,
            },
            "crsCode": CRS,
        },
    }
    for k in range(intentos):
        try:
            arr = ee.data.computePixels(req)
            # array estructurado (h, w) con un campo por banda -> (bandas, h, w)
            return np.stack([arr[n] for n in arr.dtype.names])
        except Exception as e:  # límites de cuota / timeouts: reintentar
            if k == intentos - 1:
                raise
            time.sleep(5 * (k + 1))
            print(f"    reintento {k + 1} ({str(e)[:80]})", flush=True)


def guardar(img, ruta, dtype, nbandas):
    ruta = Path(ruta)
    if ruta.exists():
        return
    ruta.parent.mkdir(parents=True, exist_ok=True)
    out = np.zeros((nbandas, ALTO, ANCHO), dtype=dtype)
    trabajos = []
    with ThreadPoolExecutor(HILOS) as ex:
        for f in range(0, ALTO, TILE):
            for c in range(0, ANCHO, TILE):
                w, h = min(TILE, ANCHO - c), min(TILE, ALTO - f)
                trabajos.append((f, c, h, w, ex.submit(bajar_tile, img, f, c, w, h)))
        for f, c, h, w, fut in trabajos:
            out[:, f:f + h, c:c + w] = fut.result()
    tmp = ruta.with_suffix(".tmp.tif")
    with rasterio.open(tmp, "w", driver="GTiff", width=ANCHO, height=ALTO, count=nbandas,
                       dtype=dtype, crs=CRS, transform=TRANSFORM, compress="deflate",
                       tiled=True) as dst:
        dst.write(out)
    tmp.rename(ruta)


# ---------------- Landsat ----------------
NOMBRES = ["R", "G", "B"]


def preparar(bandas):
    def f(img):
        limpio = img.select("QA_PIXEL").bitwiseAnd(31).eq(0)
        return (img.select(bandas, NOMBRES).multiply(0.0000275).add(-0.2)
                .updateMask(limpio).copyProperties(img, ["system:time_start"]))
    return f


B57, B89 = ["SR_B3", "SR_B2", "SR_B1"], ["SR_B4", "SR_B3", "SR_B2"]
landsat = (ee.ImageCollection("LANDSAT/LT05/C02/T1_L2").map(preparar(B57))
           .merge(ee.ImageCollection("LANDSAT/LE07/C02/T1_L2").map(preparar(B57)))
           .merge(ee.ImageCollection("LANDSAT/LC08/C02/T1_L2").map(preparar(B89)))
           .merge(ee.ImageCollection("LANDSAT/LC09/C02/T1_L2").map(preparar(B89)))
           .filterBounds(region))
vacia = ee.Image.constant([0, 0, 0]).rename(NOMBRES).updateMask(0)


def landsat_anio(y):
    col = landsat.filterDate(f"{y}-05-01", f"{y}-10-31").merge(ee.ImageCollection([vacia]))
    return (col.median().unitScale(0, 0.3).clamp(0, 1).multiply(255)
            .unmask(0).clip(region).unmask(0).toUint8())


def main():
    prueba = "--prueba" in sys.argv
    mb_anios = [2000, 2024] if prueba else list(MB_ANIOS)
    ls_anios = [2000, 2024] if prueba else list(LS_ANIOS)

    print(f"Grilla: {ANCHO} x {ALTO} píxeles de {ESCALA} m  ({ANCHO * ALTO / 1e6:.1f} M píxeles)")
    (RAIZ).mkdir(exist_ok=True)
    (RAIZ / "grilla.json").write_text(json.dumps({
        "crs": CRS, "escala_m": ESCALA, "ancho": ANCHO, "alto": ALTO,
        "transform": list(TRANSFORM)[:6], "proyecto_ee": PROYECTO,
        "mapbiomas": MAPBIOMAS}, indent=2))

    print("Capas estáticas...", flush=True)
    est = RAIZ / "estaticos"
    guardar(ee.Image(1).clip(region).unmask(0).toUint8(), est / "region.tif", "uint8", 1)
    guardar(ee.Image("USGS/SRTMGL1_003").resample("bilinear").unmask(0).toInt16(),
            est / "elevacion.tif", "int16", 1)
    merit = ee.Image("MERIT/Hydro/v1_0_1")
    # área que drena a cada píxel (km²): los ríos grandes tienen valores altos
    guardar(merit.select("upa")
            # máximo dentro de cada píxel de 120 m: así los ríos (1 píxel de ancho) no se cortan
            .reduceResolution(ee.Reducer.max(), maxPixels=64)
            .unmask(0).toFloat(),
            est / "area_drenaje_km2.tif", "float32", 1)
    # hacia dónde corre el agua (D8: 1=E 2=SE 4=S 8=SO 16=O 32=NO 64=N 128=NE)
    guardar(merit.select("dir").unmask(0).toUint8(),
            est / "direccion_agua.tif", "uint8", 1)
    # altura sobre el río más cercano (m): el oro aluvial está en zonas bajas
    guardar(merit.select("hnd").unmask(0).toFloat(),
            est / "altura_sobre_rio.tif", "float32", 1)
    protegidas = (ee.FeatureCollection("WCMC/WDPA/current/polygons")
                  .filterBounds(region))
    guardar(ee.Image(0).paint(protegidas, 1).toUint8(), est / "protegidas.tif", "uint8", 1)

    mb = ee.Image(MAPBIOMAS)
    for y in mb_anios:
        t = time.time()
        guardar(mb.select(f"classification_{y}").unmask(0).clip(region).unmask(0).toUint8(),
                RAIZ / "mapbiomas" / f"{y}.tif", "uint8", 1)
        print(f"MapBiomas {y} ok ({time.time() - t:.0f}s)", flush=True)

    for y in ls_anios:
        t = time.time()
        guardar(landsat_anio(y), RAIZ / "landsat" / f"{y}.tif", "uint8", 3)
        print(f"Landsat {y} ok ({time.time() - t:.0f}s)", flush=True)

    print("LISTO ✔", flush=True)


if __name__ == "__main__":
    main()
