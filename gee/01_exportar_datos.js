// =====================================================================
// 01_exportar_datos.js  —  pegar en https://code.earthengine.google.com
// Exporta a Google Drive (carpeta "mineria_mdd"):
//   1. mineria_mdd.tif  -> 1 banda por año: 1 = minería, 0 = no (MapBiomas Perú)
//   2. landsat_rgb.tif  -> RGB por año 1985–2025 (para el video)
//   3. direccion_agua.tif -> hacia dónde corre el agua (HydroSHEDS)
// Todo en la misma grilla (UTM 19S, 120 m) para que encaje píxel a píxel.
// =====================================================================

var ANIO_INI = 1985;
var ANIO_FIN = 2025;
var ESCALA = 120;            // metros por píxel (bajar a 90/60 si quieres más detalle)
var CRS = 'EPSG:32719';      // UTM zona 19 Sur
var CARPETA = 'mineria_mdd';

// ---------- Región: Madre de Dios ----------
var region = ee.FeatureCollection('FAO/GAUL/2015/level1')
  .filter(ee.Filter.eq('ADM1_NAME', 'Madre de Dios'));
var geom = region.geometry();
var caja = geom.bounds();
Map.centerObject(region, 7);
Map.addLayer(region.style({color: 'yellow', fillColor: '00000000'}), {}, 'Madre de Dios');

// ---------- 1. Minería (MapBiomas Perú) ----------
// OJO: revisa en la consola (derecha) que el asset cargue y qué años trae.
// Si da error, busca "MapBiomas Peru" en la barra de búsqueda de arriba
// y reemplaza la ruta por la colección más reciente.
var MAPBIOMAS = 'projects/mapbiomas-public/assets/peru/collection3/mapbiomas_peru_collection3_integration_v1';
var CLASE_MINERIA = 30;   // en la leyenda de MapBiomas, 30 = Minería

var mb = ee.Image(MAPBIOMAS);
print('Bandas MapBiomas (años disponibles):', mb.bandNames());
var mineria = mb.eq(CLASE_MINERIA).unmask(0).toByte().clip(geom);

Map.addLayer(mineria.select(-1).selfMask(), {palette: ['ffd27f']}, 'Minería (último año)');

// ---------- 2. Landsat RGB por año ----------
var NOMBRES = ['R', 'G', 'B', 'NIR', 'SWIR1'];

function preparar(bandas) {
  return function (img) {
    var qa = img.select('QA_PIXEL');
    // bits 0-4: relleno, nube dilatada, cirros, nube, sombra
    var limpio = qa.bitwiseAnd(31).eq(0);
    return img.select(bandas, NOMBRES)
      .multiply(0.0000275).add(-0.2)
      .updateMask(limpio)
      .copyProperties(img, ['system:time_start']);
  };
}
var B_L57 = ['SR_B3', 'SR_B2', 'SR_B1', 'SR_B4', 'SR_B5'];
var B_L89 = ['SR_B4', 'SR_B3', 'SR_B2', 'SR_B5', 'SR_B6'];

var landsat = ee.ImageCollection('LANDSAT/LT05/C02/T1_L2').map(preparar(B_L57))
  .merge(ee.ImageCollection('LANDSAT/LE07/C02/T1_L2').map(preparar(B_L57)))
  .merge(ee.ImageCollection('LANDSAT/LC08/C02/T1_L2').map(preparar(B_L89)))
  .merge(ee.ImageCollection('LANDSAT/LC09/C02/T1_L2').map(preparar(B_L89)))
  .filterBounds(geom);

// imagen vacía para años sin datos (evita errores)
var vacia = ee.Image.constant([0, 0, 0, 0, 0]).rename(NOMBRES).updateMask(0);

var rgb = null;
for (var y = ANIO_INI; y <= ANIO_FIN; y++) {
  // temporada seca (mayo–octubre) = menos nubes
  var col = landsat.filterDate(y + '-05-01', y + '-10-31')
    .merge(ee.ImageCollection([vacia]));
  var comp = col.median().select(['R', 'G', 'B'])
    .unitScale(0, 0.3).clamp(0, 1).multiply(255).toByte()
    .rename([y + '_R', y + '_G', y + '_B']);
  rgb = rgb === null ? comp : rgb.addBands(comp);
}
rgb = rgb.clip(geom);

Map.addLayer(rgb.select(['2000_R', '2000_G', '2000_B']), {min: 0, max: 255}, 'Landsat 2000');
Map.addLayer(rgb.select([ANIO_FIN + '_R', ANIO_FIN + '_G', ANIO_FIN + '_B']), {min: 0, max: 255}, 'Landsat ' + ANIO_FIN);

// ---------- 3. Dirección del agua (HydroSHEDS) ----------
var direccion = ee.Image('WWF/HydroSHEDS/03DIR').select('b1').toByte().clip(geom);

// ---------- Exportar a Google Drive ----------
function exportar(img, nombre) {
  Export.image.toDrive({
    image: img,
    description: nombre,
    folder: CARPETA,
    fileNamePrefix: nombre,
    region: caja,
    scale: ESCALA,
    crs: CRS,
    maxPixels: 1e13
  });
}
exportar(mineria, 'mineria_mdd');
exportar(rgb, 'landsat_rgb');
exportar(direccion, 'direccion_agua');

print('Listo. Ve a la pestaña "Tasks" (derecha) y dale RUN a las 3 tareas.');
