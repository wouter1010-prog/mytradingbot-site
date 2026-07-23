'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const root = __dirname;
const html = fs.readFileSync(path.join(root, 'mytradingbot-dashboard.html'), 'utf8');
let script = fs.readFileSync(path.join(root, 'dashboard.js'), 'utf8');
script = script
  .replace("positions:[{symbol:'BTCUSDT',side:'Buy',size:.147,entry:63955.4,mark:64210.8,stop_loss:63200,take_profit:66000,leverage:3,liq:55736.5,pnl:37.54}]", 'positions:[]')
  .replaceAll('fresh:true,age_hours:.2', 'fresh:false,age_hours:7.5');

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
  try {
    const d=window.document;
    assert.equal(d.getElementById('focusTitle').textContent, 'Je marktkaart is verouderd');
    assert.equal(d.getElementById('decisionBadge').textContent, 'CHARTS VERNIEUWEN');
    assert.equal(d.getElementById('focusActionButton').textContent, 'Charts vernieuwen');
    assert.match(d.getElementById('decisionReason').textContent, /oud/);
    assert(d.getElementById('reviewCompleteSummary'));
    console.log('test_focus_states.js: verouderde-kaarttoestand en wizard-eindsamenvatting geslaagd');
    window.close();
  } catch (error) {
    console.error(error);
    window.close();
    process.exitCode=1;
  }
}, 350);
