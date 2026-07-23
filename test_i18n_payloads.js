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
window.fetch = async () => { throw new Error('real-payload i18n test must not use network'); };
window.eval(script);

const wait = (ms=50) => new Promise((resolve) => setTimeout(resolve, ms));

(async () => {
  await wait(350);
  const t = window.__MYTRADINGBOT_TEST__;
  assert(t, 'demo test seam missing');
  t.setLanguage('en', { persist:false });

  assert.equal(t.sourceLabel({source_class:'BYBIT_VERIFIED',origin_class:'MANUAL_OPEN'}), 'BYBIT VERIFIED · MANUALLY OPENED');
  assert.equal(t.sourceLabel({source_class:'MANUAL_OPEN'}), 'MANUALLY OPENED');
  assert.equal(t.sourceLabel({source_class:'LEGACY'}), 'LEGACY IMPORT');
  assert.equal(t.consistencyLabel('mismatch'), 'DIRECTION UNVERIFIED');
  assert.equal(t.consistencyReason('mismatch'), 'Result, direction and price movement require manual review.');
  assert.equal(t.processLabel({process_status:'unreviewed'}), 'NOT REVIEWED');
  assert.equal(t.processLabel({process_status:'reviewed'}), 'REVIEWED');
  assert.equal(t.percentageMetricsReason({snapshot_count:4}, 6), 'Insufficient historical equity data — 4 of 6 records.');
  assert.equal(t.percentageMetricsReason({snapshot_coverage_pct:50}, 6), 'Insufficient historical equity data — 3 of 6 records.');
  assert.equal(t.sampleLabelForCount(6), 'INSUFFICIENT TRADES');
  assert.equal(t.reviewReasonLabel('trend veranderde van down naar range'), 'trend changed from down to range');
  assert.equal(t.reviewReasonLabel('menselijke controle is ouder dan 12 uur'), 'human review is older than 12 hours');

  const base = t.demoOverview();
  base.latest = {
    ...base.latest,
    execution_gate:{
      status:'ENTRY_READY', orderable:true,
      reason:'3m lokale kanteling bevestigd bij 4H steun. Het orderticket mag veilig worden voorbereid; de eindklik blijft handmatig.'
    },
    setup:{
      ...base.latest.setup,
      trigger:{type:'local_reversal',direction:'long'},
      parent_zone:{source_timeframe:'4H',role:'support'}
    }
  };
  t.setOverview(base);
  assert.equal(t.executionReason(base.latest), '3M local reversal confirmed at 4H support. The order ticket may be prepared safely; the final click remains manual.');

  for (const [status, expected] of [
    ['WAIT_3M_TRIGGER', 'The 3M chart is moving, but there is no concrete local signal that needs your review yet.'],
    ['WAIT_3M_TURN', 'Price is at an HTF zone. There is no confirmed local 3M reversal or retest yet.'],
    ['TICKET_INPUT_REQUIRED', 'The 3M signal is confirmed, but no valid entry zone has been selected for this ticket.'],
    ['SETUP_INVALIDATED', 'The relevant HTF zone has been invalidated. A local 3M reversal does not restore that thesis.'],
  ]) {
    const latest = {...base.latest, execution_gate:{status,orderable:false,reason:'Rauwe Nederlandse motorzin die niet zichtbaar mag worden.'}};
    assert.equal(t.executionReason(latest), expected, status);
  }

  const candidate = {...base.latest, execution_gate:{status:'ENTRY_CANDIDATE',orderable:false,reason:'De lokale 3M-kanteling is gevonden, maar eerst oplossen: Technische ticketstop geldig.',checks:[{key:'m3_stop',label:'Technische ticketstop geldig',ok:false}]}};
  assert.equal(t.executionReason(candidate), 'The local 3M reversal was detected, but first resolve: technical ticket stop.');
  const noTrade = {...base.latest, execution_gate:{status:'NO_TRADE',orderable:false,reason:'R:R-poort geblokkeerd: maximaal 2.25R, minimaal 3.00R vereist.',checks:[{key:'rr',label:'R:R ≥ 1:3',ok:false,detail:'max 2.25R'}]}};
  assert.equal(t.executionReason(noTrade), 'R:R gate blocked: maximum 2.25R, minimum 3.00R required.');

  const payload = t.demoOverview();
  payload.principal = {...payload.principal, role:'owner', mode:'owner', display_name:'Eigenaar'};
  payload.account.positions = [];
  payload.journal.stats = {...payload.journal.stats, trades:6, snapshot_count:4, snapshot_coverage_pct:66.67, pnl_basis:'MIXED_SOURCES', source_verified:2, unknown_source_count:1};
  payload.journal.trades = [{
    id:'closed-pnl-1',symbol:'BTCUSDT',direction:'long',entry:64000,exit:63950,pnl:-22.81,pnl_pct:-0.112,
    source_class:'BYBIT_VERIFIED',origin_class:'MANUAL_OPEN',direction_consistency:'mismatch',process_status:'unreviewed',closed_at:new Date().toISOString()
  }];
  payload.activity = [{type:'chart_synced',timeframe:'3M',note:'5 zone(s) gelezen · 62% zekerheid',at:new Date().toISOString()}];
  t.setOverview(payload);
  t.switchView('journal', {persist:false});
  await wait(40);
  const text = window.document.body.textContent.replace(/\s+/g,' ');
  assert.match(text, /BYBIT VERIFIED · MANUALLY OPENED/);
  assert.match(text, /DIRECTION UNVERIFIED/);
  assert.match(text, /NOT REVIEWED/);
  assert.match(text, /4 of 6 records with historical account value/);
  assert.match(text, /INSUFFICIENT TRADES/);
  assert.doesNotMatch(text, /BYBIT GEVERIFIEERD|HANDMATIG GEOPEND|RICHTING ONGEVERIFIEERD|NIET BEOORDEELD|ONVOLDOENDE TRADES|Onvoldoende historische equitydata/);
  t.switchView('manage', {persist:false});
  await wait(20);
  const manage = window.document.body.textContent.replace(/\s+/g,' ');
  assert.match(manage, /Live owner/);
  assert.match(window.document.getElementById('inviteLabel').getAttribute('placeholder'), /For example: brother Mark/);

  console.log('test_i18n_payloads.js: real server codes and real motor payloads render without Dutch interface labels');
  window.close();
})().catch((error) => { console.error(error); window.close(); process.exitCode=1; });
