"""
final_sangre.py — efecto dramático final: las venas doradas se vuelven sangre,
se expanden, gotean hacia abajo y todo se tiñe de rojo antes de irse a negro.

Se usa desde 04_video.py; también se puede probar sola:
  python final_sangre.py      -> salida/final_sangre_prueba.png
"""
import numpy as np
from scipy import ndimage

SANGRE = np.array([118, 2, 10], np.float32)       # rojo sangre
SANGRE_OSC = np.array([48, 0, 4], np.float32)     # sangre seca / sombras
SANGRE_BRI = np.array([200, 22, 28], np.float32)  # brillo húmedo


def _suave(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


class FinalSangre:
    def __init__(self, cuadro_final, semilla=3):
        F = cuadro_final.astype(np.float32)
        self.F = F
        R, G, B = F[..., 0], F[..., 1], F[..., 2]
        lum = F.mean(-1)
        # "venas": píxeles dorados/crema (R alto, B bajo)
        self.w = np.clip((R - B) / 140, 0, 1) * np.clip(lum / 170, 0, 1)
        H0 = lum.shape[0]
        self.w_mapa = self.w.copy()          # sin el texto (no gotea)
        self.w_mapa[:int(H0 * 0.12)] = 0
        self.w_mapa[int(H0 * 0.92):] = 0
        self.lum = lum / 255
        H, W = lum.shape
        rng = np.random.default_rng(semilla)
        # columnas que gotean (pocas, irregulares)
        col = ndimage.gaussian_filter1d(rng.random(W), 5)
        col = np.clip((col - np.percentile(col, 55)) / (col.max() - np.percentile(col, 55)), 0, 1) ** 0.7
        self.col = col[None, :]
        # largo de cada gota (varía por columna)
        self.largo = (0.3 + 0.7 * ndimage.gaussian_filter1d(rng.random(W), 1))[None, :]
        self.H = H

    def cuadro(self, t):
        """t en [0, 1]: 0 = dorado original, 1 = todo sangre."""
        e = _suave(t)
        F, w = self.F, self.w

        # 1. las venas cambian de oro a sangre
        e1 = _suave(t * 2.2)
        rojo = SANGRE + (SANGRE_BRI - SANGRE) * self.lum[..., None]
        img = F * (1 - w[..., None] * e1) + rojo * w[..., None] * e1

        # 2. el resto se oscurece y se tiñe
        tinte = F.mean(-1, keepdims=True) * np.array([0.9, 0.12, 0.12])
        img = img * (1 - 0.7 * e) + tinte * 0.5 * e

        # 3. la sangre se expande (sangrado)
        sig = 1 + 10 * e
        exp = np.clip(ndimage.gaussian_filter(w, sig) * (1.0 + 2.0 * e), 0, 1)[..., None]
        a = 0.75 * _suave(t * 1.6)
        # mezcla (no suma): la sangre cubre, no satura
        img = img * (1 - exp * a) + np.maximum(img, SANGRE_OSC + (SANGRE - SANGRE_OSC) * exp) * exp * a

        # 4. gotea hacia abajo
        if t > 0.25:
            et = _suave((t - 0.25) / 0.75)
            largo = max(2, int(self.H * 0.35 * et))
            gotas = np.zeros_like(w)
            fuente = np.clip(ndimage.gaussian_filter(self.w_mapa, 2.5) * 2.5, 0, 1) * self.col
            # suma decreciente de copias desplazadas hacia abajo
            for k, d in enumerate(np.linspace(0, largo, 24)):
                d = int(d)
                desp = np.zeros_like(fuente)
                desp[d:] = fuente[:self.H - d] if d else fuente
                lim = (np.arange(self.H)[:, None] - 0) >= 0
                gotas = np.maximum(gotas, desp * (1 - k / 24) ** 0.6 * (self.largo >= k / 24) * lim)
            gotas = ndimage.gaussian_filter(gotas, (2.0, 2.2))
            img = img * (1 - gotas[..., None] * 0.85 * et) + \
                (SANGRE_OSC + (SANGRE - SANGRE_OSC) * gotas[..., None]) * gotas[..., None] * 0.85 * et

        return np.clip(img, 0, 255).astype(np.uint8)


if __name__ == "__main__":
    from PIL import Image
    from comun import SALIDA
    cuadros = sorted((SALIDA / "cuadros").glob("*.png"))
    F = np.asarray(Image.open(cuadros[-1]).convert("RGB"))
    fx = FinalSangre(F)
    tiras = [np.asarray(Image.fromarray(fx.cuadro(t)).resize((600, 600))) for t in (0, 0.3, 0.6, 1.0)]
    Image.fromarray(np.hstack(tiras)).save(SALIDA / "final_sangre_prueba.png")
    print("ok")
