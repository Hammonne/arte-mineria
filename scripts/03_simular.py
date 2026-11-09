"""
03_simular.py — proyecta la minería desde 2024 hacia el futuro, año por año,
hasta que cubra la fracción `--hasta` de Madre de Dios.
CUÁNTO crece: tasa histórica. DÓNDE: BFS con pesos (Dijkstra) desde la minería de 2024.

ESCENARIO ESPECULATIVO: supone que la minería sigue creciendo a la misma tasa
histórica (≈9.4% anual, 2014–2024) y que se expande donde el modelo aprendió
que suele expandirse. No es un pronóstico: es "qué pasaría si sigue la tendencia".

Salidas en salida/:
  anio_mineria.tif   año en que cada píxel se volvió minería (real ≤2024, simulado >2024; 0 = nunca)
  resumen.csv        por año: km² de minería, % de la región, km de río contaminado

Uso:
  python 03_simular.py                 # tasa histórica, hasta 95% de la región
  python 03_simular.py --tasa 0.15     # más rápido
  python 03_simular.py --hasta 0.5     # parar al 50%
"""
import argparse
import csv
import time

import joblib
import numpy as np
import rasterio

from comun import (ANTROPICO, BOSQUE, SALIDA, avance_dijkstra, clases, contaminacion,
                   estaticos, mineria_acumulada, perfil)

ap = argparse.ArgumentParser()
ap.add_argument("--tasa", type=float, default=None, help="crecimiento anual (0.094 = 9.4%%)")
ap.add_argument("--hasta", type=float, default=0.95, help="fracción de la región donde parar")
ap.add_argument("--max-anio", type=int, default=2300)
ap.add_argument("--semilla", type=int, default=7)
ap.add_argument("--fuerza", type=float, default=0.0,
                help="0 = BFS compacto (el que mejor predijo 2014–2024); >0 = sigue más los corredores favorables")
args = ap.parse_args()

datos = joblib.load(SALIDA / "modelo.joblib")
modelo = datos["modelo"]
tasa = args.tasa if args.tasa is not None else datos["tasa_anual"]
S = estaticos()
REG = S["region"]
N_REG = REG.sum()
rio = S["rio"]
rng = np.random.default_rng(args.semilla)

# historia real
anio_min = np.zeros(REG.shape, np.uint16)
MIN = mineria_acumulada(range(1985, 2025))
for y in range(2024, 1984, -1):
    anio_min[MIN[y]] = y
m = MIN[2024]
cls = clases(2024)
antr = np.isin(cls, list(ANTROPICO))
bosq = np.isin(cls, list(BOSQUE)).astype(np.float32)

filas = []


def registrar(y, m, simulado):
    c = contaminacion(m)
    km_rio = ((c >= 1) & rio & REG).sum() * 0.12
    pct_rio = 100 * ((c >= 1) & rio & REG).sum() / (rio & REG).sum()
    km2 = m[REG].sum() * 0.0144
    filas.append({"anio": y, "simulado": int(simulado), "mineria_km2": round(km2, 1),
                  "pct_region": round(100 * m[REG].sum() / N_REG, 2),
                  "rio_contaminado_km": round(km_rio), "pct_rios_contaminados": round(pct_rio, 1)})
    f = filas[-1]
    print(f"{y}{'*' if simulado else ' '}  minería {f['mineria_km2']:>9,.0f} km²  "
          f"({f['pct_region']:5.1f}% región)   ríos contaminados {f['pct_rios_contaminados']:5.1f}%",
          flush=True)


print(f"Tasa de crecimiento: {100 * tasa:.1f}% anual   (* = simulado)\n")
for y in range(1985, 2025):
    registrar(y, MIN[y], False)

# cuántos píxeles nuevos cada año (crecimiento exponencial a la tasa histórica)
area = m[REG].sum()
cuotas = []
while area < args.hasta * N_REG and 2024 + len(cuotas) < args.max_anio:
    n = int(np.ceil(area * tasa))
    cuotas.append(n)
    area += n

# dónde: BFS con pesos (Dijkstra) desde la minería de 2024
futuro = avance_dijkstra(modelo, m, antr, bosq, REG, cuotas, 2025, rng, fuerza=args.fuerza)
anio_min[futuro > 0] = futuro[futuro > 0]
for y in range(2025, 2025 + len(cuotas)):
    registrar(y, (anio_min > 0) & (anio_min <= y), True)

p = perfil()
p.update(dtype="uint16", count=1, compress="deflate", nodata=0)
with rasterio.open(SALIDA / "anio_mineria.tif", "w", **p) as f:
    f.write(anio_min, 1)
with open(SALIDA / "resumen.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=filas[0].keys())
    w.writeheader()
    w.writerows(filas)
print("\nGuardado: salida/anio_mineria.tif y salida/resumen.csv")
