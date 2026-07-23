'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const root = __dirname;
const html = fs.readFileSync(path.join(root, 'mytradingbot-dashboard.html'), 'utf8');
const script = fs.readFileSync(path.join(root, 'dashboard.js'), 'utf8');
const dom = new JSDOM(html, {
  url: 'http://localhost/dashboard?demo=1&static=1',
  runScripts: 'outside-only',
  pretendToBeVisual: true
});
const { window } = dom;
window.AbortController = global.AbortController;
window.URL.createObjectURL = () => 'blob:preview';
window.URL.revokeObjectURL = () => {};
if (!window.crypto.randomUUID) window.crypto.randomUUID = () => `test-${Math.random().toString(16).slice(2)}`;
window.HTMLElement.prototype.scrollIntoView = function scrollIntoView() {};
window.scrollTo = function scrollTo() {};
window.HTMLDialogElement.prototype.showModal = function showModal() { this.open = true; this.setAttribute('open', ''); };
window.HTMLDialogElement.prototype.close = function close() { this.open = false; this.removeAttribute('open'); };
window.fetch = async () => { throw new Error('Demo mag geen netwerkdata nodig hebben'); };
window.eval(script);

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const clickView = (view) => {
  const button = window.document.querySelector(`#appNav [data-view="${view}"]`);
  assert(button, `Navigatieknop ${view} ontbreekt`);
  button.click();
};

