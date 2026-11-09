"""
04_video.py — video 1985 → fin de la simulación, estilo de las imágenes de referencia:
bosque verde-azulado oscuro, minería y ríos contaminados en dorado/crema, viñeta.

  1985–2025: imagen satelital real (Landsat) de cada año + caminos de contaminación
  2025→     : base Landsat 2025 + minería simulada + caminos de contaminación

Salidas en salida/:
  madre_de_dios.mp4       el video
  cuadros/AAAA.png        un cuadro por año (alta calidad)

Uso:
  python 04_video.py                       # 0.5 s por año
  python 04_video.py --seg-por-anio 1      # más lento
  python 04_video.py --lado 1080           # resolución (cuadrado)
  python 04_video.py --seg-sangre 0        # sin el final rojo
"""
import argparse
import subprocess

import numpy as np
import rasterio
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

from comun import DATOS, SALIDA, contaminacion, estaticos, leer

ap = argparse.ArgumentParser()
ap.add_argument("--lado", type=int, default=1440)
ap.add_argument("--fps", type=int, default=24)
ap.add_argument("--seg-por-anio", type=float, default=0.5)
ap.add_argument("--pausa-final", type=float, default=1.5)
ap.add_argument("--seg-sangre", type=float, default=5.0, help="duración del final rojo (0 = sin final)")
args = ap.parse_args()

S = estaticos()
REG = S["region"]
ANIO_MIN = leer(SALIDA / "anio_mineria.tif")
ULTIMO_REAL_LS = 2025
ULTIMO_REAL_MIN = 2024
FIN = int(ANIO_MIN.max())
H0, W0 = REG.shape

# ---------------- geometría de salida ----------------
escala = (args.lado * 0.86) / max(H0, W0)
H1, W1 = int(H0 * escala), int(W0 * escala)
OY, OX = (args.lado - H1) // 2 + int(args.lado * 0.03), (args.lado - W1) // 2


def achicar(a, maximo=False):
    """Reduce un raster a la resolución del video. `maximo` conserva líneas finas (ríos)."""
    a = a.astype(np.float32)
    if maximo:
        a = ndimage.maximum_filter(a, size=max(1, int(round(1 / escala))))
    return np.asarray(Image.fromarray(a).resize((W1, H1), Image.BILINEAR))


REG1 = achicar(REG) > 0.5
ALTO1 = achicar(S["hnd"]) > 25   # > 25 m sobre el río más cercano

# ---------------- paleta (sacada de las referencias) ----------------
OSCURO = np.array([6, 18, 17], np.float32)       # fondo / sombras del bosque
BOSQUE = np.array([40, 86, 72], np.float32)      # bosque iluminado
CREMA = np.array([238, 214, 160], np.float32)    # minería / sedimento
ORO = np.array([214, 160, 70], np.float32)       # brillo de los ríos contaminados


def gradiente(t, colores):
    t = np.clip(t, 0, 1)[..., None]
    n = len(colores) - 1
    i = np.minimum((t * n).astype(int), n - 1)
    f = t * n - i
    c = np.stack(colores)
    return c[i[..., 0]] * (1 - f) + c[i[..., 0] + 1] * f


def base_landsat(anio):
    with rasterio.open(DATOS / "landsat" / f"{anio}.tif") as f:
        rgb = f.read().astype(np.float32) / 255
    lum = 0.3 * rgb[0] + 0.59 * rgb[1] + 0.11 * rgb[2]
    lum = np.stack([achicar(lum)])[0]
    # normaliza por año (los satélites cambian de calibración) usando el bosque
    v = lum[REG1]
    lo, hi = np.percentile(v, 2), np.percentile(v, 99.7)
    t = np.clip((lum - lo) / max(hi - lo, 1e-3), 0, 1) ** 1.15
    # nubes residuales en las lomas/montañas: se atenúan lejos de las zonas bajas
    t = np.where(ALTO1, np.minimum(t, 0.45), t)
    return gradiente(t, [OSCURO, BOSQUE, BOSQUE * 1.4, CREMA])


VINETA = None


def vineta():
    global VINETA
    if VINETA is None:
        yy, xx = np.mgrid[0:args.lado, 0:args.lado] / args.lado - 0.5
        VINETA = (1 - 0.75 * np.clip(np.sqrt(xx ** 2 + yy ** 2) * 1.5, 0, 1) ** 2)[..., None]
    return VINETA


try:
    FUENTE = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", int(args.lado * 0.055))
    FUENTE_C = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", int(args.lado * 0.018))
