# Madre de Dios: venas de oro

Timelapse de la minería aurífera en Madre de Dios (Perú) de 1985 a 2024 con datos satelitales,
y una proyección especulativa de cómo seguiría la contaminación por los ríos si la tendencia continúa.

## Qué hace

1. **Datos reales (1985–2024).** Se usan imágenes Landsat y los mapas anuales de minería de
   MapBiomas Perú, todo a 120 m por píxel.
2. **Caminos de contaminación.** Desde cada zona minera se sigue el agua río abajo (MERIT Hydro).
   Son las "venas" doradas del video.
3. **Proyección (2025 en adelante).** Un modelo aprende de 1990–2023 dónde aparece minería nueva.
   La minería avanza con un BFS con pesos (Dijkstra) desde la minería de 2024, y crece a la tasa
   histórica (9,4 % anual entre 2014 y 2024).
4. **Video** con el estilo visual del proyecto: bosque verde oscuro, venas doradas y final en sangre.

> ⚠️ La proyección es un **escenario especulativo** ("qué pasaría si sigue la tendencia"),
> no un pronóstico. Supone un crecimiento exponencial sin freno, incluso en áreas protegidas.

## Resultados

| | |
|---|---|
| Minería en 1985 | 4 km² |
| Minería en 2024 | 1.276 km² |
| Crecimiento 2014–2024 | 9,4 % anual |
| Mitad de los ríos contaminados (proyección) | ~2061 |
| 95 % de la región minada (proyección) | ~2070 |

Para validar el modelo se entrenó solo hasta 2013 y se simuló 2014–2024 a ciegas: el 82 % de la
minería nueva real cayó a menos de 1 km de la simulada, contra 68 % con píxeles al azar.

## Cómo correrlo

Se necesita una cuenta de [Google Earth Engine](https://code.earthengine.google.com/register)
con un Cloud Project registrado para uso no comercial.

```bash
conda env create -f environment.yml
conda activate mineria
earthengine authenticate
earthengine set_project TU-PROYECTO      # y cambiar PROYECTO en scripts/01_descargar.py

cd scripts
python 01_descargar.py     # ~30 min, baja ~400 MB a datos/
python 02_entrenar.py      # ~2 min, entrena y valida el modelo
python 03_simular.py       # proyección -> salida/anio_mineria.tif, salida/resumen.csv
python 04_video.py         # video -> salida/madre_de_dios.mp4 y salida/cuadros/
```

Opciones útiles:

```bash
python 03_simular.py --tasa 0.05          # otro escenario de crecimiento
python 04_video.py --seg-por-anio 1       # video más lento
python 04_video.py --seg-sangre 0         # sin el final rojo
```

## Estructura

```
scripts/
  01_descargar.py    descarga desde Earth Engine
  comun.py           variables del modelo, BFS/Dijkstra, contaminación río abajo
  02_entrenar.py     modelo + validación 2014–2024
  03_simular.py      proyección al futuro
  04_video.py        render del video
  final_sangre.py    efecto final
gee/
  01_exportar_datos.js   alternativa para el Code Editor de Earth Engine (exporta a Drive)
salida/
  resumen.csv        km² de minería y % de ríos contaminados por año
```

## Fuentes de datos

- **MapBiomas Perú**, Colección 3: clases de cobertura anuales (clase 30 = minería).
- **Landsat 5/7/8/9** Collection 2, nivel 2 (USGS / NASA).
- **MERIT Hydro** (Yamazaki et al., 2019): área de drenaje, dirección del agua y altura sobre el río.
- **SRTM** (elevación), **WDPA** (áreas protegidas), **FAO GAUL** (límite regional).
