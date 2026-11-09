"""
02_entrenar.py — aprende de la historia (1985–2024) DÓNDE aparece minería nueva.

1. Validación: entrena solo con 1990–2013 y simula 2014→2024 sin mirar el mapa real
   (solo usa cuántos km² crecieron cada año), luego compara con lo que pasó de verdad.
2. Modelo final: entrena con 1990–2023 y lo guarda en salida/modelo.joblib,
   junto con la tasa de crecimiento histórica (para decidir CUÁNTO crece).
"""
import time

import joblib
import numpy as np
from scipy import ndimage
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

from comun import (ANTROPICO, BOSQUE, NOMBRES_VARIABLES, SALIDA, clases, estaticos,
                   mineria_acumulada, paso, probabilidades, variables)

NEG_POR_ANIO = 150_000
rng = np.random.default_rng(42)
S = estaticos()
REG = S["region"]

ANIOS = list(range(1985, 2025))
print("Cargando minería acumulada...", flush=True)
MIN = mineria_acumulada(ANIOS)
CLS = {y: clases(y) for y in ANIOS}
km2 = lambda a: a[REG].sum() * 0.0144


def ejemplos(anios_t):
    X, y, w = [], [], []
    for t in anios_t:
        m0, m1 = MIN[t], MIN[t + 1]
        cand = REG & ~m0 & (CLS[t] != 0)
        pos = np.flatnonzero(cand & m1)
        neg_all = np.flatnonzero(cand & ~m1)
        neg = rng.choice(neg_all, size=min(NEG_POR_ANIO, neg_all.size), replace=False)
        idx = np.concatenate([pos, neg])
        antr = np.isin(CLS[t], list(ANTROPICO))
        bosq = np.isin(CLS[t], list(BOSQUE)).astype(np.float32)
        X.append(variables(m0, antr, bosq, idx))
        y.append(np.r_[np.ones(pos.size), np.zeros(neg.size)])
        w.append(np.r_[np.ones(pos.size), np.full(neg.size, neg_all.size / neg.size)])
    return np.vstack(X), np.concatenate(y), np.concatenate(w)


def entrenar(anios_t):
    t0 = time.time()
    X, y, w = ejemplos(anios_t)
    m = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08, max_leaf_nodes=31,
                                       min_samples_leaf=200, random_state=0)
    m.fit(X, y, sample_weight=w)
    print(f"  entrenado con {len(y):,} ejemplos ({int(y.sum()):,} positivos) en {time.time()-t0:.0f}s",
          flush=True)
    return m


def acierto(sim_nuevo, real_nuevo, km=1.0):
    cerca = ndimage.binary_dilation(sim_nuevo, iterations=int(round(km / 0.12)))
    return 100 * (real_nuevo & cerca).sum() / real_nuevo.sum()


if __name__ == "__main__":
    SALIDA.mkdir(exist_ok=True)

    print("\n== Validación: entrena 1990–2013, predice DÓNDE 2014–2024 a ciegas ==", flush=True)
    mod_val = entrenar(range(1990, 2014))
    antr = np.isin(CLS[2014], list(ANTROPICO))
    bosq = np.isin(CLS[2014], list(BOSQUE)).astype(np.float32)

    # a) ¿el modelo ordena bien los píxeles? (AUC: 0.5 = azar, 1 = perfecto)
    cand, p = probabilidades(mod_val, MIN[2014], antr, bosq, REG)
    real_nuevo = MIN[2024] & ~MIN[2014]
    print(f"AUC (¿quién se mina entre 2014 y 2024?): {roc_auc_score(real_nuevo.ravel()[cand], p):.3f}")

    # b) simulación con la cantidad real de cada año
    m = MIN[2014]
    r = np.random.default_rng(1)
    for y in range(2015, 2025):
        n = int(MIN[y][REG].sum() - m[REG].sum())
        m = paso(mod_val, m, antr, bosq, REG, n, r)
    sim_nuevo = m & ~MIN[2014]
    azar = np.zeros_like(sim_nuevo)
    azar.ravel()[r.choice(cand, size=int(sim_nuevo.sum()), replace=False)] = True
    print(f"Minería nueva real 2014–2024 a < 1 km de la simulada: {acierto(sim_nuevo, real_nuevo):.0f}%"
          f"   (misma cantidad al azar: {acierto(azar, real_nuevo):.0f}%)")

    # tasa de crecimiento histórica (exponencial, últimos 10 años)
    anios = np.arange(2014, 2025)
    areas = np.array([km2(MIN[y]) for y in anios])
    tasa = float(np.exp(np.polyfit(anios, np.log(areas), 1)[0]) - 1)
    print(f"\nCrecimiento histórico 2014–2024: {100 * tasa:.1f}% por año "
          f"({areas[0]:.0f} → {areas[-1]:.0f} km²)")

    print("\n== Modelo final: entrena 1990–2023 ==", flush=True)
    modelo = entrenar(range(1990, 2024))
    joblib.dump({"modelo": modelo, "variables": NOMBRES_VARIABLES, "tasa_anual": tasa},
                SALIDA / "modelo.joblib")
    print("Guardado en salida/modelo.joblib")