except OSError:
    FUENTE = FUENTE_C = ImageFont.load_default()

GRANO = np.random.default_rng(0).normal(0, 1, (args.lado, args.lado, 1)).astype(np.float32)


def cuadro(anio):
    simulado = anio > ULTIMO_REAL_MIN
    base = base_landsat(min(anio, ULTIMO_REAL_LS))
    mineria = (ANIO_MIN > 0) & (ANIO_MIN <= anio)

    # minería simulada: se pinta crema con textura (la real ya se ve en Landsat)
    img = base.copy()
    if simulado:
        nueva = achicar(mineria & (ANIO_MIN > ULTIMO_REAL_MIN))
        # textura de pozas: mezcla de tierra removida (crema apagado) y agua oscura
        ruido = ndimage.gaussian_filter(np.random.default_rng(7).random((H1, W1)), 1.2)
        ruido = (ruido - ruido.mean()) / ruido.std()
        tierra = gradiente(np.clip(0.55 + 0.25 * ruido, 0, 1),
                           [OSCURO, BOSQUE * 0.8, CREMA * 0.75, CREMA])
        img = img * (1 - nueva[..., None]) + tierra * nueva[..., None]

    # caminos de contaminación: brillo dorado río abajo
    c = contaminacion(mineria)
    v = np.clip(np.log1p(c) / np.log1p(20000), 0, 1)
    v[mineria & ~S["rio"]] = 0          # brilla el camino del agua, no la mina misma
    v = achicar(v, maximo=True)
    brillo = ndimage.gaussian_filter(v, 2.5) * 1.6 + v
    img = img + ORO * np.clip(brillo, 0, 1.2)[..., None] * 0.9

    img[~REG1] = 0
    lienzo = np.zeros((args.lado, args.lado, 3), np.float32)
    lienzo[OY:OY + H1, OX:OX + W1] = img
    lienzo = lienzo * vineta() + GRANO * 4
    im = Image.fromarray(np.clip(lienzo, 0, 255).astype(np.uint8))

    d = ImageDraw.Draw(im)
    m = int(args.lado * 0.045)
    d.text((m, m), str(anio), font=FUENTE, fill=(238, 214, 160))
    km2 = mineria[REG].sum() * 0.0144
    sub = "proyección (si sigue la tendencia)" if simulado else "datos satelitales"
    d.text((m, m + int(args.lado * 0.07)), f"{sub}  ·  minería {km2:,.0f} km²".replace(",", "."),
           font=FUENTE_C, fill=(150, 170, 160))
    d.text((m, args.lado - m - int(args.lado * 0.02)), "MADRE DE DIOS, PERÚ",
           font=FUENTE_C, fill=(110, 130, 120))
    return np.asarray(im)


if __name__ == "__main__":
    carpeta = SALIDA / "cuadros"
    carpeta.mkdir(parents=True, exist_ok=True)
    salida = SALIDA / "madre_de_dios.mp4"
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{args.lado}x{args.lado}", "-r", str(args.fps), "-i", "-",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "slow", str(salida)],
        stdin=subprocess.PIPE)
    n = max(1, int(args.fps * args.seg_por_anio))
    previo = None
    for anio in range(1985, FIN + 1):
        actual = cuadro(anio)
        Image.fromarray(actual).save(carpeta / f"{anio}.png")
        if previo is None:
            previo = actual
        for k in range(n):  # fundido suave entre años
            a = (k + 1) / n
            ff.stdin.write((previo * (1 - a) + actual * a).astype(np.uint8).tobytes())
        previo = actual
        print(anio, end=" ", flush=True)
    for _ in range(int(args.fps * args.pausa_final)):
        ff.stdin.write(previo.tobytes())

    # final dramático: las venas se vuelven sangre, se expanden y gotean
    if args.seg_sangre > 0:
        from final_sangre import FinalSangre
        fx = FinalSangre(previo)
        n = int(args.fps * args.seg_sangre)
        for k in range(n):
            f = fx.cuadro((k + 1) / n)
            ff.stdin.write(f.tobytes())
        Image.fromarray(f).save(carpeta / "final_sangre.png")
        for _ in range(int(args.fps * 2)):                 # pausa en rojo
            ff.stdin.write(f.tobytes())
        n = int(args.fps * 2)
        for k in range(n):                                 # fundido a negro
            ff.stdin.write((f * (1 - (k + 1) / n)).astype(np.uint8).tobytes())
    ff.stdin.close()
    ff.wait()
    print(f"\nListo: {salida}")