(async () => {
  await wait(350);
  const { document } = window;

  assert(document.getElementById('loginLayer').classList.contains('hidden'), 'demo moet zonder login openen');
  assert.equal(document.querySelector('#appNav [data-view="today"]').getAttribute('aria-current'), 'page');

  // Positie-eerst: de dagelijkse cockpit moet direct de lopende trade, balans en één volgende stap tonen.
  assert.equal(document.getElementById('focusTitle').textContent, 'Je LONG BTCUSDT loopt');
  assert.equal(document.getElementById('decisionBadge').textContent, 'POSITIE OPEN');
  assert.match(document.getElementById('decisionReason').textContent, /open resultaat/i);
  assert.equal(document.getElementById('focusActionButton').textContent, 'Bekijk je positie');
  assert.match(document.getElementById('headerBalance').textContent, /20\.110|20,110|20.*110/);
  assert.match(document.getElementById('accountOpenPnl').textContent, /37,54|37\.54/);
  assert.match(document.getElementById('positionsArea').textContent, /LONG.*BTCUSDT/);
  assert.match(document.getElementById('positionsArea').textContent, /Pas na TP2/i);
  assert.match(document.getElementById('positionsArea').textContent, /Instap/);
  assert.match(document.getElementById('positionsArea').textContent, /Huidige prijs/);
  assert.match(document.getElementById('positionsArea').textContent, /Stop/);
  assert.match(document.getElementById('positionsArea').textContent, /Doel/);
  assert.match(document.getElementById('positionsArea').textContent, /63\.955|63,955/, 'instap moet uit backendveld entry komen');
  assert.match(document.getElementById('positionsArea').textContent, /64\.210|64,210/, 'huidige prijs moet uit backendveld mark komen');

  // Alle charttechniek is uit het zicht tot de gebruiker die bewust opent.
  const chartPanel = document.getElementById('chartWorkflowPanel');
  const marketMapPanel = document.getElementById('marketMapPanel');
  const technicalPanel = document.getElementById('chartTechPanel');
  assert(chartPanel && marketMapPanel && technicalPanel, 'collapsible chartstructuur ontbreekt');
  assert.equal(chartPanel.open, false, 'Je 4 charts moet standaard dicht staan');
  assert.equal(marketMapPanel.open, false, 'Marktkaart moet standaard dicht staan');
  assert.equal(technicalPanel.open, false, 'Technische details moeten standaard dicht staan');
  assert.match(chartPanel.querySelector('.summary-copy').textContent, /alleen om charts te lezen of controleren/i);

  // Vandaag toont geen dagboek, lessen of beheer.
  assert.equal(document.getElementById('prestaties').hidden, true);
  assert.equal(document.getElementById('learnView').hidden, true);
  assert.equal(document.getElementById('manageView').hidden, true);
  assert.equal(document.getElementById('positionSection').hidden, false);

  // Dagboek is een aparte, rustige pagina en behoudt de geverifieerde tabel/filters.
  clickView('journal');
  await wait(20);
  assert.equal(document.getElementById('prestaties').hidden, false);
  assert.equal(document.getElementById('todaySummary').hidden, true);
  assert.match(document.getElementById('performanceSummaryKpis').textContent, /Totaal resultaat/);
  assert.equal(document.getElementById('performanceDetailsPanel').open, false, 'geavanceerde cijfers moeten standaard dicht staan');
  assert.match(document.getElementById('performanceAdvancedKpis').textContent, /Winstfactor/);
  assert.equal(document.querySelectorAll('#journalTableBody tr').length, 12);
  assert([...document.querySelectorAll('#journalTableBody tr')].every((row) => row.children.length === 9), 'iedere journaalrij moet negen cellen hebben');
  assert(document.querySelectorAll('#journalTableBody .source-badge').length > 0, 'bronbadges ontbreken');
  assert(!/controleren/i.test(document.getElementById('performanceDataQuality').textContent), 'datakwaliteitsbanner is niet gevuld');
  document.getElementById('journalDirectionFilter').value = 'short';
  document.getElementById('journalDirectionFilter').dispatchEvent(new window.Event('change'));
  await wait(10);
  assert([...document.querySelectorAll('#journalTableBody .trade-direction')].every((cell) => cell.textContent === 'SHORT'));
  document.getElementById('resetJournalFilters').click();

  // Leren en Beheer zijn afzonderlijk, met zware onderdelen standaard dicht.
  clickView('learn');
  await wait(10);
  assert.equal(document.getElementById('learnView').hidden, false);
  for (const id of ['knowledgeSourcePanel', 'coachPanel', 'knowledgePanel', 'deepdivesPanel']) {
    assert.equal(document.getElementById(id).open, false, `${id} moet standaard dicht staan`);
  }
  clickView('manage');
  await wait(10);
  assert.equal(document.getElementById('manageView').hidden, false);
  assert.equal(document.getElementById('auditPanel').open, false, 'Systeemaudit moet standaard dicht staan');
  assert.equal(document.getElementById('inviteHistoryPanel').open, false, 'oude uitnodigingen moeten standaard dicht staan');
  assert.equal(document.getElementById('testerHistoryPanel').open, false, 'ingetrokken testers moeten standaard dicht staan');
  assert.match(document.getElementById('manageView').textContent, /Testers en uitnodigingen/);

  // De chartreview blijft technisch intact, maar wordt alleen via Vandaag geopend.
  clickView('today');
  chartPanel.open = true;
  marketMapPanel.open = true;
  document.querySelector('#timeframeTabs [data-timeframe="3M"]').click();
  document.getElementById('reviewDraftButton').click();
  await wait(40);
  assert.equal(document.getElementById('reviewDialog').open, true);
  assert.equal(document.getElementById('reviewTimeframe').value, '3M');
  assert(!document.getElementById('triggerReview').classList.contains('hidden'));
  assert.equal(document.querySelectorAll('#triggerFlagEditor [data-flag]').length, 8);
  assert.match(document.querySelector('#reviewDialog .zones-head + p').textContent, /open orders.*entry\/SL\/TP.*nooit als zone/i);
  document.getElementById('reviewDialog').close();

  // Eindcontrole en foutuitleg zijn in gewone taal aanwezig.
  assert(document.getElementById('reviewCompleteSummary'), 'wizard-eindsamenvatting ontbreekt');
  assert.match(script, /showReviewCompletionSummary/);
  assert.match(script, /Je marktkaart is verouderd/);
  assert.match(script, /Wat je kunt doen/);
  assert(!script.includes('Mechanische poorten'), 'technisch jargon mag niet op Vandaag terugkomen');
  assert.match(script, /entry:63955\.4,mark:64210\.8/,'demo moet exact het echte productie-schema gebruiken');

  assert(!script.includes('.innerHTML'), 'onbetrouwbare data mag niet via innerHTML worden gerenderd');
  assert.match(script, /1D.*4H.*15M.*3M/s, 'vaste MTF-keten moet behouden blijven');
  assert.equal(document.getElementById('footerVersion').textContent, 'UX v8.4.0');
  console.log('test_dashboard.js: v8.4.0 één-focus, tabs, collapsibles en veilige reviewflow geslaagd');
  window.close();
})().catch((error) => {
  console.error(error);
  window.close();
  process.exitCode = 1;
});
