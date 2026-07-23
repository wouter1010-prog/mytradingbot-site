'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const root = __dirname;
const html = fs.readFileSync(path.join(root, 'mytradingbot-dashboard.html'), 'utf8');
const script = fs.readFileSync(path.join(root, 'dashboard.js'), 'utf8');
const dom = new JSDOM(html, { url:'http://localhost/dashboard?demo=1&static=1', runScripts:'outside-only', pretendToBeVisual:true });
const { window } = dom;
window.AbortController = global.AbortController;
window.URL.createObjectURL = () => 'blob:preview';
window.URL.revokeObjectURL = () => {};
window.HTMLElement.prototype.scrollIntoView = function() {};
window.scrollTo = function() {};
window.HTMLDialogElement.prototype.showModal = function() { this.open=true; this.setAttribute('open',''); };
window.HTMLDialogElement.prototype.close = function() { this.open=false; this.removeAttribute('open'); };
window.fetch = async () => { throw new Error('demo must not use network'); };
window.eval(script);

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
(async () => {
  await wait(300);
  const d = window.document;
  d.querySelector('[data-language="en"]').click();
  await wait(120);
  assert.equal(d.documentElement.lang, 'en');
  assert.equal(d.querySelector('[data-view="today"] span').textContent, 'Today');
  assert.equal(d.querySelector('[data-view="journal"] span').textContent, 'Journal');
  assert.match(d.body.textContent, /Open position|No position/);
  assert.match(d.body.textContent, /Your account/);
  const visibleText=d.body.textContent.replace(/\s+/g,' ').trim();
  const residual=[
    'Vandaag','Dagboek','Beheer','Je rekening','Jouw rekening','Lopende positie','Openen','Verversen','Uitloggen',
    'Controleer','grafiek','Geen ','Nodig een tester uit','gelezen','gecontroleerd','ongewijzigd','Dalend','Stijgend',
    'Zijwaarts','onbekend','Herkomst','Bron:','Laatste bron','Winstfactor','verliesreeks','regels','lessen verwerkt',
    'werkruimte actief','rekeningwaarde','huidige prijs','instap','positie in winst','Dagtrade','opbouw','signaal'
  ];
  for(const word of residual) assert(!visibleText.toLowerCase().includes(word.toLowerCase()), `Dutch text remains in English mode: ${word}`);
  assert(d.querySelector('.flag-nl') && d.querySelector('.flag-gb'), 'real CSS flags must be present');
  assert.equal(d.getElementById('footerVersion').textContent, 'UX v8.4.0');
  d.querySelector('[data-language="nl"]').click();
  await wait(120);
  assert.equal(d.documentElement.lang, 'nl');
  assert.equal(d.querySelector('[data-view="today"] span').textContent, 'Vandaag');
  console.log('test_i18n.js: dashboard switches fully between Dutch and English');
  window.close();
})().catch((error) => { console.error(error); window.close(); process.exitCode=1; });
