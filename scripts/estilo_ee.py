"""
estilo_ee.py — el estilo "venas de oro" calculado dentro de Earth Engine
(la misma lógica que gee/app_venas_de_oro.js; sirve para probar desde Python).

  python estilo_ee.py            -> salida/prueba_estilo/*.png (zonas, Landsat y Sentinel-2)
"""
import json
from pathlib import Path

import ee

RAIZ = Path(__file__).resolve().parent.parent
PROYECTO = "mineria-mmd-514207"

# rango de brillo FIJO (reflectancia), medido sobre Madre de Dios 1997–2025
LO, HI = 0.022, 0.20
GAMMA = 0.95
# paleta sacada de las imágenes de referencia: bosque verde oliva, sedimento durazno-dorado
OSCURO, BOSQUE, BOSQUE2, CREMA = "101c14", "2f4630", "526b48", "e8c496"
ORO_OSC = "8a6438"


# ---------------- colecciones ----------------
def _l(bandas):
    def f(img):
        ok = img.select("QA_PIXEL").bitwiseAnd(31).eq(0)
        return (img.select(bandas, ["R", "G", "B"]).multiply(0.0000275).add(-0.2)
                .updateMask(ok).copyProperties(img, ["system:time_start"]))
    return f


def landsat():
    b57, b89 = ["SR_B3", "SR_B2", "SR_B1"], ["SR_B4", "SR_B3", "SR_B2"]
    return (ee.ImageCollection("LANDSAT/LT05/C02/T1_L2").map(_l(b57))
            .merge(ee.ImageCollection("LANDSAT/LE07/C02/T1_L2").map(_l(b57)))
            .merge(ee.ImageCollection("LANDSAT/LC08/C02/T1_L2").map(_l(b89)))
            .merge(ee.ImageCollection("LANDSAT/LC09/C02/T1_L2").map(_l(b89))))


def sentinel2():
    cs = ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED")
    s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").linkCollection(cs, ["cs_cdf"])
    return s2.map(lambda i: i.select(["B4", "B3", "B2"], ["R", "G", "B"]).divide(10000)
                  .updateMask(i.select("cs_cdf").gte(0.6))
                  .copyProperties(i, ["system:time_start"]))


def compuesto(col, anio, region=None, radio=1):
    """Mediana de la temporada seca (mayo–octubre) de anio±radio años: tapa huecos y nubes.
    Landsat: radio=1 (3 años). Sentinel-2: radio=0 (con 3 años excede la memoria de EE)."""
    c = col.filter(ee.Filter.calendarRange(5, 10, "month"))
    c = c.filterDate(f"{anio - radio}-01-01", f"{anio + radio + 1}-01-01")
    if region is not None:
        c = c.filterBounds(region)
    return c.median()


# ---------------- estilo ----------------
def estilo(rgb):
    R, G, B = rgb.select("R"), rgb.select("G"), rgb.select("B")
    lum = R.multiply(0.3).add(G.multiply(0.59)).add(B.multiply(0.11))
    t = lum.subtract(LO).divide(HI - LO).clamp(0, 1).pow(GAMMA)
    # lomas/montañas: atenúa nubes residuales (altura sobre el río > 25 m)
    alto = ee.Image("MERIT/Hydro/v1_0_1").select("hnd").gt(25)
    t = t.where(alto.And(t.gt(0.45)), 0.45)
    frio = t.visualize(min=0, max=1, palette=[OSCURO, BOSQUE, BOSQUE2, CREMA]).toFloat()
    calido = t.multiply(1.15).clamp(0, 1).visualize(min=0, max=1,
                                                     palette=[OSCURO, ORO_OSC, "c99a62", CREMA]).toFloat()
    calidez = R.subtract(G).divide(R.add(G).add(0.001)).multiply(6).clamp(0, 1)
    k = calidez.multiply(t.multiply(2.5).clamp(0, 1))
    return frio.multiply(ee.Image(1).subtract(k)).add(calido.multiply(k)).toUint8()


if __name__ == "__main__":
    import urllib.request
    ee.Initialize(project=PROYECTO)
    zonas = json.loads((RAIZ / "datos" / "zonas" / "zonas.json").read_text())
    out = RAIZ / "salida" / "prueba_estilo"
    out.mkdir(parents=True, exist_ok=True)
    L, S2 = landsat(), sentinel2()
    for z in zonas:
        caja = ee.Geometry.Point([z["lon"], z["lat"]]).buffer(14000).bounds()
        for nombre, col, anio, radio in (("landsat", L, 2020, 1), ("sentinel", S2, 2023, 0)):
            img = estilo(compuesto(col, anio, caja, radio))
            url = img.getThumbURL({"region": caja, "dimensions": 1024, "format": "png"})
            urllib.request.urlretrieve(url, out / f"{z['id']}_{nombre}_{anio}.png")
            print(z["id"], nombre, "ok", flush=True)
