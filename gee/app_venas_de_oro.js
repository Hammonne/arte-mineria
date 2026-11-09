// =====================================================================
//  VENAS DE ORO — app de Earth Engine
//  Minería aurífera en Madre de Dios (Perú) y alrededores, 1985 → hoy.
//
//  Cómo usar: pegar en https://code.earthengine.google.com  →  Run.
//  Para publicar: botón "Apps" (arriba) → NEW APP → elegir el proyecto → PUBLISH.
// =====================================================================

// ---------------- estilo (mismo que scripts/estilo_ee.py) ----------------
var LO = 0.022, HI = 0.20, GAMMA = 0.95;
var PAL_FRIO = ['101c14', '2f4630', '526b48', 'e8c496'];          // bosque verde oliva → crema
var PAL_CALIDO = ['101c14', '8a6438', 'c99a62', 'e8c496'];        // sedimento: durazno-dorado
var ALTO = ee.Image('MERIT/Hydro/v1_0_1').select('hnd').gt(25);  // lomas (atenúa nubes)

var ANIO_MIN = 1985, ANIO_MAX = 2025, ANIO_S2 = 2017;
// zona de trabajo: Madre de Dios + Cusco, Puno, norte de Bolivia, Acre/Rondônia (Brasil).
// Sin este filtro EE intenta combinar todas las imágenes del mundo y la capa no carga.
var CAJA = ee.Geometry.Rectangle([-74.5, -16.0, -66.0, -8.5]);

var LUGARES = [
  {nombre: 'Toda Madre de Dios y alrededores', lon: -70.2, lat: -12.2, zoom: 8},
  {nombre: 'Huepetuhe', lon: -70.508, lat: -12.933, zoom: 12},
  {nombre: 'La Pampa / Interoceánica', lon: -70.008, lat: -12.878, zoom: 12},
  {nombre: 'Río Madre de Dios (Boca Colorado)', lon: -70.425, lat: -12.661, zoom: 12},
  {nombre: 'Río Madre de Dios (Laberinto)', lon: -69.717, lat: -12.654, zoom: 12}
];

// ---------------- colecciones ----------------
function prepLandsat(bandas) {
  return function (img) {
    var ok = img.select('QA_PIXEL').bitwiseAnd(31).eq(0);
    return img.select(bandas, ['R', 'G', 'B']).multiply(0.0000275).add(-0.2)
      .updateMask(ok).copyProperties(img, ['system:time_start']);
  };
}
var B57 = ['SR_B3', 'SR_B2', 'SR_B1'], B89 = ['SR_B4', 'SR_B3', 'SR_B2'];
var LANDSAT = ee.ImageCollection('LANDSAT/LT05/C02/T1_L2').map(prepLandsat(B57))
  .merge(ee.ImageCollection('LANDSAT/LE07/C02/T1_L2').map(prepLandsat(B57)))
  .merge(ee.ImageCollection('LANDSAT/LC08/C02/T1_L2').map(prepLandsat(B89)))
  .merge(ee.ImageCollection('LANDSAT/LC09/C02/T1_L2').map(prepLandsat(B89)));

var CS = ee.ImageCollection('GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED');
var SENTINEL = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').linkCollection(CS, ['cs_cdf'])
  .map(function (i) {
    return i.select(['B4', 'B3', 'B2'], ['R', 'G', 'B']).divide(10000)
      .updateMask(i.select('cs_cdf').gte(0.6)).copyProperties(i, ['system:time_start']);
  });

// mediana de la temporada seca (mayo–octubre); Landsat usa 3 años para tapar huecos y nubes
function compuesto(anio, altaRes, region) {
  var col = altaRes ? SENTINEL : LANDSAT;
  var radio = altaRes ? 0 : 1;
  var a = ee.Number(anio);                      // sirve con año normal o calculado en el servidor (GIF)
  col = col.filter(ee.Filter.calendarRange(5, 10, 'month'))
    .filterDate(ee.Date.fromYMD(a.subtract(radio), 1, 1), ee.Date.fromYMD(a.add(radio + 1), 1, 1));
  if (region) col = col.filterBounds(region);   // necesario para exportar (si no, excede memoria)
  return col.median();
}

