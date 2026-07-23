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
window.HTMLDialogElement.prototype.showModal = function() { this.open = true; };
window.HTMLDialogElement.prototype.close = function() { this.open = false; };
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
window.eval(script);

(async()=>{
  await wait(300);
  const api = window.__MYTRADINGBOT_TEST__;
  assert(api, 'test seam ontbreekt');
  const overview = api.demoOverview();
  overview.account.positions = [];
  overview.latest.execution_gate = {status:'ENTRY_READY',orderable:true,reason:'ticket klaar'};
  overview.account_guard = {
    release:'R25B-COMMITMENT-GUARDS',active:false,one_way:true,daily_loss_limit_pct:2,daily_loss_limit_usdt:400,
    buffer_remaining_usdt:300,buffer_remaining_pct:75,buffer_state:'healthy',positions_open:0,max_positions:1,
    cooldown_active:false,cooldown_seconds_remaining:0,ticket_blocked:false,gate_status:'COMMITMENT_OFF',
    next_reset_at:'2026-07-23T22:00:00+00:00',read_only_to_bybit:true
  };
  overview.journal.trades = [{
    id:'close-r',source_class:'BYBIT_VERIFIED',source_label:'BYBIT GEVERIFIEERD',symbol:'BTCUSDT',direction:'long',
    entry:64000,exit:63200,pnl:-125,pnl_pct:-1.25,closed_at:'2026-07-22T10:00:00Z',process_grade:'B',
    r_multiple:-1.25,r_breach_alarm:true,r_breach_reason:'R < -1: controleer of de technische stop is verruimd of de uitvoering materieel afweek'
  }];
  api.setOverview(overview);
  await wait(50);

  assert.equal(window.document.getElementById('accountGuardBuffer').textContent.trim(), 'US$ 300,00');
  assert.equal(window.document.getElementById('accountGuardBufferFill').style.width, '75%');
  assert.match(window.document.getElementById('accountGuardNotice').textContent, /niet uit of ruimer/i);
  assert.equal(window.document.getElementById('commitmentActivateButton').disabled, false);

  window.document.getElementById('commitmentActivateButton').click();
  await wait(100);
  assert.equal(window.document.getElementById('commitmentActivateButton').disabled, true);
  assert.match(window.document.getElementById('commitmentActivateButton').textContent, /Vergrendeld tot morgen/i);
  assert.match(window.document.getElementById('accountGuardPositionMeta').textContent, /Tweede positie geblokkeerd/i);

  api.switchView('journal');
  await wait(30);
  const alarm = window.document.querySelector('.r-breach-badge');
  assert(alarm, 'R<-1-badge ontbreekt');
  assert.match(alarm.textContent, /STOP CONTROLEREN/i);

  api.setLanguage('en');
  await wait(40);
  assert.match(window.document.getElementById('accountGuardTitle').textContent, /Day buffer/i);
  assert.match(window.document.getElementById('commitmentActivateButton').textContent, /Locked until tomorrow/i);
  assert.match(window.document.querySelector('.r-breach-badge').textContent, /CHECK STOP/i);

  const css = fs.readFileSync(path.join(root, 'dashboard.css'), 'utf8');
  assert.match(css, /\.account-guard-card/);
  assert.match(css, /\.buffer-track/);
  assert.match(css, /\.r-breach-row/);
  const main = fs.readFileSync(path.join(root, 'main.py'), 'utf8');
  assert.match(main, /\/api\/v1\/commitment\/activate/);
  assert.doesNotMatch(main, /commitment\/deactivate/);
  console.log('test_phase5b_ui_r25b.js: buffer, one-way Commitment Mode, cooldown UI en R<-1-alarm werken met echte payloadvorm');
  window.close();
})().catch((error)=>{console.error(error);window.close();process.exitCode=1;});
