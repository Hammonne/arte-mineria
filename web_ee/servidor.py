"""
servidor.py — visor local tipo Google Earth con imágenes de Earth Engine en vivo.

Las teselas se calculan en Earth Engine al nivel de zoom que estés mirando
(30 m Landsat 1985+, 10 m Sentinel-2 2017+), con el estilo "venas de oro".

Uso:
  conda activate mineria
  python web_ee/servidor.py          -> abre http://127.0.0.1:8766
"""
import json
import sys
import threading
import warnings
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import ee

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "scripts"))
warnings.filterwarnings("ignore")
from estilo_ee import PROYECTO, compuesto, estilo, landsat, sentinel2  # noqa: E402

PUERTO = 8766
ANIO_S2 = 2017

ee.Initialize(project=PROYECTO)
L, S2 = landsat(), sentinel2()
# zona de trabajo: Madre de Dios + Cusco, Puno, norte de Bolivia, Acre/Rondônia (Brasil)
# (sin este filtro EE intenta combinar todas las imágenes del mundo y se cuelga)
CAJA = ee.Geometry.Rectangle([-74.5, -16.0, -66.0, -8.5])
LIMITE = (ee.Image().byte()
          .paint(ee.FeatureCollection("FAO/GAUL/2015/level1")
                 .filter(ee.Filter.eq("ADM1_NAME", "Madre de Dios")), 1, 1))

_cache, _lock = {}, threading.Lock()
COL_LANDSAT = f"projects/{PROYECTO}/assets/venas_landsat"
COL_S2 = f"projects/{PROYECTO}/assets/venas_sentinel2"
_listos = {"t": 0, "landsat": set(), "s2": set()}


def precalculados():
    """Años ya precalculados por 07_precalcular_ee.py (se revisa cada 60 s)."""
    import time
    if time.time() - _listos["t"] > 60:
        for clave, col in (("landsat", COL_LANDSAT), ("s2", COL_S2)):
            try:
                _listos[clave] = {int(a["name"].split("/")[-1])
                                  for a in ee.data.listAssets({"parent": col}).get("assets", [])}
            except Exception:  # noqa: BLE001
                _listos[clave] = set()
        _listos["t"] = time.time()
    return _listos


def url_teselas(anio, alta):
    p = precalculados()
    s2 = alta and anio >= ANIO_S2
    pre_l = anio in p["landsat"]
    pre_s2 = s2 and anio in p["s2"]
    clave = (anio, alta, pre_l, pre_s2)
    with _lock:
        if clave in _cache:
            return _cache[clave]
    if pre_l:
        # imagen ya hecha: solo se lee (rápido). Sentinel-2 10 m encima donde exista.
        capas = [ee.Image(f"{COL_LANDSAT}/{anio}")]
        if pre_s2:
            capas.append(ee.Image(f"{COL_S2}/{anio}"))
        img = ee.ImageCollection(capas).mosaic()
        fuente = ("Sentinel-2 10 m + Landsat 30 m" if pre_s2 else "Landsat · 30 m") + " · precalculado"
    else:
        img = estilo(compuesto(S2 if s2 else L, anio, CAJA, 0 if s2 else 1))
        fuente = ("Sentinel-2 · 10 m" if s2 else "Landsat · 30 m") + " · en vivo (lento, aún precalculando)"
    m = img.getMapId({"min": 0, "max": 255})
    info = {"url": m["tile_fetcher"].url_format, "fuente": fuente}
    with _lock:
        _cache[clave] = info
    return info


def url_limite():
    if "limite" not in _cache:
        _cache["limite"] = LIMITE.getMapId({"palette": ["e8c496"], "opacity": 0.4})["tile_fetcher"].url_format
    return _cache["limite"]


class Manejador(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(AQUI), **k)

    def log_message(self, *a):
        pass

    def _json(self, datos, codigo=200):
        cuerpo = json.dumps(datos).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/capa":
            q = parse_qs(u.query)
            try:
                anio = int(q["anio"][0])
                alta = q.get("alta", ["1"])[0] == "1"
                return self._json(url_teselas(anio, alta))
            except Exception as e:  # noqa: BLE001
                return self._json({"error": str(e)[:300]}, 500)
        if u.path == "/api/limite":
            return self._json({"url": url_limite()})
        return super().do_GET()


if __name__ == "__main__":
    print(f"Visor en http://127.0.0.1:{PUERTO}  (Ctrl+C para cerrar)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PUERTO), Manejador).serve_forever()