function estilo(rgb) {
  var R = rgb.select('R'), G = rgb.select('G'), B = rgb.select('B');
  var lum = R.multiply(0.3).add(G.multiply(0.59)).add(B.multiply(0.11));
  var t = lum.subtract(LO).divide(HI - LO).clamp(0, 1).pow(GAMMA);
  t = t.where(ALTO.and(t.gt(0.45)), 0.45);
  var frio = t.visualize({min: 0, max: 1, palette: PAL_FRIO}).toFloat();
  var calido = t.multiply(1.15).clamp(0, 1).visualize({min: 0, max: 1, palette: PAL_CALIDO}).toFloat();
  // sedimento, tierra removida y pozas son rojizos (R > G); la vegetación es verde
  var calidez = R.subtract(G).divide(R.add(G).add(0.001)).multiply(6).clamp(0, 1);
  var k = calidez.multiply(t.multiply(2.5).clamp(0, 1));
  return frio.multiply(ee.Image(1).subtract(k)).add(calido.multiply(k)).toUint8();
}

function imagenAnio(anio, altaRes, region) {
  return estilo(compuesto(anio, altaRes && anio >= ANIO_S2, region || CAJA));
}

// ---------------- mapa ----------------
var OSCURO = [
  {elementType: 'geometry', stylers: [{color: '#0b120e'}]},
  {elementType: 'labels.text.fill', stylers: [{color: '#8fa59a'}]},
  {elementType: 'labels.text.stroke', stylers: [{color: '#050807'}]},
  {featureType: 'water', stylers: [{color: '#08100c'}]},
  {featureType: 'road', stylers: [{visibility: 'off'}]},
  {featureType: 'poi', stylers: [{visibility: 'off'}]},
  {featureType: 'administrative', elementType: 'geometry.stroke', stylers: [{color: '#3a4a40'}]}
];
var mapa = ui.Map();
mapa.setOptions('Oscuro', {Oscuro: OSCURO});
mapa.setControlVisibility({layerList: false, fullscreenControl: true, drawingToolsControl: false});
mapa.style().set('cursor', 'crosshair');

// límite de Madre de Dios (solo una línea fina; el mapa no se recorta)
var MDD = ee.FeatureCollection('FAO/GAUL/2015/level1').filter(ee.Filter.eq('ADM1_NAME', 'Madre de Dios'));
var LIMITE = ee.Image().byte().paint(MDD, 1, 1).visualize({palette: ['e8c496'], opacity: 0.35});

// ---------------- panel ----------------
var ORO = '#e8c496', TENUE = '#8fa59a', FONDO = '#0b120e';
var panel = ui.Panel({style: {width: '330px', padding: '14px', backgroundColor: FONDO}});
function txt(t, s) {
  var base = {backgroundColor: FONDO, color: TENUE, fontSize: '12px', margin: '2px 0'};
  for (var k in s) base[k] = s[k];
  return ui.Label(t, base);
}
panel.add(txt('Venas de oro', {fontSize: '28px', color: ORO, fontWeight: 'bold', margin: '0 0 2px'}));
panel.add(txt('Minería aurífera en Madre de Dios, Perú. Imágenes satelitales reales, una por año.'));

var etiquetaAnio = txt('', {fontSize: '44px', color: ORO, margin: '14px 0 0'});
var etiquetaFuente = txt('');
panel.add(etiquetaAnio);
panel.add(etiquetaFuente);

var slider = ui.Slider({min: ANIO_MIN, max: ANIO_MAX, value: 2024, step: 1,
                        style: {stretch: 'horizontal', backgroundColor: FONDO}});
panel.add(slider);

var altaRes = ui.Checkbox({label: 'Alta resolución (Sentinel-2, 10 m, desde 2017)', value: true,
                           style: {backgroundColor: FONDO, color: TENUE, fontSize: '12px'}});
