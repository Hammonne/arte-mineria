"""
07_precalcular_ee.py — precalcula en Earth Engine la imagen con estilo de cada año y la guarda
como asset del proyecto. Así el mapa solo LEE imágenes ya hechas (rápido, como Google Earth)
en vez de combinar cientos de fotos satelitales en cada cuadrito.

Corre en los servidores de Google: se puede cerrar la compu mientras tanto.

  python 07_precalcular_ee.py           # lanza las tareas que falten
  python 07_precalcular_ee.py estado    # muestra cuántas van
"""
import sys
import warnings

import ee

from estilo_ee import PROYECTO, compuesto, estilo, landsat, sentinel2

warnings.filterwarnings("ignore")
ee.Initialize(project=PROYECTO)

RAIZ_ASSETS = f"projects/{PROYECTO}/assets"
COL_LANDSAT = f"{RAIZ_ASSETS}/venas_landsat"     # 30 m, 1985–2025
COL_S2 = f"{RAIZ_ASSETS}/venas_sentinel2"         # 10 m, 2017–2025
CRS = "EPSG:32719"

# Madre de Dios + alrededores (Cusco, Puno, norte de Bolivia, Acre)
CAJA_LANDSAT = ee.Geometry.Rectangle([-72.5, -14.3, -68.3, -10.0])
# corredor minero (Huepetuhe, La Pampa, Boca Colorado, Laberinto) a 10 m
CAJA_S2 = ee.Geometry.Rectangle([-70.9, -13.3, -68.9, -12.2])

# orden: primero los años clave (para tener pronto una versión usable), luego el resto
CLAVE = [2024, 2020, 2015, 2010, 2005, 2000, 1995, 1990]
_l = [(COL_LANDSAT, y, False, CAJA_LANDSAT, 30) for y in range(1985, 2026)]
_s = [(COL_S2, y, True, CAJA_S2, 10) for y in range(2017, 2026)]
TRABAJOS = ([t for t in _l if t[1] in CLAVE[:4]] + [t for t in _s if t[1] == 2024] +
            [t for t in _l if t[1] in CLAVE[4:]] + [t for t in _s if t[1] == 2020] +
            [t for t in _l if t[1] not in CLAVE] + [t for t in _s if t[1] not in (2020, 2024)])


def existe(ruta):
    try:
        ee.data.getAsset(ruta)
        return True
    except ee.EEException:
        return False


def lanzar():
    for col in (COL_LANDSAT, COL_S2):
        if not existe(col):
            ee.data.createAsset({"type": "IMAGE_COLLECTION"}, col)
    activas = {t["description"] for t in ee.data.getTaskList()
               if t["state"] in ("READY", "RUNNING")}
    L, S2 = landsat(), sentinel2()
    n = 0
    for col, anio, s2, caja, escala in TRABAJOS:
        nombre = f"{col.split('/')[-1]}_{anio}"
        if existe(f"{col}/{anio}") or nombre in activas:
            continue
        img = (estilo(compuesto(S2 if s2 else L, anio, caja, 0 if s2 else 1))
               .set({"anio": anio, "system:time_start": ee.Date.fromYMD(anio, 7, 1).millis()}))
        ee.batch.Export.image.toAsset(
            image=img, description=nombre, assetId=f"{col}/{anio}", region=caja,
            scale=escala, crs=CRS, maxPixels=1e13,
            pyramidingPolicy={".default": "mean"}).start()
        n += 1
    print(f"Tareas lanzadas: {n}")


def estado():
    hechos = sum(existe(f"{c}/{y}") for c, y, *_ in TRABAJOS)
    tareas = [t for t in ee.data.getTaskList() if t["description"].startswith("venas_")]
    por = {}
    for t in tareas:
        por[t["state"]] = por.get(t["state"], 0) + 1
    print(f"Imágenes listas: {hechos}/{len(TRABAJOS)}   tareas: {por}")
    for t in tareas:
        if t["state"] == "FAILED":
            print("  FALLÓ", t["description"], t.get("error_message", "")[:150])


def reordenar():
    """Cancela las tareas en cola (no las que ya corren) y las relanza en el orden de TRABAJOS."""
    for t in ee.data.getTaskList():
        if t["state"] == "READY" and t["description"].startswith("venas_"):
            ee.data.cancelTask(t["id"])
    lanzar()


if __name__ == "__main__":
    if "estado" in sys.argv:
        estado()
    elif "reordenar" in sys.argv:
        reordenar()
    else:
        lanzar()
