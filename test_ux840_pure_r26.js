'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = __dirname;
const html = fs.readFileSync(path.join(root, 'mytradingbot-dashboard.html'), 'utf8');
const js = fs.readFileSync(path.join(root, 'dashboard.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'dashboard.css'), 'utf8');
let checks = 0;
const ok = (condition, message) => { assert.ok(condition, message); checks += 1; };

ok(html.includes('UX v8.4.0') && js.includes("const VERSION = '8.4.0'"), 'UX version is 8.4.0');
ok(js.includes("const MOTOR_VERSION = '8.2.2'"), 'motor version remains 8.2.2');
ok(html.indexOf('id="todaySummary"') < html.indexOf('id="dayStartSection"'), 'Today starts with the focus card');
ok(html.indexOf('id="dayStartSection"') < html.indexOf('id="disciplineSection"'), 'day-start support follows the focus');
ok(html.indexOf('id="disciplineSection"') < html.indexOf('id="accountGuardSection"'), 'discipline and commitment remain secondary');
ok(html.indexOf('id="accountGuardSection"') < html.indexOf('id="accountSection"'), 'account follows commitment');
ok(html.indexOf('id="accountSection"') < html.indexOf('id="positionSection"'), 'position follows account');
ok(html.indexOf('id="positionSection"') < html.indexOf('id="chartWorkflowPanel"'), 'charts are the final Today support panel');
for (const id of ['dayStartCard','disciplinePanel','accountGuardPanel','accountPanel','positionPanel','chartWorkflowPanel']) {
  const re = new RegExp(`<details(?=[^>]*id="${id}")[^>]*>`);
  const match = html.match(re);
  ok(Boolean(match) && !/\sopen(?:\s|=|>)/.test(match[0]), `${id} is a closed details panel`);
}
ok(/class="top-summary"[\s\S]*?class="asset-select"[\s\S]*?class="top-status"/.test(html), 'topbar keeps market and status');
ok((html.match(/id="header(?:Balance|Updated|Layers|Verified|Workspace)"/g) || []).length === 5, 'technical topbar values remain available to assistive tech');
ok(css.includes('text-overflow:clip!important') && css.includes('white-space:normal!important'), 'topbar values cannot ellipsize');
ok(js.includes("headerStatusBox.title = state.language === 'en'"), 'full account and timestamp details move to a tooltip');
ok(js.indexOf("gate.status === 'COMMITMENT_DAY_STOP'") < js.indexOf("const dayStartReady"), 'hard commitment gates stay ahead of day-start');
ok(js.indexOf('const dayStartReady') < js.indexOf("gate.status === 'ENTRY_READY'"), 'day-start becomes the focus before ticket details');
ok(js.includes("'state.daystart.title': 'Begin met je dagstart'") && js.includes("'state.daystart.title': 'Start with your day briefing'"), 'day-start focus is bilingual');
ok(html.includes('Je orderdagboek') && html.includes('Elke trade krijgt een procescijfer'), 'journal has one calm heading and sentence');
ok(/<details[^>]*class="[^"]*performance-board[^"]*secondary-panel/.test(html), 'journal analytics are collapsed');
ok(css.includes('.journal-table{width:100%;min-width:0!important;table-layout:fixed}'), 'journal core columns fit without horizontal scrolling');
ok(css.includes('journal-table td:nth-child(9)') && css.includes('position:sticky;right:0'), 'process column remains visible');
ok(js.includes('journal-meta-icon source-icon') && js.includes("'●'"), 'source badge is a compact accessible icon');
ok(js.includes("'journal-meta-icon direction-warning','!'"), 'direction warning is a compact accessible icon');
ok(css.includes('.direction-unverified{box-shadow:none;background:transparent}'), 'unverified direction is not painted as a red loss');
ok(css.includes('.r-breach-row{box-shadow:inset 4px 0 0 var(--red)}'), 'red remains reserved for a real R breach');
ok(js.includes("document.createTextNode(' ')"), 'no-position copy has an explicit separator');
ok(js.includes("'position.none.title': 'Geen open positie.'") && js.includes("'position.none.title': 'No open position.'"), 'no-position punctuation is fixed in NL and EN');
ok(js.includes("['Rol','Prijsniveau / zone','Reden','Zekerheid']") || (js.includes('Prijsniveau / zone') && js.includes('Zekerheid')), 'four vision fields remain present');
ok(css.includes('#decisionCard .button.primary') && css.includes('.view-section .button.primary{background:rgba('), 'gold is reserved for the main focus action');
ok(css.includes('@media(max-width:680px)') && css.includes('@media(prefers-reduced-motion:reduce)'), 'mobile and reduced-motion protections remain');
ok(html.includes('id="accountPnlDisclosure"') && html.includes('P&amp;L bewust secundair'), 'P&L is secondary and expandable');
ok(fs.existsSync(path.join(root, 'test_ux840_one_focus_r26.js')), 'real-payload jsdom regression is included for the full audit environment');

console.log(`test_ux840_pure_r26.js: ${checks}/${checks} one-focus, calm journal, topbar, bilingual and accessibility assertions green`);
