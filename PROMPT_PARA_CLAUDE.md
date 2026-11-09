# Instrucciones para Claude: proyecto "Venas de oro"

Copia y pega todo esto al empezar una conversación nueva con Claude, en esta carpeta.

---

## Quién soy y cómo trabajar conmigo

- Háblame en español, casual y **simple**. Nada de explicaciones largas ni técnicas.
- **Muéstrame resultados visuales pronto** (capturas, imágenes) antes de construir cosas grandes.
  Si algo va a tardar más de 15 minutos, primero muéstrame una prueba chica y espera mi visto bueno.
- Si no entiendo algo, explícalo con un ejemplo o una imagen, no con más texto.
- No hagas `git commit` ni `git push`: dame los comandos y yo los corro.

## Lo que quiero (el objetivo real)

Un **visor interactivo tipo Google Earth** de la minería de oro en **Madre de Dios (Perú)**, donde pueda:

1. **Moverme y hacer zoom libremente** por Madre de Dios **y las regiones vecinas**
   (Cusco, Puno, norte de Bolivia, Acre en Brasil). **Nada recortado** al límite de Madre de Dios:
   quiero ver cómo afecta a los vecinos y hacia dónde bajan los ríos.
2. Que **al hacer zoom la imagen gane detalle de verdad**, como en Google Earth
   (no imágenes fijas que se pixelean).
3. Una **línea de tiempo 1985 → hoy** para ver cómo crece la minería, **sin parpadeos ni cuadros negros**,
   y que cargue **rápido**.
4. Acceso directo a estas zonas (son las de mis imágenes de referencia):
   - Huepetuhe (-12.933, -70.508)
   - La Pampa / Interoceánica (-12.878, -70.008)
   - Río Madre de Dios, Boca Colorado (-12.661, -70.425)
   - Río Madre de Dios, Laberinto (-12.654, -69.717)
5. **Estilo visual parecido a mis imágenes de referencia** (`Style Made Simple-2..5.png`, en esta carpeta):
   bosque verde oliva oscuro, ríos con sedimento y cicatrices mineras en dorado/durazno.
   **El cerebro de las referencias NO va.**
6. Extra, al final: una **proyección al futuro** de cómo seguiría la contaminación por los ríos
   y un **final dramático en rojo sangre**.

## Lo que ya existe (no lo rehagas sin preguntarme)

- Entorno conda `mineria` (Python 3.11, earthengine-api, rasterio, scikit-learn, scikit-image, ffmpeg).
- **Google Earth Engine** funcionando con la cuenta jimenag0401@gmail.com,
  proyecto **`mineria-mmd-514207`** (ya autenticado; `earthengine authenticate` funciona).
- `datos/`: Madre de Dios a 120 m (Landsat y MapBiomas 1985–2025, MERIT Hydro) y 4 zonas a 30 m.
- `scripts/01–04`: descarga, modelo de expansión minera (validado 2014–2024), simulación al futuro
  (BFS/Dijkstra) y video → `salida/madre_de_dios.mp4` (con final en sangre).
- `scripts/estilo_ee.py`: el **estilo calculado en Earth Engine** (paleta verde oliva + dorado,
  rango de brillo fijo). Es lo que más se acercó a las referencias.
- `scripts/07_precalcular_ee.py`: guarda la imagen con estilo de cada año como **asset** en Earth Engine
  (`projects/mineria-mmd-514207/assets/venas_landsat/<año>`). Ya existen 1985, 1986 y 2010;
  el resto se canceló. Cada año tarda ~6 min y las imágenes precalculadas cargan en ~0,5 s por cuadrito.
- `web_ee/`: visor local (Leaflet + teselas de Earth Engine). `gee/app_venas_de_oro.js`: la misma idea
  como app del Code Editor de Earth Engine.
- `web/`: visor viejo con imágenes fijas (descartado: se pixelaba y estaba recortado).

## Lo que salió mal (evítalo)

- **Imágenes fijas por año** (video y `web/`): al hacer zoom se ven pixeladas → **malo**.
- **Recortar a Madre de Dios**: se ve feo y oculta a los vecinos → **no recortar**.
- **Calcular las imágenes en vivo** en Earth Engine (mediana de cientos de fotos por cuadrito):
  3–14 s por cuadrito → se cuelga y aparecen cuadros negros → **precalcular** (assets) o usar otra fuente.
- **Ajustar el brillo por año**: cada año se ve distinto → parpadea → usar un **rango fijo**.
- **Fundidos mal hechos** entre años: se veía el fondo → la capa nueva va encima y la vieja se quita después.
- Sin `filterBounds`, Earth Engine combina imágenes de todo el mundo y se cuelga o excede la memoria.
- Sentinel-2 con 3 años de mediana excede la memoria de Earth Engine: usa 1 año.
- Yo esperaba algo con la nitidez de Google Earth. **Avísame claramente qué nitidez es posible**
  con datos gratuitos (Landsat 30 m desde 1985, Sentinel-2 10 m desde 2017, ¿Planet NICFI ~5 m?)
  y muéstrame un ejemplo de cerca **antes** de construir todo.

## Lo que te pido ahora

1. Muéstrame **una sola zona** (La Pampa) de cerca en 2 o 3 años, con la mejor nitidez posible y mi estilo,
   y dime honestamente qué tan cerca de Google Earth se puede llegar.
2. Si me gusta, arma el visor completo (rápido, sin recortes, sin parpadeo) y **pruébalo tú mismo
   con capturas** antes de decirme que está listo.
3. Después, la proyección al futuro y el final en sangre.