panel.add(altaRes);

panel.add(txt('IR A', {margin: '14px 0 4px', fontSize: '11px'}));
LUGARES.forEach(function (l) {
  panel.add(ui.Button({label: l.nombre, style: {stretch: 'horizontal', margin: '2px 0'},
                       onClick: function () { mapa.setCenter(l.lon, l.lat, l.zoom); }}));
});

panel.add(txt('EXPORTAR ESTA VISTA', {margin: '16px 0 4px', fontSize: '11px'}));
var salida = ui.Panel({style: {backgroundColor: FONDO}});
panel.add(ui.Button({label: '⬇ Imagen del año (PNG)', style: {stretch: 'horizontal'},
                     onClick: exportarImagen}));
panel.add(ui.Button({label: '▶ Animación 1985 → hoy (GIF)', style: {stretch: 'horizontal'},
                     onClick: exportarGif}));
panel.add(salida);

panel.add(txt('Dorado = ríos cargados de sedimento, tierra removida y pozas mineras. ' +
              'Verde = bosque. Línea fina = límite de Madre de Dios.', {margin: '14px 0 2px'}));
panel.add(txt('Datos: Landsat 5/7/8/9 (USGS/NASA), Sentinel-2 (ESA/Copernicus), ' +
              'Cloud Score+, MERIT Hydro, FAO GAUL.', {fontSize: '10px'}));

// ---------------- lógica ----------------
var capaActual = null;
function actualizar() {
  var anio = slider.getValue();
  var s2 = altaRes.getValue() && anio >= ANIO_S2;
  etiquetaAnio.setValue(String(anio));
  etiquetaFuente.setValue(s2 ? 'Sentinel-2 · 10 m por píxel' : 'Landsat · 30 m por píxel (3 años combinados)');
  var nueva = ui.Map.Layer(imagenAnio(anio, altaRes.getValue()), {min: 0, max: 255}, String(anio));
  // la capa nueva se agrega ENCIMA; la anterior se quita después (sin parpadeo a gris)
  mapa.layers().insert(mapa.layers().length() - 1, nueva);
  var vieja = capaActual;
  capaActual = nueva;
  if (vieja) ui.util.setTimeout(function () { mapa.layers().remove(vieja); }, 6000);
}
mapa.layers().add(ui.Map.Layer(LIMITE, {}, 'límite'));
slider.onChange(ui.util.debounce(actualizar, 400));
altaRes.onChange(actualizar);

function vista() { return ee.Geometry.Rectangle(mapa.getBounds(), null, false); }

function exportarImagen() {
  var anio = slider.getValue();
  var url = imagenAnio(anio, altaRes.getValue(), vista())
    .getThumbURL({region: vista(), dimensions: 2048, format: 'png'});
  salida.clear();
  salida.add(ui.Label('Abrir imagen ' + anio + ' (2048 px)', {backgroundColor: FONDO, color: ORO}, url));
}

function exportarGif() {
  salida.clear();
  if (mapa.getZoom() < 9) {
    salida.add(txt('Acércate un poco más (zoom ≥ 9) para generar la animación.', {color: ORO}));
    return;
  }
  var region = vista();
  var anios = ee.List.sequence(1986, ANIO_MAX);
  var cuadros = ee.ImageCollection(anios.map(function (a) {
    return imagenAnio(ee.Number(a).toInt(), false, region).set('anio', a);
  }));
  var url = cuadros.getVideoThumbURL({region: region, dimensions: 720, framesPerSecond: 4});
  salida.add(ui.Label('Abrir animación (GIF)', {backgroundColor: FONDO, color: ORO}, url));
  salida.add(txt('Puede tardar 1–2 minutos en generarse.'));
}

// ---------------- armar ----------------
ui.root.clear();
ui.root.add(ui.SplitPanel(panel, mapa));
mapa.setCenter(LUGARES[0].lon, LUGARES[0].lat, LUGARES[0].zoom);
actualizar();
