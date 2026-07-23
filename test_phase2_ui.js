'use strict';
const fs = require('fs');
const path = require('path');
const assert = require('assert');
const root = __dirname;
const css = fs.readFileSync(path.join(root, 'dashboard.css'), 'utf8');
const html = fs.readFileSync(path.join(root, 'mytradingbot-dashboard.html'), 'utf8');
const main = fs.readFileSync(path.join(root, 'main.py'), 'utf8');
const js = fs.readFileSync(path.join(root, 'dashboard.js'), 'utf8');
const fonts = [
  ['fraunces-500.woff2', 500], ['fraunces-600.woff2', 600],
  ['manrope-400.woff2', 400], ['manrope-600.woff2', 600],
  ['manrope-700.woff2', 700], ['manrope-800.woff2', 800],
];
for (const [name] of fonts) {
  const p = path.join(root, name);
  assert.ok(fs.existsSync(p), `${name} ontbreekt`);
  const magic = fs.readFileSync(p).subarray(0, 4).toString('ascii');
  assert.strictEqual(magic, 'wOF2', `${name} is geen geldige WOFF2`);
  assert.ok(css.includes(`/assets/${name}`), `${name} is niet CSP-veilig gekoppeld`);
}
assert.strictEqual((css.match(/@font-face/g) || []).length >= 6, true, 'zes font-face-regels ontbreken');
assert.ok(css.includes('--display:"Fraunces",Georgia,serif'), 'Fraunces display-stack ontbreekt');
assert.ok(css.includes('--sans:"Manrope"'), 'Manrope body-stack ontbreekt');
assert.ok(css.includes('font-family:var(--display)'), 'displayfont wordt niet toegepast');
assert.ok(css.includes('box-shadow:0 8px 26px var(--gold-glow)'), 'premium gouden knopgloed ontbreekt');
assert.ok(css.includes('.layer-card.active') && css.includes('var(--gold-glow)'), 'actieve-laag-gloed ontbreekt');
assert.ok(!/(fonts\.googleapis|fonts\.gstatic|https?:\/\/.*\.(?:woff2?|ttf|otf))/i.test(css), 'externe fontrequest gevonden');
assert.ok(!/(fonts\.googleapis|fonts\.gstatic)/i.test(html + main), 'CSP-onveilige fontbron gevonden');
for (const label of ['Rol', 'Prijsniveau / zone', 'Reden', 'Zekerheid']) {
  assert.ok(js.includes(label), `${label} ontbreekt in de echte vision-renderer`);
}
assert.ok(js.includes("create('dl', 'vision-zone-grid')"), 'vier-velden vision-grid ontbreekt');
assert.ok(js.includes("create('details', 'vision-technical-details')"), 'technische vision-uitklap ontbreekt');
assert.ok(html.includes('button primary'), 'primaire kernknop ontbreekt');
assert.ok(css.includes('@media(max-width:680px)'), 'mobiele 680px-regel ontbreekt');
assert.ok(css.includes('@media(prefers-reduced-motion:reduce)'), 'reduced-motion-regel ontbreekt');
function luminance(hex) {
  const rgb = hex.replace('#','').match(/../g).map(x => parseInt(x,16)/255)
    .map(c => c <= .04045 ? c/12.92 : Math.pow((c+.055)/1.055, 2.4));
  return .2126*rgb[0] + .7152*rgb[1] + .0722*rgb[2];
}
function contrast(a,b) { const x=luminance(a), y=luminance(b); return (Math.max(x,y)+.05)/(Math.min(x,y)+.05); }
assert.ok(contrast('#f4f0e6','#111a2e') >= 4.5, 'hoofdtekst haalt AA niet');
assert.ok(contrast('#9aa6bd','#111a2e') >= 4.5, 'muted tekst haalt AA niet');
assert.ok(contrast('#76839a','#111a2e') >= 4.5, 'kleine labels halen AA niet');
console.log('PASS phase 1d UX 8.3.0: fonts, CSP, premium tokens, structure, accessibility');
