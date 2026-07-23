'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const root = __dirname;
const html = fs.readFileSync(path.join(root, 'mytradingbot-dashboard.html'), 'utf8');
let script = fs.readFileSync(path.join(root, 'dashboard.js'), 'utf8');
script = script
  .replace("Object.fromEntries(TF_ORDER.map((tf) => [tf, demoLayer(tf, true)]))", "Object.fromEntries(TF_ORDER.map((tf) => [tf, demoLayer(tf, tf !== '3M')]))")
  .replace("confirmed:true,review_needed:false,state:'VERIFIED'", "confirmed:tf !== '3M',review_needed:tf === '3M',state:tf === '3M' ? 'SYNCED' : 'VERIFIED'")
  .replace("verified_complete:true,synced_count:4,confirmed_count:4", "verified_complete:false,synced_count:4,confirmed_count:3")
  .replace("positions:[{symbol:'BTCUSDT',side:'Buy',size:.147,entry:63955.4,mark:64210.8,stop_loss:63200,take_profit:66000,leverage:3,liq:55736.5,pnl:37.54}]", "positions:[]")
  .replace("latest:{ok:true,version:VERSION,asset:'BTC'", "latest:{ok:true,version:VERSION,blocking_review_timeframes:[],review_timeframes:['3M'],asset:'BTC'")
  .replace("execution_gate:{status:'ENTRY_READY',label:'INSTAP KLAAR',orderable:true,reason:'3m lokale kanteling bevestigd bij 4H-steun. Ticket mag veilig worden voorbereid; eindklik blijft handmatig.'}", "execution_gate:{status:'WAIT_3M_TRIGGER',label:'WACHT OP 3M-SIGNAAL',orderable:false,reason:'De 3M-chart beweegt, maar er is nog geen concrete lokale kanteling. Je hoeft hem nu niet handmatig te controleren.'}");

const dom = new JSDOM(html, { url:'http://localhost/dashboard?demo=1&static=1', runScripts:'outside-only', pretendToBeVisual:true });
const { window } = dom;
window.AbortController = global.AbortController;
window.URL.createObjectURL = () => 'blob:preview';
window.URL.revokeObjectURL = () => {};
window.HTMLElement.prototype.scrollIntoView = function() {};
window.scrollTo = function() {};
window.HTMLDialogElement.prototype.showModal = function() { this.open=true; this.setAttribute('open',''); };
window.HTMLDialogElement.prototype.close = function() { this.open=false; this.removeAttribute('open'); };
window.fetch = async () => { throw new Error('demo hoort geen netwerk te gebruiken'); };
window.eval(script);

setTimeout(() => {
  const document = window.document;
  assert(document.getElementById('loginLayer').classList.contains('hidden'));
  assert.match(document.getElementById('focusTitle').textContent, /geen trade|niets doen/i);
  assert.doesNotMatch(document.getElementById('focusTitle').textContent, /controleer 3M/i);
  assert.match(document.getElementById('decisionReason').textContent, /geen concreet lokaal signaal/i);
  assert.match(document.getElementById('chartWorkflowSummary').textContent, /geen hercontrole nodig/i);
  console.log('test_smart_review.js: 3M zonder trigger vraagt geen formulier; alleen beslissende wijzigingen blokkeren');
}, 400);
