'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const root = __dirname;
const html = fs.readFileSync(path.join(root, 'mytradingbot-dashboard.html'), 'utf8');
const script = fs.readFileSync(path.join(root, 'dashboard.js'), 'utf8');
const dom = new JSDOM(html, { url:'http://localhost/dashboard?demo=1&static=1&lang=en', runScripts:'outside-only', pretendToBeVisual:true });
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

const wait = (ms=50) => new Promise((resolve) => setTimeout(resolve, ms));
const snapshots = [];
function capture(label) {
  const d = window.document;
  const visibleText = [...d.querySelectorAll('body *')]
    .filter((el) => !el.closest('script,style,template') && !el.hidden && el.getAttribute('aria-hidden') !== 'true')
    .map((el) => el.childElementCount === 0 ? el.textContent : '')
    .join(' ');
  const attrs = [...d.querySelectorAll('[placeholder],[title],[aria-label]')]
    .flatMap((el) => ['placeholder','title','aria-label'].filter((name) => el.hasAttribute(name)).map((name) => el.getAttribute(name)));
  snapshots.push(`${label}\n${visibleText}\n${attrs.join(' ')}`.replace(/\s+/g,' ').trim());
}

const dutchResiduals = [
  /\b(vandaag|dagboek|beheer|leren|verversen|uitloggen|sluiten|minimaliseer|controleer|gecontroleerd|hercontrole|gelezen|grafiek|grafieken|laag|lagen|zone verwijderen|onderkant|confirmaties|reden|opslaan|annuleren|volgende laag|jouw rekening|rekeningwaarde|lopende positie|huidige prijs|open resultaat|instap|uitstap|doel|doelen|richting|stijgend|dalend|zijwaarts|onbekend|wachten|veiligheidsregels|werkruimte|toegang|uitnodiging|bron|bronnen|lessen|fout|mislukt|verlopen|bijgewerkt|ontbreekt|beschikbaar|opbouw|signaal|steun|weerstand|marktkaart|systeemaudit|niet geautoriseerd|probeer opnieuw|wat je kunt doen)\b/i,
  /\b(je|jij|jouw)\s+(marktkaart|rekening|positie|charts?|trade|toegang|cockpit)\b/i,
  /\b(geen|nog geen|alleen|moet|mag|wordt|worden)\s+(trade|chart|grafiek|laag|zone|positie|ticket|controle|review|prijs|toegang|uitnodiging|tester|data|lessen|signaal)/i,
];

(async () => {
  await wait(450);
  const t = window.__MYTRADINGBOT_TEST__;
  assert(t, 'demo test seam missing');
  assert.equal(window.document.documentElement.lang, 'en');

  for (const view of ['today','journal','learn','manage']) {
    t.switchView(view, { persist:false });
    window.document.querySelectorAll('details').forEach((node) => { node.open = true; });
    t.applyLanguage();
    await wait(30);
    capture(`view:${view}`);
  }

  t.switchView('today', { persist:false });
  for (const tf of ['1D','4H','15M','3M']) {
    t.openReview(tf);
    await wait(30);
    capture(`review:${tf}`);
    window.document.getElementById('reviewDialog').close();
  }
  t.showReviewCompletionSummary(); await wait(20); capture('review-complete'); window.document.getElementById('reviewCompleteSummary').close();
  t.openFeedback(); await wait(20); capture('feedback'); window.document.getElementById('feedbackDialog').close();
  t.openTradeInspector(); await wait(20); capture('trade-inspector'); window.document.getElementById('tradeInspector').close();

  const gateCases = [
    ['WAIT_SYNC','Synchroniseer nog: 1D, 4H. Een geslaagde synchronisatie telt direct mee; handmatige controle is pas nodig vóór orderticketvoorbereiding.'],
    ['REVIEW_STACK','Alleen 1D moet opnieuw worden bekeken: de kaart veranderde materieel. Ongewijzigde charts blijven goedgekeurd.'],
    ['WAIT_15M_SETUP','De 15M-chart is ververst, maar er is nog geen concrete opbouw. Je hoeft hem nu niet handmatig te controleren.'],
    ['REVIEW_15M_SETUP','Er is een nieuwe 15M-opbouw gezien. Controleer alleen deze laag: de lokale opbouw veranderde.'],
    ['WAIT_3M_TRIGGER','De 3M-chart beweegt, maar er is nog geen concrete lokale kanteling. Je hoeft hem nu niet handmatig te controleren.'],
    ['REVIEW_3M_TRIGGER','Er is een nieuw lokaal instapsignaal gezien. Controleer alleen de 3M-trigger: het lokale signaal veranderde.'],
    ['WAIT_HTF_LOCATION','3m is gelezen, maar de prijs ligt niet aantoonbaar bij een bevestigde 4H- of 1D-zone.'],
    ['WAIT_PRICE','Geen betrouwbare actuele prijs beschikbaar. De kaart blijft intact, maar het ticket blijft dicht.'],
    ['TICKET_INPUT_REQUIRED','De 3m-trigger is bevestigd, maar het gekozen orderticket verwijst niet naar een bestaande instapzone.'],
    ['NO_TRADE','R:R-poort geblokkeerd: maximaal 2.25R, minimaal 3.00R vereist.'],
    ['ENTRY_CANDIDATE','De lokale 3M-kanteling is gevonden, maar eerst oplossen: Technische ticketstop geldig, 3 tegengestelde zones.'],
    ['ENTRY_READY','3m lokale kanteling bevestigd bij 4H steun. Het orderticket mag veilig worden voorbereid; de eindklik blijft handmatig.'],
  ];
  for (const [status,reason] of gateCases) {
    t.setGate(status, reason); await wait(20); capture(`gate:${status}`);
  }
  t.setStaleState('3M', 5.6); await wait(20); capture('state:stale');
  t.setNoPositionState(); await wait(20); capture('state:no-position');

  for (const error of [
    'Niet geautoriseerd of beta-toegang ingetrokken',
    'Uitnodiging niet gevonden of al ingetrokken',
    'Deze chartversie is niet meer de nieuwste voor dit timeframe. Synchroniseer of open de review opnieuw.',
    'De cockpit reageerde niet op tijd. Probeer opnieuw.',
  ]) { t.setServerError(error); await wait(10); capture('server-error'); }

  const corpus = snapshots.join('\n');
  for (const regex of dutchResiduals) {
    const match = corpus.match(regex);
    if (match) { const i = match.index || 0; console.error(corpus.slice(Math.max(0,i-160), i+220)); }
    assert(!match, `Dutch text remains in English render: ${match && match[0]}`);
  }
  assert.equal(t.translateDutch('Confirmaties'), 'Confirmations');
  assert.equal(t.translateDutch('Reden'), 'Reason');
  assert.match(corpus, /Review only the 3M trigger/);
  assert.match(corpus, /Not authorised or beta access revoked/);
  assert.match(corpus, /R:R gate blocked/);
  assert.match(corpus, /Your market map is outdated/);
  assert.match(corpus, /No open position/);
  console.log(`test_i18n_full.js: ${snapshots.length} rendered states contain no Dutch UI residue`);
  window.close();
  process.exit(0);
})().catch((error) => { console.error(error); window.close(); process.exit(1); });
