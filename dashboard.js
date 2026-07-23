(() => {
  'use strict';

  const VERSION = '8.4.0';
  const MOTOR_VERSION = '8.2.2';
  const TOKEN_KEY = 'mytradingbot.v8.session';
  const COLLAPSE_KEY = 'mytradingbot.v811.panelen';
  const VIEW_KEY = 'mytradingbot.v811.view';
  const COACH_MODE_KEY = 'mytradingbot.coach.expert';
  const TF_ORDER = ['1D', '4H', '15M', '3M'];
  const TF_LABELS = {
    '1D': ['Dagcontext', 'Trend en groot bereik'],
    '4H': ['Structuur', 'HTF-zones en locatie'],
    '15M': ['Opbouw', 'Lokale opbouw bij de zone'],
    '3M': ['Instap', 'Eerste lokale kanteling']
  };
  const ROLE_LABELS = { support: 'Steun', resistance: 'Weerstand', unknown: 'Onbekend' };
  const INTENT_LABELS = { structure: 'Structuur', entry: 'Instapkandidaat', target: 'Doel', range_boundary: 'Bereikgrens' };
  const FLAG_LABELS = {
    zone_reaction: 'Reactie in de zone',
    sweep: 'Liquiditeitsprik zichtbaar',
    reclaim: 'Herverovering zichtbaar',
    structure_break: 'Lokale structuur doorbroken',
    close: 'Kaars gesloten',
    retest: 'Hertest houdt',
    pullback: 'Terugval zichtbaar',
    momentum_resume: 'Momentum hervat'
  };
  const PARAMS = new URLSearchParams(location.search);
  const DEMO = PARAMS.get('demo') === '1';
  const STATIC_CAPTURE = PARAMS.get('static') === '1';

  const LANGUAGE_KEY = 'mytradingbot.language';

  const UI_COPY = {
    nl: {
      'state.position.badge': 'POSITIE OPEN', 'state.position.title': 'Je {side} {symbol} loopt',
      'state.position.reason': 'Open resultaat {pnl} · instap {entry} · huidige prijs {price}.',
      'state.position.next': 'Volg je vooraf gekozen plan. Verplaats de stop pas na TP2 én alleen wanneer de resterende positie in winst staat.',
      'state.position.action': 'Bekijk je positie',
      'state.charts.badge': '{count}/4 GELEZEN', 'state.charts.title': 'Lees je 4 charts',
      'state.charts.reason': 'Nog {remaining} chart{plural} ontbreken: {missing}.',
      'state.charts.next': 'Open de chartstappen. De extensie leest 1D, 4H, 15M en 3M in vaste volgorde.', 'state.charts.action': 'Open chartstappen',
      'state.stale.badge': 'CHARTS VERNIEUWEN', 'state.stale.title': 'Je marktkaart is verouderd',
      'state.stale.reason': '{layers} is {age} oud en wordt daarom niet gebruikt voor een nieuw ticket.',
      'state.stale.next': 'Lees alleen de verouderde chart(s) opnieuw. Je lopende positie blijft gewoon zichtbaar en wordt niet aangepast.', 'state.stale.action': 'Charts vernieuwen',
      'state.review.badge': 'GERICHTE CONTROLE', 'state.review.title': 'Controleer alleen {timeframe}',
      'state.review.reason': 'Alleen een inhoudelijk gewijzigde of beslissende chart vraagt opnieuw jouw bevestiging.',
      'state.review.next': 'Ongewijzigde charts blijven goedgekeurd. Je hoeft nooit meer standaard alle vier opnieuw af te tekenen.', 'state.review.action': 'Controleer {timeframe}',
      'state.daystart.badge': 'DAGSTART', 'state.daystart.title': 'Begin met je dagstart',
      'state.daystart.reason': 'Je marktkaart is vers. Neem één minuut om scenario’s, no-trade en je procesfocus bewust door te lopen.',
      'state.daystart.next': 'Open de briefing. Daarna zie je pas de overige details die vandaag relevant zijn.', 'state.daystart.action': 'Neem de dag met me door',
      'state.ticket.badge': 'TICKET KAN KLAAR', 'state.ticket.title': 'Alle regels zijn groen',
      'state.ticket.reason': 'De setup is compleet en gecontroleerd. De definitieve orderklik blijft altijd van jou.',
      'state.ticket.next': 'Open de extensie en laat het ticket invullen. Controleer daarna alles visueel.', 'state.ticket.action': 'Bekijk ticketvoorbereiding',
      'state.wait.badge': 'WACHTEN IS GOED', 'state.wait.title': 'Er is nog geen trade',
      'state.wait.reason': 'De prijs staat nog niet op een geldige plek of de setup mist bevestiging.',
      'state.wait.next': 'Je hoeft niets te forceren. De cockpit blijft kijken; ververs alleen wanneer je nieuwe chartinformatie hebt.', 'state.wait.action': 'Ververs status',
      'state.idle.badge': 'GEEN TRADE', 'state.idle.title': 'Kaart compleet — niets doen is juist',
      'state.idle.reason': 'Er is nu geen geldige setup. Dat is een normale en veilige uitkomst.',
      'state.idle.next': 'Sluit de cockpit gerust. Kom terug wanneer prijs bij een belangrijk niveau komt.', 'state.idle.action': 'Ververs status',
      'position.none.meta': 'Geen open positie', 'position.none.title': 'Geen open positie.',
      'position.none.body': 'Dat is prima. De cockpit bewaakt je kaart en laat alleen iets zien wanneer jij echt actie moet nemen.',
      'price.notFresh': 'Niet vers', 'price.source': 'Prijsbron', 'price.rechecking': 'Prijs wordt opnieuw gecontroleerd',
      'price.public': 'Bybit openbare markprijs', 'price.position': 'Bybit positie-markprijs', 'price.chart': 'TradingView-chartprijs', 'price.unavailable_reason': 'Geen betrouwbare actuele prijs beschikbaar.',
      'gate.WAIT_SYNC': 'GRAFIEKLAGEN AANVULLEN', 'gate.STACK_SYNCED': '4/4 GELEZEN', 'gate.REVIEW_STACK': 'CONTROLEER KAART',
      'gate.PAPER_MODE': 'PAPER TEST', 'gate.WAIT_15M': 'WACHT OP 15M', 'gate.WAIT_15M_SETUP': 'WACHT OP 15M-OPBOUW',
      'gate.REVIEW_15M_SETUP': 'CONTROLEER 15M-OPBOUW', 'gate.WAIT_3M': 'OPEN DE 3M', 'gate.WAIT_3M_TURN': 'WACHT OP 3M-KANTELING',
      'gate.REVIEW_3M_TRIGGER': 'CONTROLEER 3M-SIGNAAL', 'gate.WAIT_HTF_LOCATION': 'WACHT OP HTF-LOCATIE', 'gate.WAIT_PRICE': 'WACHT OP PRIJS',
      'gate.ENTRY_CANDIDATE': 'INSTAPKANDIDAAT', 'gate.ENTRY_READY': 'INSTAP KLAAR', 'gate.SETUP_INVALIDATED': 'HANDELSIDEE ONGELDIG',
      'gate.COMMITMENT_DAY_STOP': 'DAGSTOP ACTIEF', 'gate.COMMITMENT_MAX_POSITION': 'MAX. 1 POSITIE', 'gate.REVENGE_COOLDOWN': 'AFKOELTIJD',
      'gate.BLOCKED': 'GEBLOKKEERD', 'gate.DEFAULT': 'WACHTEN',
      'next.ENTRY_READY': 'Controleer het ticket in TradingView en plaats de order zelf.',
      'next.REVIEW': 'Controleer nu {timeframe}; daarna opent automatisch de volgende controle.',
      'next.PAPER_MODE': 'Test de volledige workflow, stuur feedback en gebruik alleen gesimuleerde journaldata.',
      'next.WAIT_SYNC': 'Open TradingView en synchroniseer: {missing}.',
      'next.WAIT_3M_TURN': 'Blijf op 3m kijken naar de eerste lokale kanteling bij de HTF-zone.',
      'next.REVIEW_3M_TRIGGER': 'Controleer het gevonden 3m-signaal.', 'next.TRIGGER_CONFIRMED': '3m-signaal bevestigd. Alleen bij een echte trade kies je nu instapzone en stop.',
      'next.TICKET_INPUT_REQUIRED': 'Kies voor deze concrete trade een instapzone en één technische stop.',
      'next.WAIT_15M_SETUP': 'Wacht op duidelijke 15m-opbouw bij het HTF-niveau.', 'next.REVIEW_15M_SETUP': 'Controleer de 15m-opbouw die het brein heeft gezien.',
      'next.WAIT_HTF_LOCATION': 'Prijs staat nog niet aantoonbaar bij een geldige HTF-zone.', 'next.DEFAULT': 'Bekijk je charts en volg de gemarkeerde volgende stap.',
      'source.BYBIT_VERIFIED': 'BYBIT GEVERIFIEERD', 'source.MANUAL_OPEN': 'HANDMATIG GEOPEND', 'source.LEGACY': 'LEGACY-IMPORT', 'source.LEGACY_IMPORT': 'LEGACY-IMPORT', 'source.PAPER': 'PAPER', 'source.TESTDATA': 'TESTDATA', 'source.UNKNOWN': 'ONBEKEND',
      'origin.MYTRADINGBOT_TICKET': 'MYTRADINGBOT-TICKET', 'origin.MANUAL_OPEN': 'HANDMATIG GEOPEND', 'origin.UNKNOWN': 'HERKOMST ONBEKEND',
      'consistency.mismatch': 'RICHTING ONGEVERIFIEERD', 'consistency.verified': 'GEVERIFIEERD', 'consistency.unavailable': 'NIET CONTROLEERBAAR',
      'consistency.reason.mismatch': 'Resultaat, richting en prijsverloop moeten handmatig worden gecontroleerd.', 'consistency.reason.verified': 'Richting, prijsverloop en resultaat zijn onderling consistent.', 'consistency.reason.unavailable': 'Er is onvoldoende brondata voor een betrouwbare richtingcontrole.',
      'process.unreviewed': 'NIET BEOORDEELD', 'process.lesson': 'LES', 'process.reviewed': 'BEOORDEELD',
      'metrics.sample.reliable': 'BETROUWBAARDER', 'metrics.sample.building': 'IN OPBOUW', 'metrics.sample.small': 'TE KLEINE STEEKPROEF', 'metrics.sample.insufficient': 'ONVOLDOENDE TRADES',
      'metrics.insufficient': 'Onvoldoende historische equitydata — {available} van {total} records.',
      'metrics.complete': 'Alle sluitingsrecords hebben een eigen historische equity-snapshot.',
      'pnl_basis.bybit': 'BYBIT CLOSED PNL (NETTO)', 'pnl_basis.mixed': 'GEMENGDE BRONNEN', 'pnl_basis.journal': 'JOURNAL PNL',
      'audit.confidence': '{pct}% zekerheid',
      'mode.owner': 'Live eigenaar', 'mode.tester': 'Geïsoleerde paper-test',
      'invite.revoke': 'Trek uitnodiging in', 'invite.open': 'Open', 'invite.expired': 'Verlopen', 'invite.used': 'Gebruikt', 'invite.revoked': 'Ingetrokken', 'invite.none_open': 'Geen openstaande uitnodigingen.',
      'ticket.safe_badge': 'VEILIG VOOR CONTROLE', 'ticket.blocked_badge': '{count} BLOKKADE{plural}', 'ticket.safe_reason': 'De cockpit mag het ticket laten voorbereiden. Controleer alle teruggelezen velden en klik de definitieve orderknop altijd zelf.',
      'journal.showing': '{shown} van {filtered} gefilterde trade{plural} · {total} totaal',
      'review.first': 'eerste controle vereist', 'review.trend_changed': 'trend veranderde van {from} naar {to}',
      'review.approach_changed': 'lokale beweging veranderde van {from} naar {to}', 'review.range_presence': 'rangegrens toegevoegd of verwijderd',
      'review.range_shifted': 'rangegrens verschoof materieel', 'review.zone_changed': 'belangrijke zone toegevoegd, verwijderd of verplaatst',
      'review.15m_changed': '15M-opbouw veranderde', 'review.3m_changed': '3M-signaal veranderde',
      'review.expired': 'menselijke controle is ouder dan {hours} uur', 'review.unchanged': 'ongewijzigde handelskaart; eerdere controle blijft geldig',
      'trigger.local_reversal': 'lokale kanteling', 'trigger.sweep_reclaim': 'sweep/reclaim', 'trigger.breakout_retest': 'uitbraak/hertest', 'trigger.continuation': 'vervolgbeweging', 'trigger.none': 'lokaal signaal',
      'role.support': 'steun', 'role.resistance': 'weerstand', 'role.unknown': 'HTF-zone',
      'reason.REVIEW_STACK': 'Alleen {timeframe} moet opnieuw worden bekeken: {change}. Ongewijzigde charts blijven goedgekeurd.',
      'reason.REVIEW_15M_SETUP': 'Er is een nieuwe 15M-opbouw gezien. Controleer alleen deze laag: {change}.',
      'reason.REVIEW_3M_TRIGGER': 'Er is een nieuw lokaal instapsignaal gezien. Controleer alleen de 3M-trigger: {change}.',
      'reason.WAIT_SYNC': 'Nog niet alle vier charts zijn veilig gelezen.', 'reason.PAPER_MODE': 'Oefenmodus is actief; er wordt geen echt ticket vrijgegeven.',
      'reason.WAIT_15M': 'De HTF-context staat. Open 15M om te zien hoe prijs de zone benadert en de lokale opbouw ontstaat.',
      'reason.WAIT_15M_SETUP': 'De HTF-kaart staat, maar op 15M is nog geen bevestigde lokale opbouw.',
      'reason.WAIT_3M': 'De 1D/4H/15M-keten staat. Open 3M om het eerste lokale instapsignaal te lezen.',
      'reason.WAIT_3M_TRIGGER': 'De 3M-chart beweegt, maar er is nog geen concreet lokaal signaal dat jouw controle nodig heeft.',
      'reason.WAIT_PRICE': 'Geen betrouwbare actuele prijs beschikbaar. De kaart blijft intact, maar het ticket blijft dicht.',
      'reason.WAIT_HTF_LOCATION': '3M is gelezen, maar prijs ligt niet aantoonbaar bij een bevestigde 4H- of 1D-zone.',
      'reason.SETUP_INVALIDATED': 'De relevante HTF-zone is geïnvalideerd. Een lokale 3M-kanteling herstelt die thesis niet.',
      'reason.WAIT_3M_TURN': 'Prijs staat bij een HTF-zone. Er is nog geen bevestigde lokale 3M-kanteling of hertest.',
      'reason.TRIGGER_CONFIRMED': 'Het lokale 3M-signaal is gecontroleerd. Er is bewust nog geen orderticket aangevraagd.',
      'reason.TICKET_INPUT_REQUIRED': 'Het 3M-signaal is bevestigd, maar er is nog geen geldige instapzone voor dit ticket gekozen.',
      'reason.ENTRY_READY': '3M {trigger} bevestigd bij {timeframe} {role}. Het orderticket mag veilig worden voorbereid; de eindklik blijft handmatig.',
      'reason.ENTRY_CANDIDATE': 'De lokale 3M-kanteling is gevonden, maar eerst oplossen: {failed}.',
      'reason.NO_TRADE_RR': 'R:R-poort geblokkeerd: maximaal {max}R, minimaal 3.00R vereist.',
      'reason.NO_TRADE': 'Er is nu geen geldige setup. Dat is een normale en veilige uitkomst.', 'reason.BLOCKED': 'De veiligheidsregels houden het ticket geblokkeerd.',
      'reason.DEFAULT': 'De huidige status is veilig, maar vraagt nog geen nieuwe orderactie.',
      'error.token.title': 'Je toegang moet opnieuw worden gecontroleerd', 'error.token.reason': 'De cockpit kon je werkruimte niet veilig openen.', 'error.token.next': 'Open de extensie, controleer je toegang en probeer daarna opnieuw.',
      'error.connection.title': 'De verbinding is tijdelijk onderbroken', 'error.connection.reason': 'De cockpit kreeg geen betrouwbaar antwoord van de server.', 'error.connection.next': 'Controleer je internetverbinding en probeer opnieuw. Er wordt niets automatisch geplaatst.',
      'error.generic.title': 'De cockpit kan deze status nu niet betrouwbaar tonen', 'error.generic.reason': 'De gegevens zijn uit veiligheid verborgen.', 'error.generic.next': 'Ververs de cockpit. Blijft dit terugkomen, open Beheer → Systeemaudit.',
      'error.retry': 'Opnieuw proberen'
    },
    en: {
      'state.position.badge': 'POSITION OPEN', 'state.position.title': 'Your {side} {symbol} is open',
      'state.position.reason': 'Open PnL {pnl} · entry {entry} · current price {price}.',
      'state.position.next': 'Follow your chosen plan. Move the stop only after TP2 and only when the remaining position is in profit.',
      'state.position.action': 'View your position',
      'state.charts.badge': '{count}/4 READ', 'state.charts.title': 'Read your 4 charts',
      'state.charts.reason': '{remaining} chart{plural} remaining: {missing}.',
      'state.charts.next': 'Open the chart steps. The extension reads 1D, 4H, 15M and 3M in a fixed order.', 'state.charts.action': 'Open chart steps',
      'state.stale.badge': 'REFRESH CHARTS', 'state.stale.title': 'Your market map is outdated',
      'state.stale.reason': '{layers} is {age} old and is therefore not used for a new ticket.',
      'state.stale.next': 'Read only the outdated chart(s) again. Your open position remains visible and is not modified.', 'state.stale.action': 'Refresh charts',
      'state.review.badge': 'TARGETED REVIEW', 'state.review.title': 'Review only {timeframe}',
      'state.review.reason': 'Only a materially changed or decision-critical chart needs your confirmation again.',
      'state.review.next': 'Unchanged charts remain approved. You no longer need to review all four by default.', 'state.review.action': 'Review {timeframe}',
      'state.daystart.badge': 'DAY START', 'state.daystart.title': 'Start with your day briefing',
      'state.daystart.reason': 'Your market map is fresh. Take one minute to review scenarios, no-trade and your process focus.',
      'state.daystart.next': 'Open the briefing. After that, the other details relevant today stay available below.', 'state.daystart.action': 'Walk me through the day',
      'state.ticket.badge': 'TICKET READY', 'state.ticket.title': 'All rules are green',
      'state.ticket.reason': 'The setup is complete and reviewed. The final order click always remains yours.',
      'state.ticket.next': 'Open the extension and let it fill the ticket. Then review everything visually.', 'state.ticket.action': 'View ticket preparation',
      'state.wait.badge': 'WAITING IS GOOD', 'state.wait.title': 'There is no trade yet',
      'state.wait.reason': 'Price is not at a valid location yet or the setup lacks confirmation.',
      'state.wait.next': 'Do not force anything. The cockpit keeps watching; refresh only when you have new chart information.', 'state.wait.action': 'Refresh status',
      'state.idle.badge': 'NO TRADE', 'state.idle.title': 'Map complete — doing nothing is correct',
      'state.idle.reason': 'There is no valid setup now. That is a normal and safe outcome.',
      'state.idle.next': 'You can close the cockpit. Return when price reaches an important level.', 'state.idle.action': 'Refresh status',
      'position.none.meta': 'No open position', 'position.none.title': 'No open position.',
      'position.none.body': 'That is fine. The cockpit monitors your map and only shows something when you genuinely need to act.',
      'price.notFresh': 'Not fresh', 'price.source': 'Price source', 'price.rechecking': 'Price is being checked again',
      'price.public': 'Bybit public mark price', 'price.position': 'Bybit position mark price', 'price.chart': 'TradingView chart price', 'price.unavailable_reason': 'No reliable current price is available.',
      'gate.WAIT_SYNC': 'COMPLETE CHART LAYERS', 'gate.STACK_SYNCED': '4/4 READ', 'gate.REVIEW_STACK': 'REVIEW MAP',
      'gate.PAPER_MODE': 'PAPER TEST', 'gate.WAIT_15M': 'WAIT FOR 15M', 'gate.WAIT_15M_SETUP': 'WAIT FOR 15M SETUP',
      'gate.REVIEW_15M_SETUP': 'REVIEW 15M SETUP', 'gate.WAIT_3M': 'OPEN 3M', 'gate.WAIT_3M_TURN': 'WAIT FOR 3M REVERSAL',
      'gate.REVIEW_3M_TRIGGER': 'REVIEW 3M SIGNAL', 'gate.WAIT_HTF_LOCATION': 'WAIT FOR HTF LOCATION', 'gate.WAIT_PRICE': 'WAIT FOR PRICE',
      'gate.ENTRY_CANDIDATE': 'ENTRY CANDIDATE', 'gate.ENTRY_READY': 'ENTRY READY', 'gate.SETUP_INVALIDATED': 'TRADE IDEA INVALID',
      'gate.COMMITMENT_DAY_STOP': 'DAY STOP ACTIVE', 'gate.COMMITMENT_MAX_POSITION': 'MAX. 1 POSITION', 'gate.REVENGE_COOLDOWN': 'COOLDOWN',
      'gate.BLOCKED': 'BLOCKED', 'gate.DEFAULT': 'WAITING',
      'next.ENTRY_READY': 'Review the ticket in TradingView and place the order yourself.',
      'next.REVIEW': 'Review {timeframe} now; the next review will then open automatically.',
      'next.PAPER_MODE': 'Test the complete workflow, send feedback and use simulated journal data only.',
      'next.WAIT_SYNC': 'Open TradingView and sync: {missing}.',
      'next.WAIT_3M_TURN': 'Keep watching 3M for the first local reversal at the HTF zone.',
      'next.REVIEW_3M_TRIGGER': 'Review the detected 3M signal.', 'next.TRIGGER_CONFIRMED': 'The 3M signal is confirmed. Only for a real trade, now choose an entry zone and stop.',
      'next.TICKET_INPUT_REQUIRED': 'Choose an entry zone and one technical stop for this specific trade.',
      'next.WAIT_15M_SETUP': 'Wait for a clear 15M setup at the HTF level.', 'next.REVIEW_15M_SETUP': 'Review the 15M setup detected by the engine.',
      'next.WAIT_HTF_LOCATION': 'Price is not demonstrably at a valid HTF zone yet.', 'next.DEFAULT': 'Review your charts and follow the highlighted next step.',
      'source.BYBIT_VERIFIED': 'BYBIT VERIFIED', 'source.MANUAL_OPEN': 'MANUALLY OPENED', 'source.LEGACY': 'LEGACY IMPORT', 'source.LEGACY_IMPORT': 'LEGACY IMPORT', 'source.PAPER': 'PAPER', 'source.TESTDATA': 'TEST DATA', 'source.UNKNOWN': 'UNKNOWN',
      'origin.MYTRADINGBOT_TICKET': 'MYTRADINGBOT TICKET', 'origin.MANUAL_OPEN': 'MANUALLY OPENED', 'origin.UNKNOWN': 'ORIGIN UNKNOWN',
      'consistency.mismatch': 'DIRECTION UNVERIFIED', 'consistency.verified': 'VERIFIED', 'consistency.unavailable': 'NOT VERIFIABLE',
      'consistency.reason.mismatch': 'Result, direction and price movement require manual review.', 'consistency.reason.verified': 'Direction, price movement and result are mutually consistent.', 'consistency.reason.unavailable': 'There is not enough source data for a reliable direction check.',
      'process.unreviewed': 'NOT REVIEWED', 'process.lesson': 'LESSON', 'process.reviewed': 'REVIEWED',
      'metrics.sample.reliable': 'MORE RELIABLE', 'metrics.sample.building': 'BUILDING', 'metrics.sample.small': 'SAMPLE TOO SMALL', 'metrics.sample.insufficient': 'INSUFFICIENT TRADES',
      'metrics.insufficient': 'Insufficient historical equity data — {available} of {total} records.',
      'metrics.complete': 'Every close record has its own historical equity snapshot.',
      'pnl_basis.bybit': 'BYBIT CLOSED PNL (NET)', 'pnl_basis.mixed': 'MIXED SOURCES', 'pnl_basis.journal': 'JOURNAL PNL',
      'audit.confidence': '{pct}% confidence',
      'mode.owner': 'Live owner', 'mode.tester': 'Isolated paper test',
      'invite.revoke': 'Revoke invitation', 'invite.open': 'Open', 'invite.expired': 'Expired', 'invite.used': 'Used', 'invite.revoked': 'Revoked', 'invite.none_open': 'No open invitations.',
      'ticket.safe_badge': 'SAFE TO REVIEW', 'ticket.blocked_badge': '{count} BLOCKER{plural}', 'ticket.safe_reason': 'The cockpit may prepare the ticket. Review every read-back field and always click the final order button yourself.',
      'journal.showing': '{shown} of {filtered} filtered trade{plural} · {total} total',
      'review.first': 'first review required', 'review.trend_changed': 'trend changed from {from} to {to}',
      'review.approach_changed': 'local movement changed from {from} to {to}', 'review.range_presence': 'range boundary added or removed',
      'review.range_shifted': 'range boundary shifted materially', 'review.zone_changed': 'important zone added, removed or moved',
      'review.15m_changed': '15M setup changed', 'review.3m_changed': '3M signal changed',
      'review.expired': 'human review is older than {hours} hours', 'review.unchanged': 'unchanged trading map; the previous review remains valid',
      'trigger.local_reversal': 'local reversal', 'trigger.sweep_reclaim': 'sweep and reclaim', 'trigger.breakout_retest': 'breakout and retest', 'trigger.continuation': 'continuation', 'trigger.none': 'local signal',
      'role.support': 'support', 'role.resistance': 'resistance', 'role.unknown': 'HTF zone',
      'reason.REVIEW_STACK': 'Only {timeframe} must be reviewed again: {change}. Unchanged charts remain approved.',
      'reason.REVIEW_15M_SETUP': 'A new 15M setup was detected. Review only this layer: {change}.',
      'reason.REVIEW_3M_TRIGGER': 'A new local entry signal was detected. Review only the 3M trigger: {change}.',
      'reason.WAIT_SYNC': 'Not all four charts have been read safely yet.', 'reason.PAPER_MODE': 'Paper mode is active; no live ticket is released.',
      'reason.WAIT_15M': 'The HTF context is ready. Open 15M to see how price approaches the zone and builds the local setup.',
      'reason.WAIT_15M_SETUP': 'The HTF map is ready, but 15M does not yet show a confirmed local setup.',
      'reason.WAIT_3M': 'The 1D/4H/15M chain is ready. Open 3M to read the first local entry signal.',
      'reason.WAIT_3M_TRIGGER': 'The 3M chart is moving, but there is no concrete local signal that needs your review yet.',
      'reason.WAIT_PRICE': 'No reliable current price is available. The map remains intact, but the ticket stays locked.',
      'reason.WAIT_HTF_LOCATION': '3M has been read, but price is not demonstrably at a confirmed 4H or 1D zone.',
      'reason.SETUP_INVALIDATED': 'The relevant HTF zone has been invalidated. A local 3M reversal does not restore that thesis.',
      'reason.WAIT_3M_TURN': 'Price is at an HTF zone. There is no confirmed local 3M reversal or retest yet.',
      'reason.TRIGGER_CONFIRMED': 'The local 3M signal has been reviewed. No order ticket has been requested yet by design.',
      'reason.TICKET_INPUT_REQUIRED': 'The 3M signal is confirmed, but no valid entry zone has been selected for this ticket.',
      'reason.ENTRY_READY': '3M {trigger} confirmed at {timeframe} {role}. The order ticket may be prepared safely; the final click remains manual.',
      'reason.ENTRY_CANDIDATE': 'The local 3M reversal was detected, but first resolve: {failed}.',
      'reason.NO_TRADE_RR': 'R:R gate blocked: maximum {max}R, minimum 3.00R required.',
      'reason.NO_TRADE': 'There is no valid setup now. That is a normal and safe outcome.', 'reason.BLOCKED': 'The safety rules keep the ticket locked.',
      'reason.DEFAULT': 'The current status is safe, but does not require a new order action.',
      'error.token.title': 'Your access must be checked again', 'error.token.reason': 'The cockpit could not open your workspace securely.', 'error.token.next': 'Open the extension, check your access and try again.',
      'error.connection.title': 'The connection is temporarily interrupted', 'error.connection.reason': 'The cockpit did not receive a reliable response from the server.', 'error.connection.next': 'Check your internet connection and try again. Nothing is placed automatically.',
      'error.generic.title': 'The cockpit cannot display this status reliably right now', 'error.generic.reason': 'The data is hidden for safety.', 'error.generic.next': 'Refresh the cockpit. If this keeps happening, open Manage → System audit.',
      'error.retry': 'Try again'
    }
  };

  function ui(key, params = {}) {
    const table = UI_COPY[state?.language === 'en' ? 'en' : 'nl'] || UI_COPY.nl;
    const fallback = UI_COPY.nl[key] || key;
    return String(table[key] ?? fallback).replace(/\{(\w+)\}/g, (_, name) => String(params[name] ?? ''));
  }

  function priceSourceLabel(value) {
    const raw = String(value || '').trim();
    if (/public|openbare/i.test(raw)) return ui('price.public');
    if (/position|positie/i.test(raw)) return ui('price.position');
    if (/tradingview|chart/i.test(raw)) return ui('price.chart');
    return raw || ui('price.source');
  }


  function sourceLabel(item = {}) {
    const sourceClass = String(item.source_class || 'UNKNOWN').toUpperCase().replace(/[^A-Z0-9]+/g, '_');
    const source = ui(`source.${sourceClass}`);
    const originClass = String(item.origin_class || '').toUpperCase().replace(/[^A-Z0-9]+/g, '_');
    if (!originClass) return source;
    const originKey = `origin.${originClass}`;
    const origin = ui(originKey);
    return origin === originKey ? source : `${source} · ${origin}`;
  }

  function consistencyLabel(value) {
    const key = `consistency.${String(value || 'unavailable').toLowerCase()}`;
    const label = ui(key);
    return label === key ? ui('consistency.unavailable') : label;
  }

  function processLabel(item = {}) {
    const grade = String(item.process_grade || item.proces_grade || '').toUpperCase();
    if (['A','B','C'].includes(grade)) return grade;
    const status = String(item.process_status || item.proces_status || '').toLowerCase();
    if (['reviewed','beoordeeld','complete','completed'].includes(status)) return ui('process.reviewed');
    return item.lesson ? ui('process.lesson') : ui('process.unreviewed');
  }

  function consistencyReason(value) {
    const normalized = String(value || 'unavailable').toLowerCase();
    const key = `consistency.reason.${['mismatch','verified','unavailable'].includes(normalized) ? normalized : 'unavailable'}`;
    return ui(key);
  }

  function sampleLabelForCount(count) {
    if (count >= 100) return ui('metrics.sample.reliable');
    if (count >= 30) return ui('metrics.sample.building');
    if (count >= 10) return ui('metrics.sample.small');
    return ui('metrics.sample.insufficient');
  }

  function percentageMetricsReason(stats = {}, total = 0) {
    const available = Number.isFinite(Number(stats.snapshot_count)) ? Number(stats.snapshot_count) : Math.round((Number(stats.snapshot_coverage_pct || 0) / 100) * Number(total || 0));
    return available >= total && total > 0
      ? ui('metrics.complete')
      : ui('metrics.insufficient', { available, total });
  }


  function pnlBasisLabel(value) {
    const raw = String(value || '').toUpperCase();
    if (raw.includes('BYBIT')) return ui('pnl_basis.bybit');
    if (raw.includes('GEMENG') || raw.includes('MIXED')) return ui('pnl_basis.mixed');
    return ui('pnl_basis.journal');
  }

  function normaliseTrendLabel(value) {
    const raw = String(value || 'unknown').toLowerCase();
    const labels = state.language === 'en'
      ? { up:'up', down:'down', range:'range', sideways:'range', unknown:'unknown' }
      : { up:'stijgend', down:'dalend', range:'range', sideways:'range', unknown:'onbekend' };
    return labels[raw] || raw;
  }

  function reviewReasonLabel(rawValue) {
    const raw = String(rawValue || '').trim();
    if (!raw) return ui('review.first');
    let match = raw.match(/^trend veranderde van (\S+) naar (\S+)$/i);
    if (match) return ui('review.trend_changed', { from: normaliseTrendLabel(match[1]), to: normaliseTrendLabel(match[2]) });
    match = raw.match(/^lokale beweging veranderde van (\S+) naar (\S+)$/i);
    if (match) return ui('review.approach_changed', { from: normaliseTrendLabel(match[1]), to: normaliseTrendLabel(match[2]) });
    match = raw.match(/^menselijke controle is ouder dan ([0-9.]+) uur$/i);
    if (match) return ui('review.expired', { hours: match[1] });
    const exact = {
      'eerste controle vereist':'review.first',
      'rangegrens toegevoegd of verwijderd':'review.range_presence',
      'rangegrens verschoof materieel':'review.range_shifted',
      'belangrijke zone toegevoegd, verwijderd of verplaatst':'review.zone_changed',
      '15m-opbouw veranderde':'review.15m_changed',
      '3m-signaal veranderde':'review.3m_changed',
      'ongewijzigde handelskaart; eerdere controle blijft geldig':'review.unchanged',
    };
    const key = exact[raw.toLowerCase()];
    return key ? ui(key) : (state.language === 'en' ? ui('review.first') : raw);
  }

  function triggerLabelForUi(value) {
    const key = `trigger.${String(value || 'none').toLowerCase()}`;
    const label = ui(key);
    return label === key ? ui('trigger.none') : label;
  }

  function roleLabelForUi(value) {
    const key = `role.${String(value || 'unknown').toLowerCase()}`;
    const label = ui(key);
    return label === key ? ui('role.unknown') : label;
  }

  function checkLabelForUi(check = {}) {
    const key = String(check.key || '');
    const labels = {
      htf_location: ['HTF-locatie', 'HTF location'], htf_thesis: ['HTF-thesis', 'HTF thesis'], htf_invalidation: ['HTF-zonegrens', 'HTF zone boundary'],
      m15_context: ['15M-context', '15M context'], m15_setup: ['15M-opbouw', '15M setup'], m3_trigger: ['3M-signaal', '3M signal'],
      m3_confirmations: ['minimaal twee triggerbewijzen', 'at least two trigger confirmations'], local_turn: ['lokale trendkanteling', 'local trend reversal'],
      context_relation: ['relatie met HTF-zone', 'relation to the HTF zone'], price_side: ['prijszijde en geldigheid', 'price side and validity'],
      m3_stop: ['technische ticketstop', 'technical ticket stop'], targets: ['drie tegengestelde zones', 'three opposing zones'], rr: ['R:R ≥ 1:3', 'R:R ≥ 1:3'],
      range: ['4H-rangecontext', '4H range context'], freshness: ['actuele tijdframeketen', 'fresh timeframe chain'],
    };
    return (labels[key] || [check.label || key, check.label || key])[state.language === 'en' ? 1 : 0];
  }

  function executionReason(latest = {}) {
    const gate = latest.execution_gate || {};
    const status = String(gate.status || 'DEFAULT');
    const blocking = asArray(latest.blocking_review_timeframes);
    const review = asArray(latest.review_timeframes);
    const timeframe = blocking[0] || review[0] || '1D';
    const reviewSource = layerBundle(timeframe).source || {};
    const change = reviewReasonLabel(reviewSource.review_reason);
    if (status === 'REVIEW_STACK' || status === 'STACK_SYNCED') return ui('reason.REVIEW_STACK', { timeframe, change });
    if (status === 'REVIEW_15M_SETUP') return ui('reason.REVIEW_15M_SETUP', { change: reviewReasonLabel((layerBundle('15M').source || {}).review_reason) });
    if (status === 'REVIEW_3M_TRIGGER') return ui('reason.REVIEW_3M_TRIGGER', { change: reviewReasonLabel((layerBundle('3M').source || {}).review_reason) });
    if (status === 'ENTRY_READY') {
      const setup = latest.setup || {};
      const parent = setup.parent_zone || latest.parent_zone || {};
      const trigger = latest.trigger_3m || latest.trigger || setup.trigger || {};
      return ui('reason.ENTRY_READY', {
        trigger: triggerLabelForUi(trigger.type || setup.trigger_type),
        timeframe: parent.source_timeframe || parent.timeframe || 'HTF',
        role: roleLabelForUi(parent.role || parent.rol),
      });
    }
    if (status === 'ENTRY_CANDIDATE') {
      const failed = asArray(gate.checks).filter((check) => check && check.ok === false).map(checkLabelForUi);
      return ui('reason.ENTRY_CANDIDATE', { failed: failed.join(', ') || (state.language === 'en' ? 'the remaining safety checks' : 'de resterende veiligheidscontroles') });
    }
    if (status === 'NO_TRADE') {
      const rr = asArray(gate.checks).find((check) => check?.key === 'rr' && check.ok === false);
      const match = String(rr?.detail || gate.reason || '').match(/([0-9.]+)R/i);
      return rr || /R:R/i.test(String(gate.reason || '')) ? ui('reason.NO_TRADE_RR', { max: match?.[1] || '0.00' }) : ui('reason.NO_TRADE');
    }
    if (['COMMITMENT_DAY_STOP','COMMITMENT_MAX_POSITION','REVENGE_COOLDOWN'].includes(status)) {
      const guard = latest.account_guard || state.overview?.account_guard || {};
      if (state.language !== 'en') return guard.reason || String(gate.reason || 'Commitment Mode houdt het ticket dicht.');
      if (status === 'COMMITMENT_DAY_STOP') return 'The daily buffer is exhausted. Commitment Mode keeps new tickets locked until the next Amsterdam calendar day.';
      if (status === 'COMMITMENT_MAX_POSITION') return 'One position is already open. Commitment Mode does not allow a second position today.';
      return 'Cooldown after a stop-out. Wait calmly until the timer expires before reassessing.';
    }
    const key = `reason.${status}`;
    const value = ui(key);
    if (value !== key) return value;
    return ui('reason.DEFAULT');
  }

  function errorKind(raw) {
    const value = String(raw || '');
    if (/token|401|403|toegang|unauthor/i.test(value)) return 'token';
    if (/timeout|niet op tijd|network|fetch|verbinding|abort/i.test(value)) return 'connection';
    return 'generic';
  }
  const NL_EN_EXTRA = [
    ['Volgende stap', 'Next step'], ['Status', 'Status'], ['Dagstart', 'Day start'],
    ['Je orderdagboek', 'Your trade journal'],
    ['Elke trade krijgt een procescijfer. Resultaten en patronen staan rustig ingeklapt.', 'Every trade receives a process grade. Results and patterns stay quietly collapsed.'],
    ['Afgeronde trades', 'Completed trades'],
    ['Proces eerst. Open een regel voor alle bron-, richting- en uitvoeringsdetails.', 'Process first. Open a row for all source, direction and execution details.'],
    ['Resultaten en patronen', 'Results and patterns'],
    ['Nog geen trades', 'No trades yet'], ['Nieuwe sluitingen verschijnen hier automatisch.', 'New closes appear here automatically.'],
    ['Open alleen de coach, les of reflectie die je nu nodig hebt.', 'Open only the coach, lesson or reflection you need now.'],
    ['Testers, bronnen en diagnose blijven uit je dagelijkse handelsflow.', 'Testers, sources and diagnostics stay out of your daily trading flow.'],
    ['Briefing klaar', 'Briefing ready'], ['Open wanneer je je dag bewust wilt beginnen.', 'Open when you want to begin the day deliberately.'],
    ['Nog geen opname', 'No capture yet'], ['Lees deze chart vanuit TradingView.', 'Read this chart from TradingView.'],
    ['Nog geen grafiek', 'No chart yet'], ['De lijn verschijnt na je eerste sluitingen.', 'The line appears after your first closes.'],
    ['Dagbuffer & Commitment Mode', 'Day buffer & Commitment Mode'],
    ['Vrijwillig, één richting', 'Voluntary, one way'],
    ['Zie hoeveel rustige ruimte er vandaag nog is. Geen P&L-teller, alleen de resterende buffer.', 'See how much calm room remains today. No P&L counter, only the remaining buffer.'],
    ['Resterende dagbuffer', 'Remaining day buffer'],
    ['Activeer Commitment Mode om deze limiet voor vandaag te vergrendelen.', 'Activate Commitment Mode to lock this limit for today.'],
    ['Positiehek', 'Position gate'], ['Niet actief', 'Not active'], ['Afkoeltijd', 'Cooldown'], ['Geen', 'None'],
    ['Na een stop-out', 'After a stop-out'], ['Reset', 'Reset'], ['Morgen', 'Tomorrow'],
    ['Dagverlieslimiet', 'Daily loss limit'], ['Commitment Mode activeren', 'Activate Commitment Mode'],
    ['Eenmaal actief kan dit hek vandaag niet uit of ruimer. Morgen kies je opnieuw.', 'Once active, this gate cannot be turned off or widened today. You choose again tomorrow.'],
    ['Jouw discipline vandaag', 'Your discipline today'],
    ['De score gebruikt alleen procesdata; winst of verlies telt niet mee.', 'The score uses process data only; profit or loss does not count.'],
    ['Discipline-score', 'Discipline score'],
    ['Nog geen procesdata', 'Not enough process data yet'],
    ['Regels gevolgd', 'Rules followed'],
    ['Alleen beoordeelde trades', 'Assessed trades only'],
    ['Procesgrade-trend', 'Process-grade trend'],
    ['A, B en C — zonder P&L', 'A, B and C — without P&L'],
    ['Verdien je dag', 'Earn your day'],
    ['Doe je dagstart of leg bewust een kijkdag vast.', 'Complete your day start or consciously record a watching day.'],
    ['Ik heb vandaag bewust niet gehandeld', 'I consciously did not trade today'],
    ['Hoe wordt deze score opgebouwd?', 'How is this score calculated?'],
    ['Regelgedrag', 'Rule behaviour'],
    ['Procesgrades', 'Process grades'],
    ['Dagritme', 'Daily routine'],
    ['Geen P&L, winrate of rekeninggroei. Alleen wat jij kon controleren.', 'No P&L, win rate or account growth. Only what you could control.'],
    ['P&L bewust secundair', 'P&L deliberately secondary'],
    ['Toon resultaat', 'Show result'],
    ['Je proces staat boven de uitkomst van één trade.', 'Your process matters more than the outcome of one trade.'],
    ['DEMO — GEEN ECHTE TRADE OF ACCOUNTDATA', 'DEMO — NO REAL TRADE OR ACCOUNT DATA'],
    ['POSITIE OPEN', 'POSITION OPEN'], ['NET GECHECKT', 'JUST CHECKED'], ['Winstfactor', 'Profit factor'], ['0,5%', '0.5%'],
    ['Herkomst van de regels', 'Rule provenance'], ['OPERATORBELEID', 'OPERATOR POLICY'], ['AUDIT-GEVERIFIEERD', 'AUDIT VERIFIED'],
    ['A-PROCES', 'A PROCESS'], ['B-PROCES', 'B PROCESS'], ['C-PROCES', 'C PROCESS'],
    ['Scalp 0,5%, dagtrade 1%, swingtrade 2% is een persoonlijke instelling.', 'Scalp 0.5%, day trade 1%, swing trade 2% is a personal setting.'],
    ['Swingtrade', 'Swing trade'], ['15m-opbouw', '15m setup'], ['Daily-bereik hoog', 'Daily range high'], ['Daily-steun', 'Daily support'],
    ['Nu', 'Now'], ['Gecheckt', 'Checked'], ['Positie loopt', 'Position open'],
    ['Je LONG BTCUSDT loopt', 'Your LONG BTCUSDT is open'], ['Je SHORT BTCUSDT loopt', 'Your SHORT BTCUSDT is open'],
    ['Volg je vooraf gekozen plan. Verplaats de stop pas na TP2 én alleen wanneer de resterende positie in winst staat.', 'Follow your chosen plan. Move the stop only after TP2 and only when the remaining position is in profit.'],
    ['Volg je vooraf ingestelde plan', 'Follow your pre-set plan'],
    ['Stop na TP1 laten staan. Pas na TP2 én alleen wanneer de resterende positie in winst staat mag de stop naar break-even.', 'Keep the stop in place after TP1. Only after TP2, and only when the remaining position is in profit, may the stop move to break-even.'],
    ['Bekijk je positie', 'View your position'], ['Jouw rekening', 'Your account'], ['Versie', 'Version'],
    ['Live, alleen-lezen via Bybit', 'Live, read-only via Bybit'], ['Grootte', 'Size'], ['Liquidatie', 'Liquidation'],
    ['gelezen', 'read'], ['geen hercontrole nodig', 'no re-review needed'], ['gerichte controle', 'targeted review'], ['gerichte controles', 'targeted reviews'],
    ['GECONTROLEERD', 'REVIEWED'], ['Gecontroleerd', 'Reviewed'], ['Gesynchroniseerd', 'Synced'], ['GELEZEN', 'READ'],
    ['Trend en groot bereik', 'Trend and broad range'], ['HTF-zones en locatie', 'HTF zones and location'], ['Lokale opbouw bij de zone', 'Local setup near the zone'], ['Eerste lokale kanteling', 'First local reversal'],
    ['Huidige prijs is beschikbaar', 'Current price is available'], ['Rekeningwaarde is bijgewerkt', 'Account value is up to date'],
    ['Juiste werkruimte actief', 'Correct workspace active'], ['Alle veiligheidsregels zijn groen', 'All safety rules are green'],
    ['Jij houdt de eindklik', 'You keep the final click'], ['de cockpit klikt nooit definitief', 'the cockpit never performs the final click'],
    ['paper test · geen echt ticket', 'paper test · no real ticket'], ['live ticketcontrole toegestaan', 'live ticket review allowed'],
    ['3m lokale kanteling bevestigd bij 4H-steun. Ticket mag veilig worden voorbereid; eindklik blijft handmatig.', '3m local reversal confirmed at 4H support. The ticket may be prepared safely; the final click remains manual.'],
    ['Bekijk gecontroleerde kaart', 'View reviewed map'], ['ongewijzigde controles geldig', 'unchanged reviews remain valid'],
    ['Nauwkeurigheid', 'Accuracy'], ['Dag-bereik hoog', 'Daily range high'], ['Dag-steun', 'Daily support'],
    ['Alle vier charts staan in de cockpit. Alleen inhoudelijke wijzigingen of een concreet setup/signaal vragen opnieuw jouw controle.', 'All four charts are in the cockpit. Only material changes or a concrete setup/signal require another review.'],
    ['Prijs en ticket', 'Price and ticket'], ['Hoofdcontext', 'Primary context'], ['HTF-locatie', 'HTF location'], ['Nog geen ouderzone gekoppeld', 'No parent zone linked yet'],
    ['gekoppelde zone aan', 'linked zone to'], ['gekoppelde zones aan', 'linked zones to'],
    ['TE KLEINE STEEKPROEF', 'SAMPLE TOO SMALL'], ['afgeronde sluitingsrecords', 'completed close records'], ['Bybit-geverifieerd', 'Bybit verified'],
    ['van account', 'of account'], ['Voorlopig: te weinig trades voor conclusies', 'Preliminary: too few trades for conclusions'],
    ['met historische rekeningwaarde', 'with historical account value'], ['Waar komen deze cijfers vandaan?', 'Where do these numbers come from?'],
    ['Bron: gemengde bronnen', 'Source: mixed sources'], ['gemengde bronnen', 'mixed sources'], ['Dekking', 'Coverage'], ['bijgewerkt', 'updated'],
    ['Winfactor', 'Profit factor'], ['Verwachtingswaarde', 'Expectancy'], ['Gem. winst / verlies', 'Avg. win / loss'], ['Verwachting in R', 'Expectancy in R'],
    ['Alleen records met een opgeslagen R-resultaat', 'Only records with a stored R result'], ['Grootste verliesreeks', 'Largest losing streak'],
    ['Aaneengesloten verliestrades', 'Consecutive losing trades'], ['Kosten', 'Costs'], ['Gemiddelde ongunstige / gunstige beweging', 'Average adverse / favourable movement'],
    ['Onvoldoende steekproef', 'Insufficient sample'], ['De cijfers zijn zichtbaar, maar nog niet betrouwbaar genoeg om je regels te veranderen.', 'The figures are visible, but not yet reliable enough to change your rules.'],
    ['Resultaat', 'Result'], ['ONBEKEND', 'UNKNOWN'], ['gefilterde trades', 'filtered trades'], ['totaal', 'total'],
    ['lessen verwerkt', 'lessons processed'], ['laatste bron', 'latest source'], ['UIT', 'OFF'], ['Laatste bron', 'Latest source'], ['Titel', 'Title'],
    ['Lessen', 'Lessons'], ['Verwerkt', 'Processed'], ['Wachtrij', 'Queue'], ['Laatste controle', 'Last check'],
    ['Owner-only kennisinvoer', 'Owner-only knowledge input'], ['Kennisbron', 'Knowledge source'],
    ['Openbare kanaalbewaking en handmatige Platinum-links gebruiken dezelfde veilige wachtrij.', 'Public channel monitoring and manual Platinum links use the same safe queue.'],
    ['Plak Platinum-link', 'Paste Platinum link'], ['Voeg toe aan kenniswachtrij', 'Add to knowledge queue'],
    ['Geen Discord-scraping. Alleen de link die jij als eigenaar bewust toevoegt wordt verwerkt. Video-inhoud kan nooit handels- of risicopoorten wijzigen.', 'No Discord scraping. Only a link deliberately added by the owner is processed. Video content can never change trading or risk gates.'],
    ['Laatste automatische controle wordt geladen…', 'Loading latest automatic check…'],
    ['Bron, controle en persoonlijke keuze blijven gescheiden.', 'Source, verification and personal choice remain separate.'],
    ['Risicoprofielen', 'Risk profiles'], ['is een persoonlijke instelling.', 'is a personal setting.'],
    ['Stop pas na TP2 naar break-even en alleen wanneer de positie in winst staat.', 'Move the stop to break-even only after TP2 and only when the position is in profit.'],
    ['Kant-check', 'Side check'], ['Een instap wordt geblokkeerd wanneer prijs de geldige orderzijde al voorbij is.', 'An entry is blocked when price has already passed the valid order side.'],
    ['Alleen inschakelen voor content waarvoor aantoonbare gebruiksrechten bestaan.', 'Enable only for content with demonstrable usage rights.'],
    ['Nog geen ingestielog beschikbaar.', 'No ingestion log available yet.'], ['Proces boven uitkomst', 'Process over outcome'],
    ['Te vroege instap', 'Entry too early'], ['Win, maar het proces was te vroeg.', 'Win, but the process was too early.'],
    ['Beter: Eerst de 3m-close en hertest afwachten.', 'Better: wait for the 3m close and retest first.'],
    ['Een winst zonder bevestiging is geen A-proces.', 'A win without confirmation is not an A process.'],
    ['3m-hertest afgewacht', 'Waited for the 3m retest'], ['Goede trade op basis van proces.', 'Good trade based on process.'],
    ['Goed: De lokale kanteling kwam binnen bevestigde 4H-steun.', 'Good: the local reversal occurred inside confirmed 4H support.'],
    ['Blijf wachten op sweep, gain en hertest.', 'Keep waiting for sweep, gain and retest.'],
    ['Toegang', 'Access'], ['Testers en uitnodigingen', 'Testers and invitations'], ['Naam', 'Name'], ['Werkruimte', 'Workspace'], ['Modus', 'Mode'],
    ['Geïsoleerde paper-test', 'Isolated paper test'], ['5 minuten (test)', '5 minutes (test)'], ['gebruik(en) over', 'use(s) remaining'],
    ['Chart laag gecontroleerd', 'Chart layer reviewed'], ['3m-laag gecontroleerd', '3m layer reviewed'],
    ['Sluitingsrecord', 'Close record'], ['Chart controleren', 'Review chart'], ['Er is nog geen preview.', 'No preview is available yet.'],
    ['Tijdframe', 'Timeframe'], ['Dagtrade', 'Day trade'], ['Nog geen setup', 'No setup yet'], ['Vervolg', 'Continuation'],
    ['3m-signaal', '3m signal'], ['Nog geen signaal', 'No signal yet'], ['Kies een zone', 'Choose a zone'],
    ['Opslaan en volgende laag', 'Save and continue'], ['Bron', 'Source'], ['Regel', 'Rule'], ['Onderbouwing', 'Evidence'],
    ['datum onbekend', 'date unknown'], ['bron onbekend', 'source unknown'], ['status onbekend', 'status unknown'], ['betrouwbaarheid', 'confidence'],
    ['Mislukt', 'Failed'], ['onbekende fout', 'unknown error'], ['Verwerking gestart', 'Processing started'], ['Laatste fout', 'Latest error'],
    ['Voor de trade', 'Before the trade'], ['Tijdens de trade', 'During the trade'], ['Na de trade', 'After the trade'],
    ['Geplande stop', 'Planned stop'], ['Gepland risico', 'Planned risk'], ['Niet opgeslagen', 'Not stored'], ['Niet controleerbaar', 'Cannot be verified'],
    ['Niet beoordeeld', 'Not reviewed'], ['Nog geen les gekoppeld', 'No lesson linked yet'],
    ['Grafiekbewijs 1D → 4H → 15M → 3M', 'Chart evidence 1D → 4H → 15M → 3M'],
    ['Snapshots worden alleen getoond wanneer ze bij deze trade zijn opgeslagen. Ontbrekende beelden worden niet verzonnen.', 'Snapshots are shown only when stored with this trade. Missing images are never invented.'],
    ['Nog geen systeemmeldingen.', 'No system messages yet.'], ['Grafiek gesynchroniseerd', 'Chart synced'], ['Grafiek ongewijzigd', 'Chart unchanged'],
    ['Laag opgeslagen', 'Layer saved'], ['Ticket voorbereid', 'Ticket prepared'], ['Ticket geblokkeerd', 'Ticket blocked'], ['Plaatsing geregistreerd', 'Placement recorded'],
    ['Doel 1 voorbereid', 'Target 1 prepared'], ['Doel 2 voorbereid', 'Target 2 prepared'], ['Doel 3 voorbereid', 'Target 3 prepared'],
  ];

  const NL_EN_BASE = [
    ['Coachstijl', 'Coach style'], ['Helder en stap voor stap', 'Clear and step by step'],
    ['Standaard legt de coach lastige begrippen uit in gewone taal, met één analogie en een klein voorbeeld.', 'By default, the coach explains difficult concepts in everyday language, with one analogy and a small example.'],
    ['Expertmodus', 'Expert mode'], ['Kort en technisch', 'Short and technical'], ['HELDER', 'CLEAR'], ['EXPERT', 'EXPERT'],
    ['Leg uit', 'Explain'], ['Coach opent hieronder met een uitleg in gewone taal.', 'The coach opens below with an explanation in everyday language.'],
    ['Dagstart-coach', 'Day-start coach'], ['Neem de dag met me door', 'Walk me through the day'],
    ["Scenario's, geen voorspellingen. Geen trade is een volwaardige uitkomst.", 'Scenarios, not predictions. No trade is a valid outcome.'],
    ['Je briefing staat klaar zodra jij hem opent.', 'Your briefing is ready when you open it.'],
    ['Ik gebruik je verse marktkaart, rangepositie, lopende positie en recente procesdata.', 'I use your fresh market map, range position, open position and recent process data.'],
    ['Mentorbriefing', 'Mentor briefing'], ['Jouw dagstart-briefing', 'Your day-start briefing'], ["SCENARIO'S", 'SCENARIOS'],
    ['Vraag door over deze dagstart', 'Ask a follow-up about this day-start'],
    ['Bijvoorbeeld: waar moet ik vandaag vooral níét op reageren?', 'For example: what should I deliberately ignore today?'],
    ['Vraag coach', 'Ask coach'], ['Eerst charts vernieuwen', 'Refresh charts first'], ['Eerst charts lezen', 'Read charts first'],
    ['Alleen beslissende veranderingen of een concreet setup/signaal vragen opnieuw jouw controle.', 'Only material changes or a concrete setup/signal require your review again.'],
    ['Geen inhoudelijke hercontrole nodig', 'No material re-review needed'], ['ongewijzigde controles blijven geldig', 'unchanged reviews remain valid'], ['Zones sluiten logisch op elkaar aan', 'Zones connect logically'], ['Geen lessen voor dit filter.', 'No lessons for this filter.'], ['BLOKKADE', 'BLOCKER'],
    ['Waarneming', 'Observation'], ['Gerichte controle', 'Targeted review'], ['Veiligheidsregels', 'Safety rules'],
    ['grafieken gelezen', 'charts read'], ['actie(s) nodig', 'action(s) needed'], ['actie nodig', 'action needed'],
    ['INSTAP KLAAR', 'ENTRY READY'], ['Verse prijs beschikbaar', 'Fresh price available'],
    ['Grafieklaag gecontroleerd', 'Chart layer reviewed'], ['laag gecontroleerd', 'layer reviewed'],
    ['Voeg gesimuleerde testtrade toe', 'Add simulated test trade'], ['Exporteer mijn data', 'Export my data'],
    ['berichten', 'messages'], ['bericht', 'message'],
    ['MyTradingBot Focus Cockpit: één duidelijke volgende actie per scherm, met alle detail rustig op de achtergrond.', 'MyTradingBot Focus Cockpit: one clear next action per screen, with detail quietly kept in the background.'],
    ['Open de cockpit via de extensie of gebruik je persoonlijke beta-token. Iedere tester heeft een geïsoleerde werkruimte.', 'Open the cockpit from the extension or use your personal beta token. Every tester has an isolated workspace.'],
    ['Afgeronde sluitingsrecords. Een gedeeltelijke sluiting kan meerdere records opleveren; onbekende bronnen blijven zichtbaar als onbekend.', 'Completed close records. A partial close may create multiple records; unknown sources remain visibly marked as unknown.'],
    ['Controleer alleen de zones die jij echt getekend hebt. Open orders, entry/SL/TP-lijnen, signalen en de actuele prijs tellen nooit als zone.', 'Review only the zones you actually drew. Open orders, entry/SL/TP lines, signals and the current-price line never count as zones.'],
    ['Voor normale chartcontrole is geen stop nodig. Alleen bij een concrete trade vul je hieronder eenmalig de instapzone en technische stop in.', 'Normal chart review does not require a stop. Only for a specific trade do you select one entry zone and one technical stop below.'],
    ['Deze samenvatting bevestigt alleen wat je op je charts hebt gecontroleerd. Er wordt geen orderticket aangemaakt en niets automatisch geplaatst.', 'This summary only confirms what you reviewed on your charts. No order ticket is created and nothing is placed automatically.'],
    ['Je werkt in een geïsoleerde paper-werkruimte. Grafieken, controles, testjournal en feedback zijn gescheiden van de eigenaar en andere testers.', 'You are working in an isolated paper workspace. Charts, reviews, the test journal and feedback are separated from the owner and other testers.'],
    ['Beschrijf wat je deed, wat je verwachtte en wat er gebeurde. Deel nooit je token of API-sleutels.', 'Describe what you did, what you expected and what happened. Never share your token or API keys.'],
    ['Testers, diagnose en systeeminformatie staan hier uit de dagelijkse handelsflow.', 'Testers, diagnostics and system information live here, outside the daily trading flow.'],
    ['Bronnen en beleidskeuzes zijn beschikbaar wanneer je ze wilt controleren.', 'Sources and policy choices are available whenever you want to inspect them.'],
    ['Alles staat standaard dicht. Open alleen wat je nodig hebt.', 'Everything is closed by default. Open only what you need.'],
    ['De automatische extensiestand reageert alleen op een bewuste tijdframe- of symboolwissel.', 'Automatic extension mode responds only to an intentional timeframe or symbol change.'],
    ['Open dit alleen om charts te lezen of controleren.', 'Open this only to read or review charts.'],
    ['Ik lees ze automatisch. Jij controleert alleen wat nog openstaat.', 'I read them automatically. You only review what is still open.'],
    ['Open alleen wanneer je de onderliggende lessen wilt nalezen.', 'Open only when you want to revisit the underlying lessons.'],
    ['De lijn verschijnt zodra afgeronde trades in het orderdagboek staan.', 'The line appears once completed trades are in the journal.'],
    ['Grafiek met de cumulatieve netto PnL van de zichtbare sluitingsrecords.', 'Chart of cumulative net PnL for the visible close records.'],
    ['Pas de filters aan of wacht tot de volgende afsluiting automatisch wordt toegevoegd.', 'Adjust the filters or wait for the next close to be added automatically.'],
    ['Ik gebruik je charts, regels, orderdagboek en leskennis. Ik voorspel de markt niet.', 'I use your charts, rules, journal and learning material. I do not predict the market.'],
    ['Ik heb alles al ingevuld. Kijk alleen of trend, zones en signaal kloppen.', 'I already filled everything in. Only check whether the trend, zones and signal are correct.'],
    ['Ik heb de 15m-opbouw op de grafiek gecontroleerd.', 'I reviewed the 15m setup on the chart.'],
    ['Ik heb het 3m-signaal en de lokale kanteling gecontroleerd.', 'I reviewed the 3m signal and local reversal.'],
    ['Ik wil van dit specifieke signaal nu een orderticket voorbereiden.', 'I want to prepare an order ticket for this specific signal now.'],
    ['Synchroniseer dit tijdframe vanuit TradingView.', 'Sync this timeframe from TradingView.'],
    ['Je rekening en eventuele lopende positie worden gecontroleerd.', 'Your account and any open position are being checked.'],
    ['Je marktkaart is compleet', 'Your market map is complete'],
    ['Beveiligde omgeving', 'Secure environment'],
    ['Open jouw cockpit', 'Open your cockpit'],
    ['Verbinding testen', 'Test connection'],
    ['Taal kiezen', 'Choose language'],
    ['Nederlands', 'Dutch'],
    ['Handelscockpit', 'Trading cockpit'],
    ['Focus cockpit', 'Focus cockpit'],
    ['Systeemstatus', 'System status'],
    ['Hoofdnavigatie', 'Main navigation'],
    ['Naar het overzicht', 'Go to overview'],
    ['Je rekening', 'Your account'],
    ['Rekeningwaarde', 'Account value'],
    ['Open posities', 'Open positions'],
    ['Open resultaat', 'Open PnL'],
    ['Huidige BTC-prijs', 'Current BTC price'],
    ['Huidige prijs', 'Current price'],
    ['Prijs controleren', 'Checking price'],
    ['Alleen-lezen via Bybit', 'Read-only via Bybit'],
    ['Alleen-lezen · jij houdt altijd de eindklik', 'Read-only · you always keep the final click'],
    ['Vandaag', 'Today'],
    ['Wat moet ik nu doen?', 'What should I do now?'],
    ['Dagboek', 'Journal'],
    ['Trades en resultaten', 'Trades and results'],
    ['Leren', 'Learn'],
    ['Coach en lessen', 'Coach and lessons'],
    ['Beheer', 'Manage'],
    ['Testers en techniek', 'Testers and technical settings'],
    ['Even je cockpit laden', 'Loading your cockpit'],
    ['Even wachten', 'Please wait'],
    ['Wat nu?', 'What now?'],
    ['Handelsplan', 'Trade plan'],
    ['Richting', 'Direction'],
    ['Instap', 'Entry'],
    ['Stop-loss', 'Stop loss'],
    ['Doelen', 'Targets'],
    ['Max. R', 'Max R'],
    ['Risico', 'Risk'],
    ['Wat je trade nu doet', 'What your trade is doing now'],
    ['Lopende positie', 'Open position'],
    ['Lopende posities laden…', 'Loading open positions…'],
    ['Nog geen positie geladen', 'No position loaded yet'],
    ['Alleen wanneer nodig', 'Only when needed'],
    ['Je 4 charts', 'Your 4 charts'],
    ['Voortgang', 'Progress'],
    ['Volgende stap', 'Next step'],
    ['Wat houdt je tegen?', 'What is holding you back?'],
    ['Ik kijk wat er nog nodig is.', 'Checking what is still needed.'],
    ['Start controle', 'Start review'],
    ['Alleen voor controle', 'For review only'],
    ['Marktkaart en zones', 'Market map and zones'],
    ['Wat ik op je chart zag', 'What I saw on your chart'],
    ['Marktkaart', 'Market map'],
    ['Nog geen lagen gelezen.', 'No layers read yet.'],
    ['Grafieklaag kiezen', 'Choose chart layer'],
    ['Dagcontext', 'Daily context'],
    ['Structuur', 'Structure'],
    ['Opbouw', 'Setup'],
    ['Instap', 'Entry'],
    ['Controleer deze laag', 'Review this layer'],
    ['Bewerk gecontroleerde laag', 'Edit reviewed layer'],
    ['Laatste opname', 'Latest capture'],
    ['Geen grafiek', 'No chart'],
    ['Geen opname', 'No capture'],
    ['Gekozen laag', 'Selected layer'],
    ['Niveaus en zones', 'Levels and zones'],
    ['Rustige werkwijze', 'Calm workflow'],
    ['Dit is alles wat je hoeft te doen', 'This is all you need to do'],
    ['Synchroniseer 1D', 'Sync 1D'],
    ['Synchroniseer 4H', 'Sync 4H'],
    ['Synchroniseer 15m', 'Sync 15m'],
    ['Synchroniseer 3m', 'Sync 3m'],
    ['Dagtrend en grote context.', 'Daily trend and broad context.'],
    ['Structuur en HTF-locatie.', 'Structure and HTF location.'],
    ['Lokale opbouw bij het niveau.', 'Local setup near the level.'],
    ['Eerste lokale kanteling en instap.', 'First local reversal and entry.'],
    ['Voor diagnose', 'For diagnostics'],
    ['Technische details', 'Technical details'],
    ['Jouw afgeronde trades', 'Your completed trades'],
    ['Dagboek en resultaten', 'Journal and results'],
    ['In één oogopslag', 'At a glance'],
    ['Kerncijfers', 'Key metrics'],
    ['Totaal resultaat', 'Total result'],
    ['Winstpercentage', 'Win rate'],
    ['Max. drawdown', 'Max drawdown'],
    ['Datadekking', 'Data coverage'],
    ['Toon meer cijfers en patronen', 'Show more metrics and patterns'],
    ['Winstfactor, verwachting, kosten, grafiek en verdeling', 'Profit factor, expectancy, costs, chart and distribution'],
    ['Bron per record zichtbaar', 'Source visible per record'],
    ['Orderdagboek', 'Trade journal'],
    ['Alle richtingen', 'All directions'],
    ['Alle markten', 'All markets'],
    ['Alle resultaten', 'All results'],
    ['Alle bronnen', 'All sources'],
    ['Alleen Bybit geverifieerd', 'Bybit verified only'],
    ['Alleen legacy-import', 'Legacy imports only'],
    ['Alleen onbekende bron', 'Unknown source only'],
    ['Alleen paper', 'Paper only'],
    ['Alleen testdata', 'Test data only'],
    ['Wis filters', 'Clear filters'],
    ['Exporteer CSV', 'Export CSV'],
    ['Datum', 'Date'],
    ['Bron', 'Source'],
    ['Markt', 'Market'],
    ['Uitstap', 'Exit'],
    ['Netto resultaat', 'Net result'],
    ['Account %', 'Account %'],
    ['Proces', 'Process'],
    ['Geen sluitingsrecords voor dit filter', 'No close records for this filter'],
    ['Toon meer', 'Show more'],
    ['Resultaat door de tijd', 'Results over time'],
    ['Cumulatieve PnL', 'Cumulative PnL'],
    ['Nog geen resultaatgrafiek', 'No results chart yet'],
    ['Patronen', 'Patterns'],
    ['Waar verdien of verlies je?', 'Where do you make or lose money?'],
    ['Proces boven uitkomst', 'Process over outcome'],
    ['Wekelijkse reflectie', 'Weekly reflection'],
    ['Mentor-rapport', 'Mentor report'],
    ['NOG GEEN RAPPORT', 'NO REPORT YET'],
    ['Trade-lessen & deepdives', 'Trade lessons & deep dives'],
    ['Rustig terugkijken', 'Review calmly'],
    ['Leren van je eigen trades', 'Learn from your own trades'],
    ['Bronnen op de achtergrond', 'Sources in the background'],
    ['Waar komen de regels vandaan?', 'Where do the rules come from?'],
    ['Herkomst van je regels', 'Rule provenance'],
    ['Op jouw eigen data', 'Based on your own data'],
    ['Coach', 'Coach'],
    ['Kennisbank', 'Knowledge base'],
    ['Leskennis', 'Learning material'],
    ['Alle lessen', 'All lessons'],
    ['Categorie', 'Category'],
    ['Vraag', 'Question'],
    ['Alleen voor beheer', 'Management only'],
    ['Beheer en techniek', 'Management and technical settings'],
    ['Eigenaarsbeheer', 'Owner controls'],
    ['Nodig een tester uit', 'Invite a tester'],
    ['Naam of omschrijving', 'Name or description'],
    ['Geldig voor', 'Valid for'],
    ['Maak eenmalige uitnodiging', 'Create one-time invitation'],
    ['Openstaande uitnodigingen', 'Open invitations'],
    ['Oude uitnodigingen', 'Past invitations'],
    ['Actieve beta-testers', 'Active beta testers'],
    ['Ingetrokken testers', 'Revoked testers'],
    ['Technische controle', 'Technical checks'],
    ['Systeemaudit', 'System audit'],
    ['API-token', 'API token'],
    ['Tonen', 'Show'],
    ['Verbergen', 'Hide'],
    ['Feedback', 'Feedback'],
    ['Verversen', 'Refresh'],
    ['Uitloggen', 'Log out'],
    ['Stuur feedback', 'Send feedback'],
    ['Verstuur feedback', 'Submit feedback'],
    ['Fout of blokkade', 'Error or blocker'],
    ['Onduidelijke uitleg', 'Unclear explanation'],
    ['Verbeteridee', 'Improvement idea'],
    ['Ontwerp en gebruiksgemak', 'Design and usability'],
    ['Samenvatting laden…', 'Loading summary…'],
    ['Volledige recordinspectie', 'Full record inspection'],
    ['Controle afgerond', 'Review complete'],
    ['Klopt dit?', 'Is this correct?'],
    ['Bekijk marktkaart', 'View market map'],
    ['Begeleide controle', 'Guided review'],
    ['Automatisch ingevuld', 'Filled automatically'],
    ['Trend', 'Trend'],
    ['Prijsbeweging richting de zone', 'Price movement toward the zone'],
    ['Profiel', 'Profile'],
    ['Bereik laag', 'Range low'],
    ['Bereik hoog', 'Range high'],
    ['Notitie', 'Note'],
    ['Type', 'Type'],
    ['Signaal', 'Signal'],
    ['Lokale trend ervoor', 'Prior local trend'],
    ['Signaalprijs', 'Signal price'],
    ['Bewijs', 'Evidence'],
    ['Gekozen instapzone', 'Selected entry zone'],
    ['Technische stop voor dit ticket', 'Technical stop for this ticket'],
    ['Opslaan en volgende laag', 'Save and next layer'],
    ['Annuleren', 'Cancel'],
    ['Ja, klaar', 'Yes, done'],
    ['+ Zone', '+ Zone'],
    ['Steun', 'Support'],
    ['Weerstand', 'Resistance'],
    ['Onbekend', 'Unknown'],
    ['Bereikgrens', 'Range boundary'],
    ['Instapkandidaat', 'Entry candidate'],
    ['Doel', 'Target'],
    ['Stijgend', 'Rising'],
    ['Dalend', 'Falling'],
    ['Zijwaarts', 'Sideways'],
    ['Stijgend richting zone', 'Rising toward zone'],
    ['Dalend richting zone', 'Falling toward zone'],
    ['Zijwaarts richting zone', 'Sideways toward zone'],
    ['Omhoog richting zone', 'Moving up toward zone'],
    ['Omlaag richting zone', 'Moving down toward zone'],
    ['Rotatie binnen bereik', 'Rotation within range'],
    ['Omkering', 'Reversal'],
    ['Uitbraak + hertest', 'Breakout + retest'],
    ['Sweep + herovering', 'Sweep + reclaim'],
    ['Samenpersing', 'Compression'],
    ['Geen setup', 'No setup'],
    ['Geen signaal', 'No signal'],
    ['Lokale kanteling', 'Local reversal'],
    ['Uitbraak', 'Breakout'],
    ['Break-even', 'Break-even'],
    ['Winst', 'Win'],
    ['Verlies', 'Loss'],
    ['CONTROLEREN', 'REVIEW'],
    ['GEBLOKKEERD', 'BLOCKED'],
    ['ONTBREEKT', 'MISSING'],
    ['WACHTEN', 'WAITING'],
    ['LADEN', 'LOADING'],
    ['ACTIEF', 'ACTIVE'],
    ['DATA IN OPBOUW', 'DATA BUILDING'],
    ['DATA COMPLEET', 'DATA COMPLETE'],
    ['BRON CONTROLEREN', 'CHECK SOURCE'],
    ['DATA CONTROLEREN', 'CHECK DATA'],
    ['DATA LADEN', 'LOADING DATA'],
    ['GEAVANCEERD', 'ADVANCED'],
    ['OP DATA GEBASEERD', 'DATA-BASED'],
    ['Openen', 'Open'],
    ['Inklappen', 'Collapse'],
    ['onbekend', 'unknown'],
    ['onvoldoende trades', 'insufficient trades'],
    ['te kleine steekproef', 'sample too small'],
    ['in opbouw', 'building'],
    ['betrouwbaarder', 'more reliable'],
    ['geen data', 'no data'],
    ['records', 'records'],
    ['record', 'record'],
    ['trades', 'trades'],
    ['trade', 'trade'],
    ['lessen', 'lessons'],
    ['les', 'lesson'],
    ['meldingen', 'messages'],
    ['melding', 'message'],
    ['uur', 'hours'],
    ['min', 'min'],
    ['sec', 'sec'],
    ['dagen', 'days'],
    ['dag', 'day'],
  ];
  const NL_EN_V824 = [
    // v8.2.4: every visible dialog, tooltip, live gate and API error has an explicit translation.
    ['Reactie in de zone', 'Reaction in the zone'], ['Liquiditeitsprik zichtbaar', 'Liquidity sweep visible'], ['Herverovering zichtbaar', 'Reclaim visible'], ['Lokale structuur doorbroken', 'Local structure broken'], ['Kaars gesloten', 'Candle closed'], ['Hertest houdt', 'Retest holds'], ['Terugval zichtbaar', 'Pullback visible'], ['Momentum hervat', 'Momentum resumed'],
    ['Bijvoorbeeld: waarom is deze 3m-kanteling nog niet klaar voor een ticket?', 'For example: why is this 3m reversal not ready for a ticket yet?'],
    ['Sluiten', 'Close'], ['Minimaliseer', 'Minimise'], ['Zone verwijderen', 'Remove zone'], ['steun', 'support'], ['weerstand', 'resistance'], ['lokale opbouw', 'local setup'], ['instapzone', 'entry zone'], ['kanteling', 'reversal'], ['hertest', 'retest'], ['herovering', 'reclaim'], ['uitbraak', 'breakout'], ['vervolgbeweging', 'continuation'],
    ['Controlevoortgang', 'Review progress'], ['Grafiek ter controle', 'Chart under review'],
    ['Gesynchroniseerde TradingView-grafiek', 'Synced TradingView chart'], ['Top', 'Top'],
    ['Onderkant', 'Bottom'], ['Tests', 'Tests'], ['Confirmaties', 'Confirmations'], ['Reden', 'Reason'],
    ['Prijs, rol en functie zijn gecontroleerd.', 'Price, role and purpose have been reviewed.'],
    ['Controle opslaan', 'Save review'], ['Markt', 'Market'], ['Functie', 'Purpose'], ['Rol', 'Role'],
    ['Alleen voor deze trade', 'Only for this trade'], ['Wat is op deze grafiek aantoonbaar zichtbaar?', 'What is demonstrably visible on this chart?'],
    ['De waarden zijn automatisch ingevuld. Controleer alleen wat gemarkeerd is.', 'The values were filled automatically. Review only what is highlighted.'],
    ['Bewerk de gecontroleerde laag zonder andere tijdframes te overschrijven.', 'Edit the reviewed layer without overwriting other timeframes.'],
    ['Kies de trend voor deze laag.', 'Choose the trend for this layer.'],
    ['Minimaal één TradingView-zone is vereist.', 'At least one TradingView zone is required.'],
    ['vul geldige boven- en ondergrens in.', 'enter valid upper and lower boundaries.'],
    ['bevestig prijs, rol en functie.', 'confirm price, role and purpose.'],
    ['noteer waarom de zone bestaat.', 'record why the zone exists.'],
    ['Bevestig de 15m-opbouw.', 'Confirm the 15m setup.'], ['Bevestig het 3m-signaal.', 'Confirm the 3m signal.'],
    ['Vul één technische stop in voor dit concrete ticket.', 'Enter one technical stop for this specific ticket.'],
    ['Bij een long moet de technische stop onder de signaalprijs liggen.', 'For a long, the technical stop must be below the signal price.'],
    ['Bij een short moet de technische stop boven de signaalprijs liggen.', 'For a short, the technical stop must be above the signal price.'],
    ['Dit zie ik:', 'This is what I see:'], ['zones over 4 charts.', 'zones across 4 charts.'],
    ['Controleer de samenvatting nog één keer; dit maakt niet automatisch een trade.', 'Review the summary once more; this does not automatically create a trade.'],
    ['Open', 'Open'], ['Controle nodig', 'Review required'], ['Laag ontbreekt', 'Layer missing'],
    ['Reden nog controleren', 'Reason still needs review'], ['Verse prijs beschikbaar', 'Fresh price available'],
    ['Ticket hard geblokkeerd', 'Ticket firmly blocked'], ['bron', 'source'], ['ontbreekt', 'missing'],
    ['controle nodig', 'review required'], ['nog niet duidelijk', 'not clear yet'],
    ['GRAFIEKLAGEN AANVULLEN', 'COMPLETE CHART LAYERS'], ['4/4 GELEZEN', '4/4 READ'],
    ['CONTROLEER KAART', 'REVIEW MAP'], ['PAPER TEST', 'PAPER TEST'], ['WACHT OP 15M', 'WAIT FOR 15M'],
    ['WACHT OP 15M-OPBOUW', 'WAIT FOR 15M SETUP'], ['CONTROLEER 15M-OPBOUW', 'REVIEW 15M SETUP'],
    ['WACHT OP 3M', 'WAIT FOR 3M'], ['WACHT OP 3M-KANTELING', 'WAIT FOR 3M REVERSAL'],
    ['CONTROLEER 3M-SIGNAAL', 'REVIEW 3M SIGNAL'], ['WACHT OP HTF-LOCATIE', 'WAIT FOR HTF LOCATION'],
    ['WACHT OP PRIJS', 'WAIT FOR PRICE'], ['INSTAPKANDIDAAT', 'ENTRY CANDIDATE'],
    ['INSTAP KLAAR', 'ENTRY READY'], ['HANDELSIDEE ONGELDIG', 'TRADE IDEA INVALID'],
    ['THESIS ONGELDIG', 'THESIS INVALID'], ['KIES INSTAPZONE', 'CHOOSE ENTRY ZONE'],
    ['NOG 1 GRAFIEKLAAG', '1 CHART LAYER LEFT'], ['GRAFIEKLAGEN', 'CHART LAYERS'],
    ['Controleer het ticket in TradingView en plaats de order zelf.', 'Review the ticket in TradingView and place the order yourself.'],
    ['Test de volledige workflow, stuur feedback en gebruik alleen gesimuleerde journaldata.', 'Test the full workflow, send feedback and use simulated journal data only.'],
    ['Open TradingView en synchroniseer:', 'Open TradingView and sync:'],
    ['de ontbrekende grafieklaag', 'the missing chart layer'],
    ['Blijf op 3m kijken naar de eerste lokale kanteling bij de HTF-zone.', 'Keep watching 3m for the first local reversal at the HTF zone.'],
    ['Controleer het gevonden 3m-signaal.', 'Review the detected 3m signal.'],
    ['3m-signaal bevestigd. Alleen bij een echte trade kies je nu instapzone en stop.', '3m signal confirmed. Only for a real trade do you now choose an entry zone and stop.'],
    ['Kies voor deze concrete trade een instapzone en één technische stop.', 'Choose an entry zone and one technical stop for this specific trade.'],
    ['Wacht op duidelijke 15m-opbouw bij het HTF-niveau.', 'Wait for a clear 15m setup at the HTF level.'],
    ['Controleer de 15m-opbouw die het brein heeft gezien.', 'Review the 15m setup detected by the engine.'],
    ['Prijs staat nog niet aantoonbaar bij een geldige HTF-zone.', 'Price is not demonstrably at a valid HTF zone yet.'],
    ['Bekijk je charts en volg de gemarkeerde volgende stap.', 'Review your charts and follow the highlighted next step.'],
    ['Synchroniseer de Daily-context', 'Sync the Daily context'], ['Synchroniseer de 4H-structuur', 'Sync the 4H structure'],
    ['Synchroniseer de lokale 15M-opbouw', 'Sync the local 15M setup'],
    ['Synchroniseer de 3M voor de eerste lokale trendkanteling', 'Sync 3M for the first local trend reversal'],
    ['Synchroniseer nog:', 'Still to sync:'],
    ['Een geslaagde synchronisatie telt direct mee; handmatige controle is pas nodig vóór orderticketvoorbereiding.', 'A successful sync counts immediately; manual review is needed only before preparing an order ticket.'],
    ['moet opnieuw worden bekeken:', 'must be reviewed again:'],
    ['de kaart veranderde materieel', 'the map changed materially'], ['de lokale opbouw veranderde', 'the local setup changed'],
    ['het lokale signaal veranderde', 'the local signal changed'],
    ['Er is een nieuwe 15M-opbouw gezien. Controleer alleen deze laag:', 'A new 15M setup was detected. Review only this layer:'],
    ['De 15M-chart is ververst, maar er is nog geen concrete opbouw. Je hoeft hem nu niet handmatig te controleren.', 'The 15M chart was refreshed, but there is no concrete setup yet. You do not need to review it manually now.'],
    ['Er is een nieuw lokaal instapsignaal gezien. Controleer alleen de 3M-trigger:', 'A new local entry signal was detected. Review only the 3M trigger:'],
    ['De 3M-chart beweegt, maar er is nog geen concrete lokale kanteling. Je hoeft hem nu niet handmatig te controleren.', 'The 3M chart is moving, but there is no concrete local reversal yet. You do not need to review it manually now.'],
    ['HTF-context is aanwezig. Open 15m om te zien hoe prijs de zone benadert en de lokale handelsopzet bouwt.', 'HTF context is available. Open 15m to see how price approaches the zone and builds the local setup.'],
    ['De HTF-kaart staat. Op 15m is nog geen lokale omkering, uitbraak, vervolgbeweging of rangerotatie bevestigd. De locatie blijft op wacht; er is niets afgekeurd.', 'The HTF map is ready. No local reversal, breakout, continuation or range rotation has been confirmed on 15m. The location remains on hold; nothing has been rejected.'],
    ['De grafiekanalyse ziet een mogelijke 15m-opbouw. Controleer type, richting en bewijs voordat de 3m-uitvoering wordt vrijgegeven.', 'The chart analysis sees a possible 15m setup. Review its type, direction and evidence before 3m execution is released.'],
    ['De 1D/4H/15m-keten staat. Open 3m om de eerste lokale trendkanteling, liquiditeitsprik met herovering, uitbraak met hertest of vervolgbeweging te lezen.', 'The 1D/4H/15m chain is ready. Open 3m to read the first local reversal, liquidity sweep with reclaim, breakout with retest or continuation.'],
    ['Geen betrouwbare actuele prijs beschikbaar. De kaart blijft intact, maar het ticket blijft dicht.', 'No reliable current price is available. The map remains intact, but the ticket stays locked.'],
    ['3m is gelezen, maar de prijs ligt niet aantoonbaar bij een bevestigde 4H- of 1D-zone.', '3m has been read, but price is not demonstrably at a confirmed 4H or 1D zone.'],
    ['De relevante HTF-zone is expliciet geïnvalideerd.', 'The relevant HTF zone has been explicitly invalidated.'],
    ['De 3m-trigger is bevestigd, maar het gekozen orderticket verwijst niet naar een bestaande instapzone.', 'The 3m trigger is confirmed, but the selected order ticket does not refer to an existing entry zone.'],
    ['R:R-poort geblokkeerd:', 'R:R gate blocked:'], ['maximaal', 'maximum'], ['minimaal', 'minimum'], ['vereist', 'required'],
    ['De lokale 3M-kanteling is gevonden, maar eerst oplossen:', 'The local 3M reversal was found, but first resolve:'],
    ['Het orderticket mag veilig worden voorbereid; de eindklik blijft handmatig.', 'The order ticket may be prepared safely; the final click remains manual.'],
    ['De marktprijs ontbreekt of is te oud. Ticketvoorbereiding is geblokkeerd.', 'The market price is missing or too old. Ticket preparation is blocked.'],
    ['Deze beta-werkruimte is volledig geïsoleerd en bereidt geen echt orderticket voor.', 'This beta workspace is fully isolated and does not prepare a real order ticket.'],
    ['Vul de ontbrekende timeframe-laag aan.', 'Complete the missing timeframe layer.'],
    ['Synchroniseer eerst een grafiek met een geldige prijs', 'First sync a chart with a valid price'],
    ['De laatste grafiekprijs is te oud en Bybit kon niet worden bevestigd', 'The latest chart price is too old and Bybit could not be confirmed'],
    ['Geen geldige positieve marktprijs beschikbaar', 'No valid positive market price is available'],
    ['Instrument komt overeen', 'Instrument matches'], ['Actieve chart', 'Active chart'], ['komt niet overeen met', 'does not match'],
    ['Alleen de eigenaar kan deze beta-instelling wijzigen', 'Only the owner can change this beta setting'],
    ['Niet geautoriseerd of beta-toegang ingetrokken', 'Not authorised or beta access revoked'],
    ['Te veel pogingen; probeer later opnieuw', 'Too many attempts; try again later'],
    ['Uitnodiging niet gevonden of al ingetrokken', 'Invitation not found or already revoked'],
    ['Tester niet gevonden', 'Tester not found'], ['Beschrijf je feedback iets uitgebreider', 'Describe your feedback in a little more detail'],
    ['Eigenaarsdata kan niet via deze beta-route worden gewist', 'Owner data cannot be deleted through this beta route'],
    ['Gebruik deze route alleen in beta-testmodus', 'Use this route only in beta test mode'],
    ['ongeldig timeframe', 'invalid timeframe'], ['Nog geen draft voor deze timeframe', 'No draft for this timeframe yet'],
    ['Nog geen chartpreview voor deze timeframe', 'No chart preview for this timeframe yet'],
    ['Gebruik exact 1D, 4H, 15M of 3M', 'Use exactly 1D, 4H, 15M or 3M'],
    ['Geen chartdraft gevonden voor deze asset/timeframe', 'No chart draft found for this asset/timeframe'],
    ['Deze chartversie is niet meer de nieuwste voor dit timeframe. Synchroniseer of open de review opnieuw.', 'This chart version is no longer the latest for this timeframe. Sync or reopen the review.'],
    ['Te veel coachvragen; probeer later opnieuw', 'Too many coach questions; try again later'],
    ['vraag ontbreekt', 'question is missing'], ['Geen geldig antwoord', 'No valid response'],
    ['De cockpit reageerde niet op tijd. Probeer opnieuw.', 'The cockpit did not respond in time. Try again.'],
    ['Preview niet beschikbaar', 'Preview unavailable'], ['Nog geen succesvolle accountcontrole vastgelegd.', 'No successful account check recorded yet.'],
    ['Laatste succesvolle controle:', 'Last successful check:'], ['BYBIT-WATCHER ACTIEF', 'BYBIT WATCHER ACTIVE'],
    ['BYBIT NIET GECONFIGUREERD', 'BYBIT NOT CONFIGURED'], ['WATCHER CONTROLEREN', 'CHECK WATCHER'],
    ['Gemengde bronnen', 'Mixed sources'], ['bronrecord(s) onbekend', 'source record(s) unknown'],
    ['Historische equitydekking is onvolledig.', 'Historical equity coverage is incomplete.'],
    ['Nog onvoldoende trades', 'Not enough trades yet'], ['∞ · nog geen verliesrecord', '∞ · no losing record yet'],
    ['Geen lessen voor dit filter.', 'No lessons for this filter.'], ['Nog geen deepdives. Na een afgeronde trade verschijnt hier de procesles.', 'No deep dives yet. A process lesson will appear here after a completed trade.'],
    ['Nog geen betrouwbare zones gevonden.', 'No reliable zones found yet.'],
    ['Nog geen systeemmeldingen.', 'No system messages yet.'], ['Nog geen openstaande uitnodigingen.', 'No open invitations yet.'],
    ['Nog geen oude uitnodigingen.', 'No past invitations yet.'], ['Geen actieve beta-testers.', 'No active beta testers.'],
    ['Nog geen ingetrokken testers.', 'No revoked testers yet.'],
    ['Beslisketen', 'Decision chain'], ['Relatie tussen je 4 charts', 'Relationship between your 4 charts'], ['Aanvullende prestatiecijfers', 'Additional performance metrics'], ['Waar verdien of verlies je', 'Where do you make or lose money'],
    ['Trek uitnodiging in', 'Revoke invitation'], ['Bijvoorbeeld: broer Mark', 'For example: brother Mark'], ['Live eigenaar', 'Live owner'],
    ['Verbinding tijdelijk onderbroken', 'Connection temporarily interrupted'],
    ['De verbinding is tijdelijk onderbroken', 'The connection is temporarily interrupted'],
    ['Probeer opnieuw', 'Try again'], ['Wat je kunt doen', 'What you can do'],
  ];
  const NL_EN = [...NL_EN_EXTRA, ...NL_EN_BASE, ...NL_EN_V824].sort((a, b) => b[0].length - a[0].length);
  const NL_EN_DIRECT = new Map(NL_EN);
  const NL_EN_PATTERNS = [
    [/^Je (LONG|SHORT) (.+?) loopt$/u, 'Your $1 $2 is open'],
    [/^Open resultaat (.+?) · instap (.+?) · huidige prijs (.+?)\.$/u, 'Open PnL $1 · entry $2 · current price $3.'],
    [/^(\d+) open · (.+)$/u, '$1 open · $2'],
    [/^(\d+)\/4 gelezen · geen hercontrole nodig$/u, '$1/4 read · no re-review needed'],
    [/^(\d+)\/4 gelezen · (\d+) gerichte controles?$/u, '$1/4 read · $2 targeted review(s)'],
    [/^(\d+) actie\(s\) nodig$/u, '$1 action(s) needed'],
    [/^(\d+) gekoppelde zones? aan (.+)$/u, '$1 linked zone(s) to $2'],
    [/^(\d+) zones · (.+)$/u, '$1 zones · $2'],
    [/^(\d+) van (\d+) records met historische rekeningwaarde$/u, '$1 of $2 records with historical account value'],
    [/^(\d+) van (\d+) gefilterde trades · (\d+) totaal$/u, '$1 of $2 filtered trades · $3 total'],
    [/^Onvoldoende steekproef: (\d+) trades? is een te kleine steekproef\. De cijfers zijn zichtbaar, maar nog niet betrouwbaar genoeg om je regels te veranderen\.$/u, 'Insufficient sample: $1 trade(s) is too small a sample. The figures are visible, but not yet reliable enough to change your rules.'],
    [/^Bron: gemengde bronnen · (\d+)\/(\d+) Bybit-geverifieerd · Dekking: (\d+)\/(\d+) met historische equity · bijgewerkt (.+)\.$/u, 'Source: mixed sources · $1/$2 Bybit verified · Coverage: $3/$4 with historical equity · updated $5.'],
    [/^(\d+) lessen verwerkt · laatste bron (.+)\.$/u, '$1 lessons processed · latest source $2.'],
    [/^(open|verlopen|gebruikt|ingetrokken) · geldig tot (.+) · (\d+) gebruik\(en\) over$/u, '$1 · valid until $2 · $3 use(s) remaining'],
    [/^Controleer nu (.+?); daarna opent automatisch de volgende controle\.$/u, 'Review $1 now; the next review will then open automatically.'],
    [/^(.+?) · (1D|4H|15M|3M) controleren$/u, '$1 · $2 review'],
    [/^Alleen (.+?) moet opnieuw worden bekeken: (.+?)\. Ongewijzigde charts blijven goedgekeurd\.$/u, 'Only $1 must be reviewed again: $2. Unchanged charts remain approved.'],
    [/^Er is een nieuwe 15M-opbouw gezien\. Controleer alleen deze laag: (.+?)\.$/u, 'A new 15M setup was detected. Review only this layer: $1.'],
    [/^Er is een nieuw lokaal instapsignaal gezien\. Controleer alleen de 3M-trigger: (.+?)\.$/u, 'A new local entry signal was detected. Review only the 3M trigger: $1.'],
    [/^R:R-poort geblokkeerd: maximaal ([0-9.]+)R, minimaal ([0-9.]+)R vereist\.$/u, 'R:R gate blocked: maximum $1R, minimum $2R required.'],
    [/^3m (.+?) bevestigd bij (.+?) steun\. Het orderticket mag veilig worden voorbereid; de eindklik blijft handmatig\.$/u, '3m $1 confirmed at $2 support. The order ticket may be prepared safely; the final click remains manual.'],
    [/^3m (.+?) bevestigd bij (.+?) weerstand\. Het orderticket mag veilig worden voorbereid; de eindklik blijft handmatig\.$/u, '3m $1 confirmed at $2 resistance. The order ticket may be prepared safely; the final click remains manual.'],
    [/^Zone (\d+): kies steun of weerstand\.$/u, 'Zone $1: choose support or resistance.'],
    [/^Zone (\d+): vul geldige boven- en ondergrens in\.$/u, 'Zone $1: enter valid upper and lower boundaries.'],
    [/^Zone (\d+): bevestig prijs, rol en functie\.$/u, 'Zone $1: confirm price, role and purpose.'],
    [/^Zone (\d+): noteer waarom de zone bestaat\.$/u, 'Zone $1: record why the zone exists.'],
    [/^Dit zie ik: (\d+) zones over 4 charts\. Controleer de samenvatting nog één keer; dit maakt niet automatisch een trade\.$/u, 'This is what I see: $1 zones across 4 charts. Review the summary once more; this does not automatically create a trade.'],
    [/^(\d+) zones? · (Gecontroleerd|Open)$/u, '$1 zone(s) · $2'],
  ];
  const originalText = new WeakMap();
  const originalAttrs = new WeakMap();
  let languageObserver = null;
  let languageTimer = null;
  let languageApplying = false;

  function preserveOuterWhitespace(source, translated) {
    const leading = source.match(/^\s*/u)?.[0] || '';
    const trailing = source.match(/\s*$/u)?.[0] || '';
    return `${leading}${translated}${trailing}`;
  }

  function replaceDutchFragments(value) {
    let text = String(value ?? '');
    const protectedTranslations = [];
    for (const [source, target] of NL_EN) {
      const escaped = source.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const pattern = /^[\p{L}\p{N}_-]+$/u.test(source)
        ? new RegExp(`(?<![\\p{L}\\p{N}_-])${escaped}(?![\\p{L}\\p{N}_-])`, 'gu')
        : new RegExp(escaped, 'gu');
      text = text.replace(pattern, () => {
        const index = protectedTranslations.push(target) - 1;
        return `\uE000${index}\uE001`;
      });
    }
    return text.replace(/\uE000(\d+)\uE001/gu, (_, index) => protectedTranslations[Number(index)] || '');
  }

  function translateDutch(value) {
    const sourceText = String(value ?? '');
    const trimmed = sourceText.trim();
    if (!trimmed) return sourceText;
    const direct = NL_EN_DIRECT.get(trimmed);
    if (direct != null) return preserveOuterWhitespace(sourceText, direct);
    for (const [pattern, replacement] of NL_EN_PATTERNS) {
      if (pattern.test(trimmed)) {
        const translated = replaceDutchFragments(trimmed.replace(pattern, replacement));
        return preserveOuterWhitespace(sourceText, translated);
      }
    }
    return replaceDutchFragments(sourceText);
  }

  function currentLocale() { return state.language === 'en' ? 'en-GB' : 'nl-NL'; }

  function translateTextNode(node) {
    const current = node.nodeValue || '';
    const previous = originalText.get(node);
    const previousTranslation = previous == null ? null : translateDutch(previous);
    if (previous == null || (current !== previous && current !== previousTranslation)) originalText.set(node, current);
    const original = originalText.get(node) || '';
    const next = state.language === 'en' ? translateDutch(original) : original;
    if (current !== next) node.nodeValue = next;
  }

  function translateAttributes(node) {
    const names = ['placeholder', 'title', 'aria-label'];
    let values = originalAttrs.get(node);
    if (!values) { values = {}; originalAttrs.set(node, values); }
    for (const name of names) {
      if (!node.hasAttribute?.(name)) continue;
      const current = node.getAttribute(name) || '';
      const previous = values[name];
      const previousTranslation = previous == null ? null : translateDutch(previous);
      if (previous == null || (current !== previous && current !== previousTranslation)) values[name] = current;
      const original = values[name] || '';
      const next = state.language === 'en' ? translateDutch(original) : original;
      if (current !== next) node.setAttribute(name, next);
    }
  }

  function observeLanguage() {
    languageObserver?.observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['placeholder', 'title', 'aria-label'] });
  }

  function applyLanguage(root = document) {
    if (languageApplying) return;
    languageApplying = true;
    languageObserver?.disconnect();
    try {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      let node;
      while ((node = walker.nextNode())) {
        if (node.parentElement?.closest('script,style')) continue;
        translateTextNode(node);
      }
      root.querySelectorAll?.('[placeholder],[title],[aria-label]').forEach(translateAttributes);
      document.documentElement.lang = state.language;
      document.title = 'MyTradingBot Focus Cockpit UX v8.4.0';
      document.querySelector('meta[name="description"]')?.setAttribute('content', state.language === 'en'
        ? 'MyTradingBot Focus Cockpit: position first, one clear next step, with technical detail quietly tucked away.'
        : 'MyTradingBot Focus Cockpit: positie eerst, één duidelijke volgende stap en alle techniek rustig ingeklapt.');
      $$('[data-language]').forEach((button) => {
        const active = button.dataset.language === state.language;
        button.classList.toggle('active', active);
        button.setAttribute('aria-pressed', String(active));
      });
    } finally {
      languageApplying = false;
      observeLanguage();
    }
  }

  function setLanguage(language, { persist = true, rerender = true, broadcast = true } = {}) {
    state.language = language === 'en' ? 'en' : 'nl';
    if (persist) localStorage.setItem(LANGUAGE_KEY, state.language);
    if (broadcast) window.postMessage({ source:'mytradingbot-dashboard', action:'languageChanged', language:state.language }, location.origin);
    if (rerender && state.overview) renderAll();
    applyLanguage();
  }

  function startLanguageObserver() {
    if (languageObserver) return;
    languageObserver = new MutationObserver(() => {
      if (languageApplying) return;
      clearTimeout(languageTimer);
      languageTimer = setTimeout(() => applyLanguage(), 0);
    });
    observeLanguage();
  }

  const state = {
    token: '',
    overview: null,
    asset: 'BTC',
    timeframe: '1D',
    pollTimer: null,
    reviewMode: 'draft',
    reviewSource: null,
    previewUrl: null,
    reviewPreviewUrl: null,
    journalLimit: 12,
    guidedReview: false,
    activeView: 'today',
    focusAction: 'none',
    positionModeInitialized: false,
    dayStart: null,
    dayStartStateId: null,
    language: 'nl',
    expertMode: false
  };

  const $ = (id) => document.getElementById(id);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const clear = (node) => { while (node && node.firstChild) node.removeChild(node.firstChild); return node; };
  const asArray = (value) => Array.isArray(value) ? value : [];
  const clone = (value) => JSON.parse(JSON.stringify(value || {}));
  const finite = (value) => {
    if (value === null || value === undefined || String(value).trim() === '') return null;
    const number = Number(String(value).replace(',', '.'));
    return Number.isFinite(number) ? number : null;
  };
  const create = (tag, className = '', text = '') => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== '') node.textContent = state.language === 'en' ? translateDutch(text) : text;
    return node;
  };
  const format = (value, digits = 2) => {
    const number = finite(value);
    return number === null ? '—' : number.toLocaleString(currentLocale(), { maximumFractionDigits: digits, minimumFractionDigits: 0 });
  };
  const money = (value) => {
    const number = finite(value);
    return number === null ? '—' : number.toLocaleString(currentLocale(), { style: 'currency', currency: 'USD', maximumFractionDigits: 2 });
  };
  const age = (seconds) => {
    const value = finite(seconds);
    if (value === null) return state.language === 'en' ? 'unknown' : 'onbekend';
    if (value < 60) return `${Math.round(value)} sec`;
    if (value < 3600) return `${Math.round(value / 60)} min`;
    return `${Math.round(value / 3600)} ${state.language === 'en' ? 'hours' : 'uur'}`;
  };
  const dateText = (value) => {
    if (!value) return '—';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString(currentLocale(), { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  };


  const positionEntry = (position) => finite(position?.entry ?? position?.entry_price ?? position?.avgPrice ?? position?.avg_entry_price);
  const positionMark = (position) => finite(position?.mark ?? position?.mark_price ?? position?.markPrice) ?? finite(state.overview?.latest?.price_status?.price) ?? finite(state.overview?.latest?.price);
  const positionPnl = (position) => finite(position?.pnl ?? position?.unrealised_pnl ?? position?.unrealisedPnl ?? position?.unrealizedPnl) || 0;
  const positionStop = (position) => finite(position?.stop_loss ?? position?.stopLoss);
  const positionTarget = (position) => finite(position?.take_profit ?? position?.takeProfit);
  const openPositions = () => asArray(state.overview?.account?.positions).filter((position) => (finite(position?.size) || 0) !== 0);
  const totalOpenPnl = () => openPositions().reduce((sum, position) => sum + positionPnl(position), 0);
  const friendlySide = (value) => String(value || '').toLowerCase() === 'sell' || String(value || '').toLowerCase() === 'short' ? 'SHORT' : 'LONG';


  function chartFreshness(health = {}) {
    const layers = asArray(health.layers);
    const staleLayers = layers.filter((row) => row?.synced && row?.fresh === false);
    const oldestHours = staleLayers.reduce((max, row) => Math.max(max, finite(row?.age_hours) || 0), 0);
    return { stale: health.fresh === false || staleLayers.length > 0, staleLayers, oldestHours };
  }

  function friendlyFailure(error) {
    const kind = errorKind(error?.message || error);
    return {
      title: ui(`error.${kind}.title`),
      reason: ui(`error.${kind}.reason`),
      next: ui(`error.${kind}.next`),
      actionLabel: ui('error.retry'),
    };
  }

  function deriveUserState() {
    const overview = state.overview || {};
    const latest = overview.latest || {};
    const gate = latest.execution_gate || {};
    const health = overview.stack_health || {};
    const positions = openPositions();
    if (positions.length) {
      const position = positions[0];
      const pnl = positionPnl(position);
      return { kind:'position', tone:pnl >= 0 ? 'good' : 'wait', badge:ui('state.position.badge'),
        title:ui('state.position.title',{side:friendlySide(position.side),symbol:position.symbol || (state.language==='en'?'position':'positie')}),
        reason:ui('state.position.reason',{pnl:money(pnl),entry:format(positionEntry(position),8),price:format(positionMark(position),8)}),
        next:ui('state.position.next'), action:'position', actionLabel:ui('state.position.action') };
    }
    const synced = Number(health.synced_count || 0);
    const review = asArray(latest.review_timeframes || health.review_timeframes);
    const blockingReview = asArray(latest.blocking_review_timeframes);
    const missing = asArray(latest.missing_timeframes || health.missing_timeframes);
    const freshness = chartFreshness(health);
    if (synced < 4) {
      const remaining = 4 - synced;
      return { kind:'charts', tone:'wait', badge:ui('state.charts.badge',{count:synced}), title:ui('state.charts.title'),
        reason:ui('state.charts.reason',{remaining,plural:remaining===1?'':'s',missing:missing.join(', ') || (state.language==='en'?'open TradingView and read the missing chart':'open TradingView en lees de ontbrekende chart')}),
        next:ui('state.charts.next'), action:'charts', actionLabel:ui('state.charts.action') };
    }
    if (freshness.stale) {
      const labels = freshness.staleLayers.map((row) => row.timeframe).filter(Boolean).join(', ');
      const timeText = freshness.oldestHours >= 1 ? `${format(freshness.oldestHours,1)} ${state.language==='en'?'hours':'uur'}` : (state.language==='en'?'too old':'te oud');
      return { kind:'stale', tone:'wait', badge:ui('state.stale.badge'), title:ui('state.stale.title'),
        reason:ui('state.stale.reason',{layers:labels || (state.language==='en'?'At least one chart':'Minstens één chart'),age:timeText}),
        next:ui('state.stale.next'), action:'charts', actionLabel:ui('state.stale.action') };
    }
    if (blockingReview.length || ['REVIEW_STACK','REVIEW_15M_SETUP','REVIEW_3M_TRIGGER'].includes(String(gate.status || ''))) {
      const next = blockingReview[0] || review[0] || (state.language==='en'?'the changed chart':'de gewijzigde chart');
      return { kind:'review', tone:'wait', badge:ui('state.review.badge'), title:ui('state.review.title',{timeframe:next}),
        reason:executionReason(latest),
        next:ui('state.review.next'), action:'review', actionLabel:ui('state.review.action',{timeframe:next}) };
    }
    if (['COMMITMENT_DAY_STOP','COMMITMENT_MAX_POSITION','REVENGE_COOLDOWN'].includes(String(gate.status || ''))) return {
      kind:'waiting', tone:gate.status === 'COMMITMENT_DAY_STOP' ? 'bad' : 'wait',
      badge:state.language === 'en' ? 'COMMITMENT LOCKED' : 'COMMITMENT VERGRENDELD',
      title:gate.status === 'COMMITMENT_DAY_STOP'
        ? (state.language === 'en' ? 'Your day stop is active' : 'Je dagstop is actief')
        : gate.status === 'REVENGE_COOLDOWN'
          ? (state.language === 'en' ? 'First cool down' : 'Eerst afkoelen')
          : (state.language === 'en' ? 'One position is enough' : 'Eén positie is genoeg'),
      reason:executionReason(latest),
      next:state.language === 'en' ? 'The gate cannot be loosened today.' : 'Dit hek kan vandaag niet losser.',
      action:'refresh', actionLabel:state.language === 'en' ? 'Refresh status' : 'Status verversen' };
    const streak = overview.discipline?.streak || {};
    const dayStartReady = !streak.today_complete && !state.dayStart && dayStartAvailability().ready;
    if (dayStartReady) return { kind:'daystart', tone:'neutral', badge:ui('state.daystart.badge'), title:ui('state.daystart.title'),
      reason:ui('state.daystart.reason'), next:ui('state.daystart.next'), action:'daystart', actionLabel:ui('state.daystart.action') };
    if (gate.status === 'ENTRY_READY') return { kind:'ticket', tone:'good', badge:ui('state.ticket.badge'), title:ui('state.ticket.title'),
      reason:executionReason(latest),
      next:ui('state.ticket.next'), action:'ticket', actionLabel:ui('state.ticket.action') };
    if (['WAIT_PRICE','WAIT_HTF_LOCATION','ENTRY_CANDIDATE','WAIT_15M','WAIT_15M_SETUP','WAIT_3M','WAIT_3M_TURN','REVIEW_15M_SETUP','REVIEW_3M_TRIGGER','TRIGGER_CONFIRMED','TICKET_INPUT_REQUIRED'].includes(String(gate.status || ''))) return {
      kind:'waiting', tone:'wait', badge:ui('state.wait.badge'), title:ui('state.wait.title'),
      reason:executionReason(latest),
      next:ui('state.wait.next'), action:'refresh', actionLabel:ui('state.wait.action') };
    return { kind:'idle', tone:'neutral', badge:ui('state.idle.badge'), title:ui('state.idle.title'),
      reason:executionReason(latest),
      next:ui('state.idle.next'), action:'refresh', actionLabel:ui('state.idle.action') };
  }

  function switchView(view, { persist = true } = {}) {
    const allowed = ['today','journal','learn','manage'];
    state.activeView = allowed.includes(view) ? view : 'today';
    const main = $('overzicht');
    if (main) main.dataset.activeView = state.activeView;
    $$('[data-view-section]').forEach((section) => { section.hidden = section.dataset.viewSection !== state.activeView; });
    $$('#appNav [data-view]').forEach((button) => {
      const active = button.dataset.view === state.activeView;
      button.classList.toggle('active', active);
      if (active) button.setAttribute('aria-current','page'); else button.removeAttribute('aria-current');
    });
    if (persist) localStorage.setItem(VIEW_KEY, state.activeView);
    try { window.scrollTo({ top: 0, behavior: 'smooth' }); } catch (_) {}
  }

  function handleFocusAction() {
    const action = state.focusAction;
    if (action === 'position') {
      switchView('today');
      const panel = $('positionPanel');
      if (panel) { panel.open = true; updateCollapseText(panel); }
      $('positionSection')?.scrollIntoView({ behavior:'smooth', block:'start' });
      return;
    }
    if (action === 'daystart') {
      switchView('today');
      const panel = $('dayStartCard');
      if (panel) { panel.open = true; updateCollapseText(panel); panel.scrollIntoView({ behavior:'smooth', block:'start' }); }
      requestDayStart();
      return;
    }
    if (action === 'charts' || action === 'review' || action === 'stale') {
      switchView('today');
      const panel = $('chartWorkflowPanel');
      if (panel) { panel.open = true; updateCollapseText(panel); panel.scrollIntoView({ behavior:'smooth', block:'start' }); }
      if (action === 'review') setTimeout(startGuidedReview, 250);
      return;
    }
    if (action === 'ticket') {
      const panel = $('chartWorkflowPanel');
      if (panel) { panel.open = true; updateCollapseText(panel); panel.scrollIntoView({ behavior:'smooth', block:'start' }); }
      return;
    }
    loadOverview().catch(() => {});
  }

  async function api(path, options = {}) {
    if (DEMO) return demoApi(path, options);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), options.timeout || 30000);
    try {
      const response = await fetch(path, {
        method: options.method || 'GET',
        cache: 'no-store',
        credentials: 'omit',
        headers: {
          Accept: options.blob ? '*/*' : 'application/json',
          'Content-Type': 'application/json',
          'X-MyTradingBot-Token': state.token
        },
        body: options.body ? JSON.stringify(options.body) : undefined,
        signal: controller.signal
      });
      if (options.blob) {
        if (!response.ok) throw new Error(`Preview niet beschikbaar (HTTP ${response.status})`);
        return response.blob();
      }
      let data;
      try { data = await response.json(); }
      catch { throw new Error(`Geen geldig antwoord (HTTP ${response.status})`); }
      if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
      return data;
    } catch (error) {
      if (error && error.name === 'AbortError') throw new Error('De cockpit reageerde niet op tijd. Probeer opnieuw.');
      throw error;
    } finally { clearTimeout(timeout); }
  }

  function layerBundle(tf) {
    const asset = state.asset;
    const confirmed = state.overview?.market_stack?.assets?.[asset]?.layers?.[tf] || null;
    const draft = state.overview?.chart_drafts?.assets?.[asset]?.layers?.[tf] || null;
    const health = asArray(state.overview?.stack_health?.layers).find((row) => row.timeframe === tf) || null;
    const source = health?.review_needed && draft ? draft : (confirmed || draft);
    return { confirmed, draft, health, source };
  }

  function gateTone(status) {
    const value = String(status || '');
    if (value === 'ENTRY_READY') return 'good';
    if (/INVALID|BLOCK|ERROR/.test(value)) return 'bad';
    return 'wait';
  }

  function gateLabel(status) {
    const key = `gate.${String(status || 'DEFAULT')}`;
    const value = ui(key);
    return value === key ? String(status || ui('gate.DEFAULT')).replaceAll('_',' ') : value;
  }

  function nextActionText(latest) {
    const gate = latest?.execution_gate || {};
    const missing = asArray(latest?.missing_timeframes);
    const review = asArray(latest?.review_timeframes);
    if (gate.status === 'ENTRY_READY') return ui('next.ENTRY_READY');
    if (gate.status === 'STACK_SYNCED' || gate.status === 'REVIEW_STACK') return ui('next.REVIEW',{timeframe:review[0] || (state.language==='en'?'the next layer':'de eerstvolgende laag')});
    if (gate.status === 'PAPER_MODE') return ui('next.PAPER_MODE');
    if (gate.status === 'WAIT_SYNC') return ui('next.WAIT_SYNC',{missing:missing.join(', ') || (state.language==='en'?'the missing chart layer':'de ontbrekende grafieklaag')});
    if (gate.status === 'WAIT_3M_TURN') return ui('next.WAIT_3M_TURN');
    if (gate.status === 'REVIEW_3M_TRIGGER') return ui('next.REVIEW_3M_TRIGGER');
    if (gate.status === 'TRIGGER_CONFIRMED') return ui('next.TRIGGER_CONFIRMED');
    if (gate.status === 'TICKET_INPUT_REQUIRED') return ui('next.TICKET_INPUT_REQUIRED');
    if (gate.status === 'WAIT_15M_SETUP') return ui('next.WAIT_15M_SETUP');
    if (gate.status === 'REVIEW_15M_SETUP') return ui('next.REVIEW_15M_SETUP');
    if (gate.status === 'WAIT_HTF_LOCATION') return ui('next.WAIT_HTF_LOCATION');
    return executionReason(latest) || ui('next.DEFAULT');
  }

  function renderHeader() {
    const overview = state.overview || {};
    const health = overview.stack_health || {};
    const account = overview.account || {};
    const userState = deriveUserState();
    $('headerLayers').textContent = `${health.synced_count || 0}/4`;
    $('headerVerified').textContent = `${health.confirmed_count || 0}/4`;
    $('headerUpdated').textContent = dateText(overview.updated_at);
    $('headerWorkspace').textContent = overview.principal?.display_name || '—';
    $('headerBalance').textContent = money(account.equity);
    $('headerStatus').textContent = userState.kind === 'position' ? (state.language === 'en' ? 'Position open' : 'Positie loopt') : userState.title;
    const headerStatusBox = $('headerStatus')?.parentElement;
    if (headerStatusBox) {
      const checkedAt = overview.updated_at ? new Date(overview.updated_at).toLocaleString(currentLocale(), { dateStyle:'medium', timeStyle:'short' }) : '—';
      headerStatusBox.title = state.language === 'en'
        ? `Account ${money(account.equity)} · checked ${checkedAt}`
        : `Rekening ${money(account.equity)} · gecontroleerd ${checkedAt}`;
    }
    $('footerVersion').textContent = `UX v${VERSION}`;
    $('brainVersion').textContent = `v${overview.version || MOTOR_VERSION}`;

    const assets = new Set([state.asset, ...Object.keys(overview.market_stack?.assets || {}), ...Object.keys(overview.chart_drafts?.assets || {})]);
    const select = $('assetSelect');
    clear(select);
    [...assets].filter(Boolean).sort().forEach((asset) => {
      const option = create('option'); option.value = asset; option.textContent = `${asset}USDT`; option.selected = asset === state.asset; select.append(option);
    });
  }

  function renderFocus() {
    const latest = state.overview?.latest || {};
    const account = state.overview?.account || {};
    const view = deriveUserState();
    state.focusAction = view.action;
    $('decisionCard').className = `panel focus-card ${view.tone}`;
    $('focusTitle').textContent = view.title;
    $('decisionBadge').textContent = view.badge;
    $('decisionBadge').className = `badge ${view.tone}`;
    $('decisionReason').textContent = view.reason;
    $('nextAction').querySelector('strong').textContent = view.next;
    $('focusActionButton').textContent = view.actionLabel;
    $('focusActionButton').disabled = false;

    const setup = latest.setup;
    const showPlan = Boolean(setup && ['ticket','waiting'].includes(view.kind));
    $('tradePlan').classList.toggle('hidden', !showPlan);
    if (showPlan) {
      $('planDirection').textContent = String(setup.direction || '—').toUpperCase();
      $('planEntry').textContent = format(setup.entry, 8);
      $('planStop').textContent = format(setup.stop_loss, 8);
      $('planTargets').textContent = asArray(setup.take_profits).slice(0, 3).map((value) => format(value, 8)).join(' · ') || '—';
      $('planRr').textContent = setup.rr_max == null ? '—' : `${format(setup.rr_max, 2)}R`;
      $('planRisk').textContent = setup.risk_pct == null ? '—' : `${format(setup.risk_pct, 2)}%`;
    }

    $('accountEquity').textContent = money(account.equity);
    $('accountPositions').textContent = String(openPositions().length);
    const pnl = totalOpenPnl();
    $('accountOpenPnl').textContent = money(pnl);
    $('accountOpenPnl').classList.toggle('good', pnl > 0);
    $('accountOpenPnl').classList.toggle('bad', pnl < 0);
    const priceState = latest.price_status || {};
    const currentPrice = finite(priceState.price ?? latest.price);
    const priceValid = Boolean(priceState.ok !== false && currentPrice && currentPrice > 0 && !priceState.stale);
    $('accountPrice').textContent = priceValid ? format(currentPrice, 2) : ui('price.notFresh');
    $('accountPrice').classList.toggle('bad', !priceValid);
    $('accountPriceMeta').textContent = priceValid ? `${priceSourceLabel(priceState.source)} · ${age(priceState.age_seconds)}` : (priceState.reason ? ui('price.unavailable_reason') : ui('price.rechecking')); 
    $('accountFreshness').textContent = account.mode === 'paper' ? 'OEFENMODUS' : account.equity_fresh ? 'NET GECHECKT' : 'CONTROLEREN';
    $('accountFreshness').className = `badge ${account.mode === 'paper' ? 'wait' : account.equity_fresh ? 'good' : 'wait'}`;
  }

  function renderDiscipline() {
    const discipline = state.overview?.discipline || {};
    const score = finite(discipline.score);
    const band = String(discipline.score_band || 'insufficient');
    const bandLabels = state.language === 'en'
      ? {strong:'Strong process',steady:'Steady process',building:'Building',earn_back:'Earn-back',insufficient:'More process data needed'}
      : {strong:'Sterk proces',steady:'Stabiel proces',building:'In opbouw',earn_back:'Earn-back',insufficient:'Meer procesdata nodig'};
    const tone = band === 'strong' ? 'good' : band === 'steady' ? 'good' : band === 'building' ? 'wait' : band === 'earn_back' ? 'neutral' : 'neutral';
    $('disciplineScore').textContent = score === null ? '—' : `${Math.round(score)}`;
    $('disciplineScoreLabel').textContent = bandLabels[band] || bandLabels.insufficient;
    $('disciplineBadge').textContent = (bandLabels[band] || bandLabels.insufficient).toUpperCase();
    $('disciplineBadge').className = `badge ${tone}`;

    const streak = discipline.streak || {};
    const current = Number(streak.current || 0);
    $('disciplineStreak').textContent = `${current} ${state.language === 'en' ? (current === 1 ? 'day' : 'days') : (current === 1 ? 'dag' : 'dagen')}`;
    const streakMessages = state.language === 'en'
      ? {earned_today:'Today counts. Keep the process simple.',available_today:`Your ${current}-day streak is still active. Earn today with your day start or a conscious no-trade day.`,earn_back:'Earn-back: one deliberate process action today starts your streak again.',start:'Start today with your day start or a conscious watching day.'}
      : {earned_today:'Vandaag telt mee. Houd het proces eenvoudig.',available_today:`Je streak van ${current} dagen staat nog. Verdien vandaag met je dagstart of een bewuste no-trade-dag.`,earn_back:'Earn-back: één bewuste procesactie vandaag start je streak opnieuw.',start:'Start vandaag met je dagstart of een bewuste kijkdag.'};
    $('disciplineStreakMeta').textContent = streakMessages[streak.status] || streakMessages.start;

    const rules = discipline.rules || {};
    $('disciplineRules').textContent = rules.pct == null ? '—' : `${format(rules.pct, 0)}%`;
    $('disciplineRulesMeta').textContent = rules.count
      ? (state.language === 'en' ? `${rules.followed}/${rules.count} assessed trades` : `${rules.followed}/${rules.count} beoordeelde trades`)
      : (state.language === 'en' ? 'No assessed trades yet' : 'Nog geen beoordeelde trades');

    const grades = discipline.grades || {};
    const trendLabels = state.language === 'en'
      ? {improving:'Improving',stable:'Stable',declining:'Earn-back focus',insufficient:'Not enough grades'}
      : {improving:'Verbeterend',stable:'Stabiel',declining:'Earn-back-focus',insufficient:'Nog te weinig grades'};
    $('disciplineTrend').textContent = trendLabels[grades.trend] || trendLabels.insufficient;
    $('disciplineTrendMeta').textContent = grades.recent_score == null
      ? (state.language === 'en' ? 'A, B and C without P&L' : 'A, B en C zonder P&L')
      : (state.language === 'en' ? `Recent process score ${format(grades.recent_score, 0)}/100` : `Recente processcore ${format(grades.recent_score, 0)}/100`);

    const routine = discipline.routine || {};
    $('disciplineBreakdownRules').textContent = rules.pct == null ? '—' : `${format(rules.pct, 0)}% · ${rules.count}`;
    $('disciplineBreakdownGrades').textContent = grades.score == null ? '—' : `${format(grades.score, 0)}/100 · ${grades.count}`;
    $('disciplineBreakdownRoutine').textContent = routine.pct == null ? '—' : `${format(routine.pct, 0)}% · ${routine.completed_days}/${routine.observed_days}`;

    const today = discipline.today || {};
    const button = $('noTradeDayButton');
    let title = state.language === 'en' ? 'Earn your day' : 'Verdien je dag';
    let text = state.language === 'en' ? 'Complete your day start or consciously record a watching day.' : 'Doe je dagstart of leg bewust een kijkdag vast.';
    if (streak.today_complete) {
      title = state.language === 'en' ? 'Today is earned' : 'Vandaag is verdiend';
      if (streak.earned_by_day_start && streak.earned_by_no_trade) text = state.language === 'en' ? 'Your day start and conscious no-trade choice both count.' : 'Je dagstart en bewuste no-trade-keuze tellen allebei mee.';
      else if (streak.earned_by_day_start) text = state.language === 'en' ? 'Your completed day start keeps the streak alive.' : 'Je afgeronde dagstart houdt de streak actief.';
      else text = state.language === 'en' ? 'Your conscious no-trade day is process profit.' : 'Je bewuste no-trade-dag is proceswinst.';
    } else if (today.open_position) {
      text = state.language === 'en' ? 'A position is open. Manage the trade; a no-trade day cannot be recorded.' : 'Er staat een positie open. Beheer de trade; een no-trade-dag kan nu niet worden vastgelegd.';
    } else if (today.trade_activity_present) {
      text = state.language === 'en' ? 'Trading activity is already in today’s journal. Earn the day through your day start.' : 'Er staat al handelsactiviteit in het dagboek. Verdien de dag via je dagstart.';
    }
    $('disciplineTodayTitle').textContent = title;
    $('disciplineTodayText').textContent = text;
    button.classList.toggle('hidden', Boolean(streak.today_complete));
    button.disabled = !today.no_trade_allowed;
    button.textContent = today.no_trade_declared
      ? (state.language === 'en' ? 'Conscious no-trade recorded' : 'Bewuste no-trade vastgelegd')
      : (state.language === 'en' ? 'I consciously did not trade today' : 'Ik heb vandaag bewust niet gehandeld');
  }

  async function markNoTradeDay() {
    const button = $('noTradeDayButton');
    if (!button || button.disabled) return;
    button.disabled = true;
    const original = button.textContent;
    button.textContent = state.language === 'en' ? 'Recording…' : 'Vastleggen…';
    try {
      const response = await api('/api/v1/discipline/no-trade', { method:'POST', body:{}, timeout:30000 });
      if (response.discipline) state.overview.discipline = response.discipline;
      renderDiscipline();
      applyLanguage();
    } catch (error) {
      $('disciplineTodayText').textContent = error.message;
      button.textContent = original;
      button.disabled = false;
    }
  }

  function renderAccountGuard() {
    const guard = state.overview?.account_guard || {};
    const card = $('accountGuardSection')?.querySelector('.account-guard-card');
    if (!card) return;
    const owner = String(state.overview?.principal?.role || '').toLowerCase() === 'owner';
    $('accountGuardSection').hidden = !owner;
    if (!owner) return;
    const active = Boolean(guard.active);
    const blocked = Boolean(guard.ticket_blocked);
    $('accountGuardNotice').className = 'notice info account-guard-notice';
    const remaining = finite(guard.buffer_remaining_usdt);
    const ratio = finite(guard.buffer_remaining_pct);
    $('accountGuardBadge').textContent = active
      ? (blocked ? (state.language === 'en' ? 'LOCKED' : 'GEBLOKKEERD') : (state.language === 'en' ? 'ACTIVE' : 'ACTIEF'))
      : (state.language === 'en' ? 'OFF' : 'UIT');
    $('accountGuardBadge').className = `badge ${blocked ? 'bad' : active ? 'good' : 'neutral'}`;
    card.classList.toggle('locked', active); card.classList.toggle('blocked', blocked);
    $('accountGuardBuffer').textContent = remaining == null ? '—' : money(remaining);
    $('accountGuardBufferMeta').textContent = active
      ? (state.language === 'en'
          ? `${format(guard.daily_loss_limit_pct,2)}% is locked for today. Wins cannot restore buffer already consumed.`
          : `${format(guard.daily_loss_limit_pct,2)}% staat voor vandaag vast. Winst geeft eerder verbruikte buffer niet terug.`)
      : (state.language === 'en'
          ? `Preview based on a maximum ${format(guard.daily_loss_limit_pct,2)}% day buffer. Activate to lock it.`
          : `Voorbeeld op basis van maximaal ${format(guard.daily_loss_limit_pct,2)}% dagbuffer. Activeer om te vergrendelen.`);
    const fill = $('accountGuardBufferFill');
    fill.style.width = `${Math.max(0, Math.min(100, ratio == null ? 0 : ratio))}%`;
    $('accountGuardBufferTrack').className = `buffer-track ${guard.buffer_state || 'unknown'}`;
    $('accountGuardPosition').textContent = `${guard.positions_open || 0} / ${guard.max_positions || 1}`;
    $('accountGuardPositionMeta').textContent = active
      ? (guard.position_block ? (state.language === 'en' ? 'Second position blocked' : 'Tweede positie geblokkeerd') : (state.language === 'en' ? 'Maximum one position' : 'Maximaal één positie'))
      : (state.language === 'en' ? 'Not locked' : 'Niet vergrendeld');
    const cooldown = Number(guard.cooldown_seconds_remaining || 0);
    $('accountGuardCooldown').textContent = cooldown > 0 ? `${Math.ceil(cooldown / 60)} min` : (state.language === 'en' ? 'None' : 'Geen');
    $('accountGuardCooldownMeta').textContent = cooldown > 0
      ? (active ? (state.language === 'en' ? 'Ticket locked until timer ends' : 'Ticket dicht tot de timer afloopt') : (state.language === 'en' ? 'Advisory; activate Commitment Mode for a hard gate' : 'Advies; activeer Commitment Mode voor een hard hek'))
      : (state.language === 'en' ? 'Starts after a stop-out' : 'Start na een stop-out');
    $('accountGuardReset').textContent = guard.next_reset_at ? dateText(guard.next_reset_at) : (state.language === 'en' ? 'Tomorrow' : 'Morgen');
    const form = $('commitmentForm'); const select = $('commitmentLossLimit'); const button = $('commitmentActivateButton');
    form.hidden = false;
    const serverMax = Number(guard.daily_loss_limit_pct || 2);
    if (active) {
      select.value = String(serverMax); select.disabled = true; button.disabled = true;
      button.textContent = state.language === 'en' ? 'Locked until tomorrow' : 'Vergrendeld tot morgen';
      $('accountGuardNotice').textContent = state.language === 'en'
        ? 'One-way today: no off switch, no wider loss limit and no override. Tomorrow you choose again.'
        : 'Vandaag één richting: geen uitknop, geen ruimere verlieslimiet en geen override. Morgen kies je opnieuw.';
    } else {
      select.disabled = false; button.disabled = false;
      const options = [...select.options].map((option) => Number(option.value));
      select.value = String(options.filter((value) => value <= serverMax + 1e-9).pop() || Math.min(...options));
      button.textContent = state.language === 'en' ? 'Activate Commitment Mode' : 'Commitment Mode activeren';
      $('accountGuardNotice').textContent = state.language === 'en'
        ? 'Once active, this gate cannot be turned off or widened today. You choose again tomorrow.'
        : 'Eenmaal actief kan dit hek vandaag niet uit of ruimer. Morgen kies je opnieuw.';
    }
  }

  async function activateCommitmentMode(event) {
    event?.preventDefault?.();
    const button = $('commitmentActivateButton'); const select = $('commitmentLossLimit');
    if (!button || button.disabled) return;
    button.disabled = true; const original = button.textContent;
    button.textContent = state.language === 'en' ? 'Locking…' : 'Vergrendelen…';
    try {
      const response = await api('/api/v1/commitment/activate', { method:'POST', body:{ daily_loss_limit_pct:Number(select.value) }, timeout:30000 });
      if (response.account_guard) state.overview.account_guard = response.account_guard;
      await loadOverview({ silent:true });
    } catch (error) {
      $('accountGuardNotice').textContent = error.message; $('accountGuardNotice').className = 'notice danger account-guard-notice';
      button.textContent = original; button.disabled = false;
    }
  }

  function renderDecisionFlow() {
    const latest = state.overview?.latest || {};
    const health = state.overview?.stack_health || {};
    const price = latest.price_status || {};
    const steps = [
      ['1', 'Waarneming', `${health.synced_count || 0}/4 grafieken gelezen`, (health.synced_count || 0) === 4],
      ['2', 'Gerichte controle', `${asArray(latest.blocking_review_timeframes).length} actie(s) nodig`, asArray(latest.blocking_review_timeframes).length === 0],
      ['3', 'Veiligheidsregels', gateLabel(latest.execution_gate?.status), Boolean(latest.execution_gate?.orderable)],
      ['4', 'Prijs en ticket', price.ok && !price.stale ? 'Verse prijs beschikbaar' : 'Ticket hard geblokkeerd', Boolean(price.ok && !price.stale)]
    ];
    const root = clear($('decisionFlow'));
    steps.forEach(([n,title,text,ok]) => { const item=create('article',`flow-step ${ok?'done':'pending'}`); item.append(create('span','flow-number',n),create('div','',title),create('small','',text)); root.append(item); });
  }

  function overlappingZonePairs(timeframe = '4H') {
    const zones = asArray(layerBundle(timeframe).source?.zones)
      .map((zone) => ({ bottom:finite(zone.bottom), top:finite(zone.top) }))
      .filter((zone) => zone.bottom !== null && zone.top !== null)
      .map((zone) => ({ bottom:Math.min(zone.bottom, zone.top), top:Math.max(zone.bottom, zone.top) }));
    let count = 0;
    for (let i = 0; i < zones.length; i += 1) for (let j = i + 1; j < zones.length; j += 1) {
      if (Math.max(zones[i].bottom, zones[j].bottom) <= Math.min(zones[i].top, zones[j].top)) count += 1;
    }
    return count;
  }

  function zoneLinkageDetail(setup = {}) {
    if (setup.parent_zone && setup.setup_zone_15m && setup.execution_zone) return state.language === 'en' ? '4H, 15M and 3M areas are linked' : '4H-, 15M- en 3M-zones zijn gekoppeld';
    const missing = [];
    if (!setup.parent_zone) missing.push(state.language === 'en' ? '4H parent area' : '4H-ouderzone');
    if (!setup.setup_zone_15m) missing.push(state.language === 'en' ? '15M setup area' : '15M-opbouwzone');
    if (!setup.execution_zone) missing.push(state.language === 'en' ? '3M execution area' : '3M-uitvoeringszone');
    const overlaps = overlappingZonePairs('4H');
    if (overlaps > 0) return state.language === 'en'
      ? `${overlaps} overlapping 4H area${overlaps === 1 ? '' : 's'} — review that layer`
      : `${overlaps} overlappende 4H-zone${overlaps === 1 ? '' : 's'} — controleer die laag`;
    return state.language === 'en' ? `Missing: ${missing.join(', ')}` : `Ontbreekt: ${missing.join(', ')}`;
  }

  function renderTicketReadiness() {
    const latest = state.overview?.latest || {};
    const health = state.overview?.stack_health || {};
    const gate = latest.execution_gate || {};
    const price = latest.price_status || {};
    const account = state.overview?.account || {};
    const setup = latest.setup || {};
    const matchedJournalRules = asArray(latest.journal_pattern_gate?.matched_rules);
    const checks = [
      { label: '4 charts gelezen', ok: Number(health.synced_count || 0) === 4, detail: `${health.synced_count || 0}/4` },
      { label: 'Geen inhoudelijke hercontrole nodig', ok: asArray(latest.blocking_review_timeframes).length === 0, detail: asArray(latest.blocking_review_timeframes).length ? asArray(latest.blocking_review_timeframes).join(', ') : 'ongewijzigde controles blijven geldig' },
      { label: state.language === 'en' ? 'Zone chain 4H → 15M → 3M' : 'Zoneketen 4H → 15M → 3M', ok: Boolean(setup.parent_zone && setup.setup_zone_15m && setup.execution_zone), detail: zoneLinkageDetail(setup) },
      { label: 'Huidige prijs is beschikbaar', ok: Boolean(price.ok && !price.stale && Number(price.price) > 0), detail: price.ok ? `${price.source || 'bron'} · ${format(price.price, 2)}` : (price.reason || 'ontbreekt') },
      { label: 'Rekeningwaarde is bijgewerkt', ok: Boolean(account.equity_fresh && Number(account.equity) > 0), detail: account.equity_fresh ? money(account.equity) : 'controle nodig' },
      { label: 'Juiste werkruimte actief', ok: state.overview?.principal?.role === 'owner', detail: state.overview?.principal?.role === 'owner' ? 'live ticketcontrole toegestaan' : 'paper test · geen echt ticket' },
      { label: 'Alle veiligheidsregels zijn groen', ok: Boolean(gate.orderable && gate.status === 'ENTRY_READY'), detail: gateLabel(gate.status) },
      ...matchedJournalRules.map((rule) => ({
        label: state.language === 'en' ? 'Owner-confirmed journal rule' : 'Door eigenaar bevestigde dagboekregel',
        ok: false,
        detail: rule.reason || (state.language === 'en' ? 'This ticket pattern is blocked.' : 'Dit ticketpatroon is geblokkeerd.'),
      })),
      { label: 'Jij houdt de eindklik', ok: true, detail: 'de cockpit klikt nooit definitief' },
    ];
    const root = clear($('ticketReadiness'));
    checks.forEach((row) => {
      const item = create('div', `readiness-item ${row.ok ? 'done' : 'blocked'}`);
      item.append(create('span', 'readiness-icon', row.ok ? '✓' : '!'), create('div', '', row.label), create('small', '', row.detail));
      root.append(item);
    });
    const ready = checks.every((row) => row.ok);
    const blockerCount = checks.filter((row) => !row.ok).length;
    $('ticketReadinessBadge').textContent = ready ? ui('ticket.safe_badge') : ui('ticket.blocked_badge', { count:blockerCount, plural:blockerCount === 1 ? '' : (state.language === 'en' ? 'S' : 'S') });
    $('ticketReadinessBadge').className = `badge ${ready ? 'good' : 'wait'}`;
    $('ticketReadinessCard').classList.toggle('ready', ready);
    $('ticketReadinessReason').textContent = ready
      ? ui('ticket.safe_reason')
      : executionReason(latest);
    const reviewLeft = asArray(latest.blocking_review_timeframes).filter((tf) => TF_ORDER.includes(tf) && layerBundle(tf).source);
    $('startReviewButton').textContent = reviewLeft.length ? `Controleer alleen ${reviewLeft[0]}${reviewLeft.length > 1 ? ` (${reviewLeft.length} nodig)` : ''}` : 'Bekijk gecontroleerde kaart';
    $('startReviewButton').disabled = Number(health.synced_count || 0) === 0;
  }


  function renderParentChain() {
    const root = clear($('parentChain'));
    if (!root) return;
    const links = state.overview?.composite_map?.parent_links || {};
    TF_ORDER.forEach((tf, index) => {
      const { source, health } = layerBundle(tf);
      const zones = asArray(source?.zones);
      const node = create('article', `parent-node ${health?.confirmed ? 'verified' : health?.synced ? 'synced' : 'missing'}`);
      const title = create('div', 'parent-node-title');
      title.append(create('strong', '', tf), create('span', '', TF_LABELS[tf][0]));
      const relationRows = asArray(links[tf]);
      const relation = relationRows.length
        ? `${relationRows.length} gekoppelde ${relationRows.length === 1 ? 'zone' : 'zones'} aan ${[...new Set(relationRows.map((row) => row.parent_timeframe))].join('/')}`
        : tf === '1D' ? 'Hoofdcontext' : tf === '4H' ? 'HTF-locatie' : 'Nog geen ouderzone gekoppeld';
      node.append(title, create('p', '', source ? `${zones.length} zones · ${translateTrend(source.trend)}` : 'Laag ontbreekt'), create('small', '', relation));
      root.append(node);
      if (index < TF_ORDER.length - 1) root.append(create('span', 'chain-arrow', '→'));
    });
  }

  function renderLayers() {
    const root = clear($('layerRail'));
    TF_ORDER.forEach((tf, index) => {
      const { source, health } = layerBundle(tf);
      const stateName = health?.confirmed ? 'verified' : health?.synced ? 'synced' : 'missing';
      const card = create('button', `layer-card ${stateName}${state.timeframe === tf ? ' active' : ''}`);
      card.type = 'button'; card.dataset.timeframe = tf; card.setAttribute('role', 'listitem');
      const top = create('div', 'layer-top');
      top.append(create('b', '', tf), create('span', `badge ${health?.confirmed ? 'good' : health?.synced ? 'wait' : 'neutral'}`, health?.confirmed ? 'GECONTROLEERD' : health?.synced ? 'GELEZEN' : 'ONTBREEKT'));
      card.append(top, create('h3', '', TF_LABELS[tf][0]), create('p', '', TF_LABELS[tf][1]));
      const foot = create('div', 'layer-foot');
      foot.append(create('span', '', `${health?.zones || 0} zones`), create('span', '', source?.overall_confidence ? `${Math.round(source.overall_confidence)}%` : '—'));
      card.append(foot);
      card.addEventListener('click', () => { state.timeframe = tf; renderLayers(); renderMap(); });
      root.append(card);

      const step = $('workflowSteps').children[index];
      step.classList.remove('done', 'current');
      if (health?.synced) step.classList.add('done');
      else if (!asArray(state.overview?.stack_health?.layers).slice(0, index).some((row) => !row.synced)) step.classList.add('current');
    });
    const health = state.overview?.stack_health || {};
    const latest = state.overview?.latest || {};
    const blocked = asArray(latest.blocking_review_timeframes).length;
    const summary = `${health.synced_count || 0}/4 gelezen · ${blocked ? `${blocked} gerichte controle${blocked===1?'':'s'}` : 'geen hercontrole nodig'}`;
    if ($('chartWorkflowSummary')) {
      $('chartWorkflowSummary').textContent = summary;
      $('chartWorkflowSummary').className = `badge ${blocked === 0 && Number(health.synced_count || 0) === 4 ? 'good' : Number(health.synced_count || 0) === 4 ? 'wait' : 'neutral'}`;
    }
    if ($('marketMapSummaryBadge')) $('marketMapSummaryBadge').textContent = summary;
  }

  function renderFacts(source, health) {
    const root = clear($('layerFacts'));
    const facts = [
      ['Status', health?.confirmed ? 'Gecontroleerd' : health?.synced ? 'Gesynchroniseerd' : 'Ontbreekt'],
      ['Trend', translateTrend(source?.trend)],
      ['Zones', String(asArray(source?.zones).length)],
      ['Nauwkeurigheid', source?.overall_confidence == null ? '—' : `${Math.round(source.overall_confidence)}%`],
      ['Bereik laag', format(source?.range_low, 8)],
      ['Bereik hoog', format(source?.range_high, 8)]
    ];
    facts.forEach(([label, value]) => {
      const box = create('div'); box.append(create('span', '', label), create('strong', '', value)); root.append(box);
    });
  }

  function translateTrend(value) {
    const labels = state.language === 'en'
      ? { up: 'Rising', down: 'Falling', range: 'Sideways', unknown: 'Unknown' }
      : { up: 'Stijgend', down: 'Dalend', range: 'Zijwaarts', unknown: 'Onbekend' };
    return labels[value] || labels.unknown;
  }

  function visionRole(zone = {}, source = {}) {
    const explicit = String(zone.role || zone.rol || '').toLowerCase();
    if (explicit === 'support' || explicit === 'resistance') return explicit;
    const color = String(zone.color || '').toLowerCase();
    if (/green|groen|teal|lime/.test(color)) return 'support';
    if (/red|rood|orange|oranje/.test(color)) return 'resistance';
    const price = finite(state.overview?.latest?.price_status?.price ?? state.overview?.latest?.price);
    const top = finite(zone.top); const bottom = finite(zone.bottom);
    if (price !== null && top !== null && top < price) return 'support';
    if (price !== null && bottom !== null && bottom > price) return 'resistance';
    return 'unknown';
  }

  function visionRoleLabel(role) {
    const labels = state.language === 'en'
      ? { support:'Support', resistance:'Resistance', unknown:'Check role' }
      : { support:'Steun', resistance:'Weerstand', unknown:'Rol controleren' };
    return labels[role] || labels.unknown;
  }

  function visionIntentLabel(intent) {
    const labels = state.language === 'en'
      ? { structure:'Structure', entry:'Local reaction area', target:'Opposing area', range_boundary:'Range boundary' }
      : { structure:'Structuur', entry:'Lokale reactiezone', target:'Tegengestelde zone', range_boundary:'Rangegrens' };
    return labels[String(intent || 'structure')] || labels.structure;
  }

  function visionReasonSummary(zone = {}, source = {}) {
    const raw = String(zone.reason || zone.label || '').trim();
    const low = raw.toLowerCase();
    const role = visionRole(zone, source);
    const tf = String(zone.source_timeframe || zone.timeframe || source.source_timeframe || state.timeframe || '').toUpperCase();
    const roleText = visionRoleLabel(role).toLowerCase();
    if (/sweep/.test(low) && /reclaim|herover/.test(low)) {
      return state.language === 'en'
        ? `Price swept this ${roleText} area and reclaimed it; verify the exact boundaries.`
        : `Prijs maakte een sweep door deze ${roleText}zone en heroverde haar; controleer de exacte grenzen.`;
    }
    if (/local[_ -]?reversal|lokale kanteling|reversal/.test(low)) {
      return state.language === 'en'
        ? `A local reversal was detected around this ${roleText} area; this is an observation, not an entry signal.`
        : `Rond deze ${roleText}zone is een lokale kanteling gezien; dit is een waarneming, geen instapsignaal.`;
    }
    if (/breakout|uitbraak/.test(low) && /retest|hertest/.test(low)) {
      return state.language === 'en'
        ? `Price broke this area and retested it; verify that the close and retest are visible.`
        : `Prijs brak door deze zone en testte haar opnieuw; controleer of close en hertest echt zichtbaar zijn.`;
    }
    if (/handmatig getekend|manually drawn|getekende zone|tradingview/.test(low)) {
      return state.language === 'en'
        ? `This is a drawn ${roleText} area on ${tf || 'the chart'}; verify its role and boundaries.`
        : `Dit is een getekende ${roleText}zone op ${tf || 'de chart'}; controleer rol en grenzen.`;
    }
    if (String(zone.intent || '') === 'target') {
      return state.language === 'en'
        ? 'This opposing area is only relevant as a potential objective after a valid setup passes every gate.'
        : 'Deze tegengestelde zone is pas relevant als mogelijk doel nadat een geldige setup alle poorten doorstaat.';
    }
    if (String(zone.intent || '') === 'range_boundary') {
      return state.language === 'en'
        ? `This area marks a visible boundary of the ${tf || 'current'} range.`
        : `Deze zone markeert een zichtbare grens van de ${tf || 'huidige'}-range.`;
    }
    if (role === 'support') {
      return state.language === 'en'
        ? `This drawn area sits below or around price and may act as support; verify the exact boundaries.`
        : 'Deze getekende zone ligt onder of rond de prijs en kan als steun werken; controleer de exacte grenzen.';
    }
    if (role === 'resistance') {
      return state.language === 'en'
        ? `This drawn area sits above or around price and may act as resistance; verify the exact boundaries.`
        : 'Deze getekende zone ligt boven of rond de prijs en kan als weerstand werken; controleer de exacte grenzen.';
    }
    return state.language === 'en'
      ? 'The model found a coloured area, but its role is not reliable yet. Check it manually.'
      : 'Het model vond een gekleurde zone, maar de rol is nog niet betrouwbaar. Controleer haar handmatig.';
  }

  function technicalDetails(raw, label) {
    const text = String(raw || '').trim();
    if (!text) return null;
    const details = create('details', 'vision-technical-details');
    details.append(create('summary', '', label), create('p', '', text.replace(/\s+/g, ' ').slice(0, 500)));
    return details;
  }

  function normaliseVisionWarning(value) {
    const text = String(value || '').trim();
    const rules = state.language === 'en' ? [
      [/chart is 1d timeframe; setup and trigger detection disabled|dit is de 1d-laag/i, 'This is the 1D context layer. Setup and trigger detection are intentionally disabled.'],
      [/chart is 4h timeframe; setup and trigger detection disabled|dit is de 4h-laag/i, 'This is the 4H context layer. Setup and trigger detection are intentionally disabled.'],
      [/purple.*ambiguous|paarse zone/i, 'A purple area has no reliable role yet. Check support or resistance manually.'],
      [/price axis|right axis|prijsas/i, 'One or more prices were read from the price axis. Verify the exact boundaries.'],
      [/current price|actuele-prijslijn/i, 'The current-price line was ignored and does not count as a user-drawn area.'],
      [/multiple resistance|weerstandsgebieden boven/i, 'Several resistance areas are visible above the current price.'],
      [/multiple support|steungebieden onder/i, 'Several support areas are visible below the current price.'],
      [/invalidation.*missing|level-2.*ontbreekt/i, 'The Level-2 invalidation is missing and must be entered and checked manually.'],
      [/range.*niet expliciet|range was not explicitly/i, 'The range was not clearly readable. Check the 4H range boundaries manually.'],
      [/possible 15m setup|mogelijke 15m-setup/i, 'A possible 15M setup was detected. Check direction, type and evidence manually.'],
      [/possible 3m trigger|mogelijke 3m-trigger/i, 'A possible 3M trigger was detected. It never becomes orderable without your review.']
    ] : [
      [/chart is 1d timeframe; setup and trigger detection disabled|dit is de 1d-laag/i, 'Dit is de 1D-contextlaag. Setup- en instapdetectie zijn hier bewust uitgeschakeld.'],
      [/chart is 4h timeframe; setup and trigger detection disabled|dit is de 4h-laag/i, 'Dit is de 4H-contextlaag. Setup- en instapdetectie zijn hier bewust uitgeschakeld.'],
      [/purple.*ambiguous|paarse zone/i, 'Een paarse zone heeft nog geen betrouwbare rol. Controleer steun of weerstand handmatig.'],
      [/price axis|right axis|prijsas/i, 'Eén of meer prijzen zijn vanaf de prijsas gelezen. Controleer de exacte grenzen.'],
      [/current price|actuele-prijslijn/i, 'De actuele-prijslijn is genegeerd en telt niet als getekende zone.'],
      [/multiple resistance|weerstandsgebieden boven/i, 'Er liggen meerdere weerstandsgebieden boven de actuele prijs.'],
      [/multiple support|steungebieden onder/i, 'Er liggen meerdere steungebieden onder de actuele prijs.'],
      [/invalidation.*missing|level-2.*ontbreekt/i, 'De Level-2-invalidatie ontbreekt en moet handmatig worden ingevuld en gecontroleerd.'],
      [/range.*niet expliciet|range was not explicitly/i, 'De range was niet duidelijk leesbaar. Controleer de 4H-rangegrenzen handmatig.'],
      [/possible 15m setup|mogelijke 15m-setup/i, 'Er is een mogelijke 15M-opbouw gezien. Controleer richting, type en bewijs handmatig.'],
      [/possible 3m trigger|mogelijke 3m-trigger/i, 'Er is een mogelijke 3M-trigger gezien. Zonder jouw controle wordt die nooit orderbaar.']
    ];
    for (const [pattern, summary] of rules) if (pattern.test(text)) return { summary, raw:text };
    return { summary: state.language === 'en' ? 'The model reported an observation that still needs your review.' : 'Het model meldde een waarneming die jij nog moet controleren.', raw:text };
  }

  function translateWarning(value) { return normaliseVisionWarning(value).summary; }

  function appendVisionWarning(root, warning) {
    const item = normaliseVisionWarning(warning);
    const card = create('div', 'warning-item vision-warning');
    card.append(create('span', '', item.summary));
    const details = technicalDetails(item.raw, state.language === 'en' ? 'Show technical model text' : 'Toon technische modeltekst');
    if (details) card.append(details);
    root.append(card);
  }

  function renderZones(source) {
    const root = clear($('layerZones'));
    const zones = asArray(source?.zones);
    $('zoneCount').textContent = String(zones.length);
    if (!zones.length) { root.append(create('div', 'empty-state', 'Nog geen betrouwbare zones gevonden.')); return; }
    zones.forEach((zone) => {
      const role = visionRole(zone, source);
      const card = create('article', `zone-card ${role}`);
      const grid = create('dl', 'vision-zone-grid');
      const add = (label, value, className = '') => {
        grid.append(create('dt', '', label), create('dd', className, value));
      };
      add(state.language === 'en' ? 'Role' : 'Rol', visionRoleLabel(role));
      add(state.language === 'en' ? 'Price level / area' : 'Prijsniveau / zone', `${format(zone.bottom, 8)} – ${format(zone.top, 8)}`, 'mono vision-price');
      add(state.language === 'en' ? 'Reason' : 'Reden', visionReasonSummary(zone, source), 'vision-reason');
      add(state.language === 'en' ? 'Confidence' : 'Zekerheid', `${Math.round(finite(zone.confidence) || 0)}%`);
      card.append(grid);
      const tags = create('div', 'vision-zone-tags');
      tags.append(create('span', `badge ${role === 'support' ? 'good' : role === 'resistance' ? 'bad' : 'neutral'}`, visionRoleLabel(role)), create('span', 'badge neutral', visionIntentLabel(zone.intent)));
      if (zone.invalidation) tags.append(create('span', 'badge neutral', `Level-2 ${format(zone.invalidation, 8)}`));
      card.append(tags);
      const details = technicalDetails(zone.reason || zone.label, state.language === 'en' ? 'Show technical model text' : 'Toon technische modeltekst');
      if (details) card.append(details);
      root.append(card);
    });
  }

  async function renderPreview(tf, source) {
    const image = $('chartPreview'); const empty = $('previewEmpty');
    if (state.previewUrl) { URL.revokeObjectURL(state.previewUrl); state.previewUrl = null; }
    if (!source) { image.hidden = true; empty.hidden = false; return; }
    if (DEMO) { image.src = demoChartData(tf); image.hidden = false; empty.hidden = true; return; }
    try {
      const blob = await api(`/api/v1/chart/preview/${encodeURIComponent(state.asset)}/${encodeURIComponent(tf)}`, { blob: true, timeout: 20000 });
      state.previewUrl = URL.createObjectURL(blob); image.src = state.previewUrl; image.hidden = false; empty.hidden = true;
    } catch { image.hidden = true; empty.hidden = false; }
  }

  function renderMap() {
    const tf = state.timeframe;
    const { source, draft, confirmed, health } = layerBundle(tf);
    $$('#timeframeTabs button').forEach((button) => {
      const active = button.dataset.timeframe === tf;
      button.classList.toggle('active', active); button.setAttribute('aria-selected', String(active));
    });
    $('layerTitle').textContent = `${tf} · ${TF_LABELS[tf][0]}`;
    $('layerStatus').textContent = health?.confirmed ? 'GECONTROLEERD' : health?.synced ? 'GELEZEN' : 'ONTBREEKT';
    $('layerStatus').className = `badge ${health?.confirmed ? 'good' : health?.synced ? 'wait' : 'neutral'}`;
    $('previewTitle').textContent = source ? `${state.asset}USDT · ${tf} · ${dateText(source.at)}` : 'Geen grafiek';
    $('previewConfidence').textContent = source?.overall_confidence == null ? '—' : `${Math.round(source.overall_confidence)}%`;
    $('previewConfidence').className = `badge ${source?.overall_confidence >= 80 ? 'good' : source ? 'wait' : 'neutral'}`;
    $('reviewDraftButton').disabled = !draft;
    $('editLayerButton').disabled = !confirmed;
    renderFacts(source, health);
    renderZones(source);
    clear($('draftWarnings'));
    asArray(source?.warnings).forEach((warning) => appendVisionWarning($('draftWarnings'), warning));
    renderPreview(tf, source);

    const healthAll = state.overview?.stack_health || {};
    const latest = state.overview?.latest || {};
    const blocking = asArray(latest.blocking_review_timeframes).length;
    $('mapSummary').textContent = `${healthAll.synced_count || 0}/4 gelezen · ${blocking ? `${blocking} gerichte controle${blocking===1?'':'s'}` : 'ongewijzigde controles geldig'}`;
    $('guideNote').textContent = healthAll.capture_complete
      ? 'Alle vier charts staan in de cockpit. Alleen inhoudelijke wijzigingen of een concreet setup/signaal vragen opnieuw jouw controle.'
      : 'De automatische extensiestand reageert alleen op een bewuste tijdframe- of symboolwissel. Voor wijzigingen binnen dezelfde grafiek gebruik je “Lees deze grafiek”.';
  }

  function renderPositions() {
    const positions = openPositions();
    document.body.classList.toggle('has-open-position', positions.length > 0);
    if (positions.length && !state.positionModeInitialized) {
      ['chartWorkflowPanel','marketMapPanel','chartTechPanel'].forEach((id) => { const panel = $(id); if (panel) { panel.open = false; updateCollapseText(panel); } });
      state.positionModeInitialized = true;
    }
    if (!positions.length) state.positionModeInitialized = false;
    const root = clear($('positionsArea'));
    const pnlTotal = totalOpenPnl();
    $('positionMeta').textContent = positions.length ? `${positions.length} open · ${money(pnlTotal)}` : ui('position.none.meta');
    if (!positions.length) {
      const empty = create('article', 'panel empty-panel calm-empty');
      empty.append(create('strong','',ui('position.none.title')), document.createTextNode(' '), create('span','',ui('position.none.body')));
      root.append(empty);
      return;
    }
    positions.forEach((position) => {
      const pnl = positionPnl(position);
      const side = friendlySide(position.side);
      const card = create('article', `panel position-hero ${pnl >= 0 ? 'positive' : 'negative'}`);
      const head = create('div', 'position-hero-head');
      const title = create('div');
      title.append(create('span', `position-side ${side === 'LONG' ? 'long' : 'short'}`, side), create('h2', '', position.symbol || 'Open positie'), create('p', 'muted', 'Live, alleen-lezen via Bybit'));
      const result = create('div', 'position-result');
      result.append(create('span', '', 'Open resultaat'), create('strong', pnl >= 0 ? 'good' : 'bad', money(pnl)));
      head.append(title, result);
      const metrics = create('div', 'position-metrics');
      const rows = [
        ['Instap', format(positionEntry(position), 8)],
        ['Huidige prijs', format(positionMark(position), 8)],
        ['Stop', format(positionStop(position), 8)],
        ['Doel', format(positionTarget(position), 8)],
        ['Grootte', format(position.size, 8)],
        ['Leverage', position.leverage ? `${format(position.leverage, 2)}x` : '—'],
        ['Liquidatie', format(position.liq || position.liqPrice, 8)]
      ];
      rows.forEach(([label,value]) => { const box=create('div'); box.append(create('span','',label),create('strong','mono',value)); metrics.append(box); });
      const guidance = create('div', 'position-guidance');
      guidance.append(create('span','guidance-icon','✓'), create('div','', 'Volg je vooraf ingestelde plan'), create('p','', 'Stop na TP1 laten staan. Pas na TP2 én alleen wanneer de resterende positie in winst staat mag de stop naar break-even.'));
      card.append(head, metrics, guidance);
      root.append(card);
    });
  }

  function tradeDirection(trade) {
    const explicit = String(trade?.direction || '').toLowerCase();
    if (explicit === 'long' || explicit === 'short') return explicit;
    const closeSide = String(trade?.close_side || trade?.side || '').toLowerCase();
    return closeSide === 'sell' ? 'long' : closeSide === 'buy' ? 'short' : 'unknown';
  }

  function tradeResult(trade) {
    const explicit = String(trade?.result || '').toLowerCase();
    if (['win', 'loss', 'breakeven'].includes(explicit)) return explicit;
    const pnl = finite(trade?.pnl) || 0;
    return pnl > 0 ? 'win' : pnl < 0 ? 'loss' : 'breakeven';
  }

  function statValue(stats, key, fallback = null) {
    const value = stats?.[key];
    return value === undefined || value === null || value === '' ? fallback : value;
  }

  function createPerformanceKpi(label, value, note, tone = 'neutral') {
    const card = create('article', `performance-kpi ${tone}`);
    const valueNode = create('strong', 'full-value', value); valueNode.title = String(value ?? '');
    card.append(create('span', '', label), valueNode, create('small', '', note));
    return card;
  }

  function renderEquityCurve(trades, stats) {
    const svg = $('equityCurve');
    const empty = $('equityCurveEmpty');
    clear(svg);
    const rows = trades
      .filter((trade) => finite(trade.pnl) !== null)
      .slice()
      .sort((a, b) => new Date(a.closed_at || a.time || a.at || 0) - new Date(b.closed_at || b.time || b.at || 0));
    if (!rows.length) {
      svg.hidden = true; empty.hidden = false; $('equityCurveMeta').textContent = 'GEEN DATA'; $('equityStartEnd').textContent = '—';
      return;
    }
    svg.hidden = false; empty.hidden = true;
    const points = [{ value: 0, at: rows[0]?.closed_at || rows[0]?.time || rows[0]?.at }];
    let running = 0;
    rows.forEach((trade) => { running += finite(trade.pnl) || 0; points.push({ value: running, at: trade.closed_at || trade.time || trade.at }); });
    const width = 720, height = 240, padX = 44, padY = 28;
    let min = Math.min(0, ...points.map((point) => point.value));
    let max = Math.max(0, ...points.map((point) => point.value));
    if (Math.abs(max - min) < 1e-9) { max += 1; min -= 1; }
    const x = (index) => padX + (index / Math.max(1, points.length - 1)) * (width - padX * 2);
    const y = (value) => padY + ((max - value) / (max - min)) * (height - padY * 2);
    const ns = 'http://www.w3.org/2000/svg';
    const make = (tag, attrs = {}) => { const node = document.createElementNS(ns, tag); Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value)); return node; };
    [0, .25, .5, .75, 1].forEach((ratio) => {
      const lineY = padY + ratio * (height - padY * 2);
      svg.append(make('line', { x1: padX, y1: lineY, x2: width - padX, y2: lineY, class: 'equity-grid' }));
    });
    const zeroY = y(0);
    svg.append(make('line', { x1: padX, y1: zeroY, x2: width - padX, y2: zeroY, class: 'equity-zero' }));
    const linePath = points.map((point, index) => `${index ? 'L' : 'M'} ${x(index).toFixed(2)} ${y(point.value).toFixed(2)}`).join(' ');
    const areaPath = `${linePath} L ${x(points.length - 1).toFixed(2)} ${zeroY.toFixed(2)} L ${x(0).toFixed(2)} ${zeroY.toFixed(2)} Z`;
    svg.append(make('path', { d: areaPath, class: 'equity-area' }));
    svg.append(make('path', { d: linePath, class: `equity-line${running < 0 ? ' negative' : ''}` }));
    const last = points[points.length - 1];
    svg.append(make('circle', { cx: x(points.length - 1), cy: y(last.value), r: 5, class: 'equity-dot' }));
    const labels = [[max, padY + 5], [0, zeroY - 6], [min, height - padY + 3]];
    labels.forEach(([value, labelY]) => { const text = make('text', { x: 5, y: labelY, class: 'equity-label' }); text.textContent = money(value); svg.append(text); });
    $('equityCurveMeta').textContent = `${rows.length} TRADE${rows.length === 1 ? '' : 'S'}`;
    $('equityCurveMeta').className = `badge ${running > 0 ? 'good' : running < 0 ? 'bad' : 'neutral'}`;
    $('equityStartEnd').textContent = `${money(0)} → ${money(running)}`;
  }

  function aggregateTrades(trades, keyFn) {
    const out = {};
    trades.forEach((trade) => {
      const key = keyFn(trade) || 'Onbekend';
      out[key] = (out[key] || 0) + (finite(trade.pnl) || 0);
    });
    return out;
  }

  function renderBreakdown(root, values, labelFn = (value) => value) {
    clear(root);
    const entries = Object.entries(values || {}).filter(([, value]) => finite(value) !== null).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
    if (!entries.length) { root.append(create('div', 'empty-state', 'Nog geen uitsplitsing beschikbaar.')); return; }
    const maximum = Math.max(1, ...entries.map(([, value]) => Math.abs(Number(value) || 0)));
    entries.forEach(([key, value]) => {
      const row = create('div', 'breakdown-row');
      const track = create('div', 'breakdown-track');
      const fill = create('div', `breakdown-fill${Number(value) < 0 ? ' bad' : ''}`); fill.style.width = `${Math.max(3, Math.abs(Number(value) || 0) / maximum * 100)}%`; track.append(fill);
      row.append(create('span', '', labelFn(key)), track, create('strong', Number(value) >= 0 ? 'good' : 'bad', money(value))); root.append(row);
    });
  }

  function filteredJournalTrades() {
    const trades = asArray(state.overview?.journal?.trades);
    const direction = $('journalDirectionFilter')?.value || 'all';
    const symbol = $('journalSymbolFilter')?.value || 'all';
    const result = $('journalResultFilter')?.value || 'all';
    const source = $('journalSourceFilter')?.value || 'live';
    const sourceMatches = (trade) => {
      const value = String(trade.source_class || 'UNKNOWN').toUpperCase();
      if (source === 'all') return true;
      if (source === 'live') return !['PAPER','TESTDATA'].includes(value);
      if (source === 'verified') return value === 'BYBIT_VERIFIED';
      if (source === 'legacy') return value === 'LEGACY_IMPORT';
      if (source === 'unknown') return value === 'UNKNOWN';
      if (source === 'paper') return value === 'PAPER';
      if (source === 'test') return value === 'TESTDATA';
      return true;
    };
    return trades.filter((trade) =>
      (direction === 'all' || tradeDirection(trade) === direction) &&
      (symbol === 'all' || String(trade.symbol || trade.asset || '').toUpperCase() === symbol) &&
      (result === 'all' || tradeResult(trade) === result) &&
      sourceMatches(trade)
    ).slice().sort((a, b) => new Date(b.closed_at || b.time || b.at || 0) - new Date(a.closed_at || a.time || a.at || 0));
  }

  function updateJournalSymbolOptions(trades) {
    const select = $('journalSymbolFilter');
    if (!select) return;
    const active = select.value || 'all';
    const symbols = [...new Set(trades.map((trade) => String(trade.symbol || trade.asset || '').toUpperCase()).filter(Boolean))].sort();
    clear(select); const all = create('option', '', 'Alle markten'); all.value = 'all'; select.append(all);
    symbols.forEach((symbol) => { const option = create('option', '', symbol); option.value = symbol; select.append(option); });
    select.value = symbols.includes(active) ? active : 'all';
  }

  function renderJournalTable() {
    const allTrades = asArray(state.overview?.journal?.trades);
    const trades = filteredJournalTrades();
    const shown = trades.slice(0, state.journalLimit);
    const body = clear($('journalTableBody'));
    const table = document.querySelector('.journal-table');
    shown.forEach((trade) => {
      const direction = tradeDirection(trade); const result = tradeResult(trade); const grade = String(trade.process_grade || '').toUpperCase();
      const row = create('tr');
      if (trade.direction_consistency === 'mismatch') row.classList.add('direction-unverified');
      if (trade.r_breach_alarm) row.classList.add('r-breach-row');
      const addCell = (label, text, className = '') => { const cell = create('td', className, text); cell.dataset.label = label; cell.title = String(text ?? ''); row.append(cell); return cell; };
      addCell('Datum', dateText(trade.closed_at || trade.time || trade.at));
      const sourceCell = addCell('Bron', '', 'journal-source-cell');
      const sourceText = sourceLabel(trade);
      const sourceIcon = create('span', `journal-meta-icon source-icon source-${String(trade.source_class || 'unknown').toLowerCase().replace(/[^a-z0-9]+/g,'-')}`, '●');
      sourceIcon.title = sourceText; sourceIcon.setAttribute('aria-label', sourceText); sourceIcon.setAttribute('role','img');
      sourceCell.append(sourceIcon);
      addCell('Markt', trade.symbol || trade.asset || '—', 'mono');
      const directionCell = addCell('Richting', direction === 'long' ? 'LONG' : direction === 'short' ? 'SHORT' : 'ONBEKEND', `trade-direction ${direction}`);
      if (trade.direction_consistency === 'mismatch') {
        const warningText = `${consistencyLabel('mismatch')} — ${consistencyReason('mismatch')}`;
        const warningIcon = create('span','journal-meta-icon direction-warning','!');
        warningIcon.title = warningText; warningIcon.setAttribute('aria-label', warningText); warningIcon.setAttribute('role','img');
        directionCell.append(warningIcon);
      }
      addCell('Instap', format(trade.entry, 8), 'mono');
      addCell('Uitstap', format(trade.exit, 8), 'mono');
      const resultCell = addCell('Netto resultaat', money(trade.pnl), `result-value ${result === 'win' ? 'good' : result === 'loss' ? 'bad' : ''}`);
      if (trade.r_breach_alarm) resultCell.append(create('span','r-breach-badge', state.language === 'en' ? `R < -1 · CHECK STOP` : `R < -1 · STOP CONTROLEREN`));
      addCell('Account %', trade.pnl_pct == null ? '—' : `${finite(trade.pnl_pct) >= 0 ? '+' : ''}${format(trade.pnl_pct, 3)}%`, `result-value ${finite(trade.pnl_pct) > 0 ? 'good' : finite(trade.pnl_pct) < 0 ? 'bad' : ''}`);
      addCell('Proces', processLabel(trade), `process-chip ${grade.toLowerCase()}`);
      const notes = [trade.r_breach_reason, trade.direction_consistency ? consistencyReason(trade.direction_consistency) : '', trade.process_judgement, trade.lesson].filter(Boolean);
      if (notes.length) row.title = notes.join(' — ');
      row.tabIndex = 0; row.classList.add('journal-clickable'); row.addEventListener('click',()=>openTradeInspector(trade)); row.addEventListener('keydown',(event)=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();openTradeInspector(trade);}});
      body.append(row);
    });
    const empty = $('journalEmpty');
    const hasRows = shown.length > 0;
    table.hidden = !hasRows; empty.hidden = hasRows;
    $('journalShowing').textContent = ui('journal.showing', { shown:shown.length, filtered:trades.length, total:allTrades.length, plural:trades.length === 1 ? '' : 's' });
    $('journalMoreButton').hidden = trades.length <= state.journalLimit;
  }

  function renderWeeklyMentor() {
    const panel = $('weeklyMentorPanel');
    const root = $('weeklyMentorContent');
    const badge = $('weeklyMentorBadge');
    if (!panel || !root || !badge) return;
    const owner = String(state.overview?.principal?.role || '').toLowerCase() === 'owner';
    panel.hidden = !owner;
    if (!owner) return;
    const status = state.overview?.services?.weekly_mentor || {};
    const payload = status.latest_report || {};
    const reports = payload.reports || {};
    const report = reports[state.language] || reports.nl || reports.en || null;
    clear(root);
    const mentorText = (value, limit = 1000) => String(value ?? '').trim().slice(0, limit);
    if (!report) {
      badge.textContent = state.language === 'en' ? 'NO REPORT YET' : 'NOG GEEN RAPPORT';
      badge.className = 'badge neutral';
      const title = state.language === 'en' ? 'No weekly mentor report yet' : 'Nog geen wekelijks mentor-rapport';
      const body = status.enabled
        ? (state.language === 'en' ? 'The first report appears after the configured weekly moment.' : 'Het eerste rapport verschijnt na het ingestelde wekelijkse moment.')
        : (state.language === 'en' ? 'The weekly mentor is disabled and sends nothing automatically.' : 'De wekelijkse mentor staat uit en verstuurt niets automatisch.');
      const empty = create('div', 'empty-state');
      empty.append(create('strong', '', title), create('span', '', body));
      root.append(empty);
      return;
    }
    badge.textContent = state.language === 'en' ? 'LATEST REPORT' : 'LAATSTE RAPPORT';
    badge.className = 'badge good';
    const article = create('article', 'weekly-mentor-card');
    const meta = create('p', 'weekly-mentor-meta muted', `${report.period_start || '—'} → ${report.period_end || '—'} · ${Number(report.trade_count || 0)} ${state.language === 'en' ? 'closed trades' : 'gesloten trades'}`);
    const strengths = create('section', 'weekly-mentor-block');
    strengths.append(create('h4', '', state.language === 'en' ? '3 strengths' : '3 sterke punten'));
    const list = create('ol', 'weekly-mentor-strengths');
    asArray(report.strengths).slice(0, 3).forEach((item) => list.append(create('li', '', mentorText(item, 800))));
    strengths.append(list);
    const pattern = create('section', 'weekly-mentor-block');
    pattern.append(create('h4', '', state.language === 'en' ? '1 journal pattern' : '1 patroon uit je dagboek'));
    pattern.append(create('p', '', mentorText(report.pattern, 1000)));
    const lesson = report.lesson || {};
    const lessonBlock = create('section', 'weekly-mentor-block weekly-mentor-lesson');
    lessonBlock.append(create('h4', '', state.language === 'en' ? '1 lesson' : '1 les'));
    lessonBlock.append(create('strong', '', mentorText(lesson.title, 240)));
    lessonBlock.append(create('p', '', mentorText(lesson.summary, 1000)));
    const safety = create('p', 'weekly-mentor-safety', mentorText(report.safety, 400));
    article.append(meta, strengths, pattern, lessonBlock, safety);
    root.append(article);
  }

  function renderDeepdives(rows) {
    $('deepdivesMeta').textContent = `${rows.length} les${rows.length === 1 ? '' : 'sen'}`;
    const root = clear($('deepdivesList'));
    rows.slice(-20).reverse().forEach((row) => {
      const card = create('article', 'deepdive-card');
      const head = create('div', 'deepdive-card-head');
      head.append(create('h4', '', row.title || `${row.symbol || 'Trade'} · ${dateText(row.time || row.at)}`));
      const grade = String(row.proces_grade || '').toUpperCase();
      if (grade) head.append(create('span', `badge ${grade === 'A' ? 'good' : grade === 'B' ? 'wait' : 'bad'}`, `${grade}-PROCES`));
      card.append(head);
      if (row.oordeel || row.summary || row.analysis) card.append(create('p', '', row.oordeel || row.summary || row.analysis));
      if (row.wat_ging_goed) card.append(create('p', '', `Goed: ${row.wat_ging_goed}`));
      if (row.wat_kan_beter) card.append(create('p', '', `Beter: ${row.wat_kan_beter}`));
      if (row.les || row.next_action) card.append(create('p', 'lesson', row.les || row.next_action));
      const lens = row.coach_loop_lesson;
      if (lens && (lens.title || lens.summary)) {
        const lensCard = create('div', 'coach-loop-lens');
        lensCard.append(create('span', 'coach-loop-lens-label', state.language === 'en' ? 'KNOWLEDGE LENS' : 'KENNISLENS'));
        if (lens.title) lensCard.append(create('strong', '', lens.title));
        if (lens.summary) lensCard.append(create('p', '', lens.summary));
        lensCard.append(create('small', 'muted', state.language === 'en' ? 'Observation lens only — never a trading signal.' : 'Alleen een observatielens — nooit een handelssignaal.'));
        card.append(lensCard);
      }
      root.append(card);
    });
    if (!root.childNodes.length) root.append(create('div', 'empty-state', 'Nog geen deepdives. Na een afgeronde trade verschijnt hier de procesles.'));
  }

  function renderPerformance() {
    const journal = state.overview?.journal || {};
    const stats = journal.stats || {};
    const trades = asArray(journal.trades);
    const tradeCount = Number(statValue(stats, 'trades', trades.length)) || trades.length;
    const wins = Number(statValue(stats, 'wins', trades.filter((trade) => tradeResult(trade) === 'win').length)) || 0;
    const winrate = finite(statValue(stats, 'winrate', tradeCount ? wins / tradeCount * 100 : null));
    const snapshotCoverage = finite(statValue(stats, 'snapshot_coverage_pct', statValue(stats, 'snapshot_coverage')));
    const totalPnl = finite(stats.total_pnl);
    const totalPnlPct = finite(stats.total_pnl_pct);
    const expectancyPct = finite(stats.expectancy_pct);
    const avgWinPct = finite(stats.avg_win_pct); const avgLossPct = finite(stats.avg_loss_pct);
    const sampleLabel = sampleLabelForCount(tradeCount);

    const verifiedCount = Number(stats.verified_source_count || 0);
    $('performanceMeta').textContent = state.language === 'en' ? `${tradeCount} completed close record${tradeCount === 1 ? '' : 's'} · ${verifiedCount} Bybit verified` : `${tradeCount} afgeronde sluitingsrecord${tradeCount === 1 ? '' : 's'} · ${verifiedCount} Bybit-geverifieerd`;
    const watcher = state.overview?.services?.account_watcher || {};
    const watcherBadge = $('journalSourceStatus');
    if (watcherBadge) {
      const healthy = watcher.configured === true && watcher.running === true && !watcher.last_error;
      const missing = watcher.configured === false;
      watcherBadge.textContent = healthy ? 'BYBIT-WATCHER ACTIEF' : missing ? 'BYBIT NIET GECONFIGUREERD' : 'WATCHER CONTROLEREN';
      watcherBadge.className = `badge ${healthy ? 'good' : missing ? 'neutral' : 'bad'}`;
      watcherBadge.title = watcher.last_error || (watcher.last_success ? `Laatste succesvolle controle: ${dateText(watcher.last_success)}` : 'Nog geen succesvolle accountcontrole vastgelegd.');
    }
    const quality = $('performanceDataQuality');
    if (quality) {
      const sourceCounts = stats.source_counts || {};
      const unknown = Number(stats.unknown_source_count || sourceCounts.UNKNOWN || 0);
      const snapshotCount = Number(stats.snapshot_count || 0);
      const sourceText = `${verifiedCount}/${tradeCount} Bybit-geverifieerd`;
      const coverageText = `${snapshotCount}/${tradeCount} met historische equity`;
      const updatedText = state.overview?.updated_at ? `bijgewerkt ${dateText(state.overview.updated_at)}` : 'bijwerktijd onbekend';
      quality.textContent = state.language === 'en' ? `Source: ${pnlBasisLabel(stats.pnl_basis)} · ${verifiedCount}/${tradeCount} Bybit verified · Coverage: ${snapshotCount}/${tradeCount} with historical equity · ${state.overview?.updated_at ? `updated ${dateText(state.overview.updated_at)}` : 'update time unknown'}${unknown ? ` · ${unknown} source record(s) unknown` : ''}.` : `Bron: ${pnlBasisLabel(stats.pnl_basis)} · ${sourceText} · Dekking: ${coverageText} · ${updatedText}${unknown ? ` · ${unknown} bronrecord(s) onbekend` : ''}.`;
      quality.className = `notice performance-quality ${unknown || snapshotCount < tradeCount ? 'warning' : 'success'}`;
    }
    $('performanceSample').textContent = String(sampleLabel).toUpperCase();
    $('performanceSample').className = `badge ${tradeCount >= 100 ? 'good' : tradeCount >= 30 ? 'wait' : 'neutral'}`;
    const percentageReason = percentageMetricsReason(stats, tradeCount);
    const pfDisplay = tradeCount < 10 ? ui('metrics.sample.insufficient') : (stats.profit_factor_display || (stats.profit_factor == null ? '—' : format(stats.profit_factor, 2)));
    const pfTone = tradeCount < 30 ? 'neutral' : (finite(stats.profit_factor) >= 1.5 || stats.profit_factor_infinite ? 'good' : finite(stats.profit_factor) < 1 ? 'bad' : 'wait');
    const expectancyDisplay = expectancyPct == null ? (stats.expectancy_usdt == null ? '—' : money(stats.expectancy_usdt)) : `${expectancyPct >= 0 ? '+' : ''}${format(expectancyPct, 3)}%`;
    const expectancyDetail = expectancyPct == null ? `${percentageReason} · ${stats.expectancy_usdt == null ? 'Geen USDT-waarde' : `${money(stats.expectancy_usdt)} per record`}` : `${money(stats.expectancy_usdt)} per record`;
    const avgDisplay = avgWinPct == null && avgLossPct == null ? `${money(stats.avg_win)} / -${money(stats.avg_loss)}` : `+${format(avgWinPct || 0, 3)}% / -${format(avgLossPct || 0, 3)}%`;
    const drawdownDisplay = stats.max_drawdown_pct == null ? (stats.max_drawdown == null ? '—' : money(stats.max_drawdown)) : `${format(stats.max_drawdown_pct, 2)}%`;
    const summaryKpis = clear($('performanceSummaryKpis'));
    summaryKpis.append(
      createPerformanceKpi('Totaal resultaat', totalPnl == null ? '—' : money(totalPnl), totalPnlPct == null ? percentageReason : `${totalPnlPct >= 0 ? '+' : ''}${format(totalPnlPct, 3)}% van account`, totalPnl > 0 ? 'good' : totalPnl < 0 ? 'bad' : 'neutral'),
      createPerformanceKpi('Winstpercentage', tradeCount ? `${wins}/${tradeCount} · ${format(winrate, 0)}%` : '—', tradeCount < 30 ? 'Voorlopig: te weinig trades voor conclusies' : 'Gebaseerd op afgeronde sluitingsrecords', tradeCount < 30 ? 'neutral' : winrate >= 55 ? 'good' : winrate == null ? 'neutral' : 'wait'),
      createPerformanceKpi('Max. drawdown', drawdownDisplay, stats.max_drawdown_pct == null ? `${percentageReason} · ${money(stats.max_drawdown)}` : money(stats.max_drawdown), stats.max_drawdown_pct == null ? 'neutral' : finite(stats.max_drawdown_pct) > 10 ? 'bad' : finite(stats.max_drawdown_pct) > 5 ? 'wait' : 'neutral'),
      createPerformanceKpi('Datadekking', snapshotCoverage == null ? '—' : `${format(snapshotCoverage, 0)}%`, `${stats.snapshot_count || 0} van ${tradeCount} records met historische rekeningwaarde`, snapshotCoverage >= 100 ? 'good' : snapshotCoverage >= 60 ? 'wait' : 'bad')
    );
    const advancedKpis = clear($('performanceAdvancedKpis'));
    advancedKpis.append(
      createPerformanceKpi('Winstfactor', pfDisplay, tradeCount < 30 ? `${tradeCount}/30 records · te kleine steekproef` : (stats.profit_factor_infinite ? 'Nog geen verliesrecord' : 'Brutowinst gedeeld door brutoverlies'), pfTone),
      createPerformanceKpi('Verwachtingswaarde', expectancyDisplay, expectancyDetail, expectancyPct == null || tradeCount < 30 ? 'neutral' : expectancyPct > 0 ? 'good' : expectancyPct < 0 ? 'bad' : 'neutral'),
      createPerformanceKpi('Gem. winst / verlies', avgDisplay, avgWinPct == null && avgLossPct == null ? percentageReason : `${money(stats.avg_win)} / -${money(stats.avg_loss)}`, 'neutral'),
      createPerformanceKpi('Verwachting in R', stats.expectancy_r == null ? '—' : `${format(stats.expectancy_r, 2)}R`, 'Alleen records met een opgeslagen R-resultaat', tradeCount < 30 ? 'neutral' : finite(stats.expectancy_r) > 0 ? 'good' : finite(stats.expectancy_r) < 0 ? 'bad' : 'neutral'),
      createPerformanceKpi('Grootste verliesreeks', stats.max_loss_streak == null ? '—' : String(stats.max_loss_streak), 'Aaneengesloten verliestrades', finite(stats.max_loss_streak) >= 5 ? 'bad' : finite(stats.max_loss_streak) >= 3 ? 'wait' : 'neutral'),
      createPerformanceKpi('Kosten', money((finite(stats.fees) || 0) + (finite(stats.funding) || 0) + (finite(stats.slippage) || 0)), `Fees ${money(stats.fees || 0)} · funding ${money(stats.funding || 0)} · slippage ${money(stats.slippage || 0)}`, 'neutral'),
      createPerformanceKpi('MAE / MFE', stats.avg_mae_r == null && stats.avg_mfe_r == null ? '—' : `${format(stats.avg_mae_r, 2)}R / ${format(stats.avg_mfe_r, 2)}R`, 'Gemiddelde ongunstige / gunstige beweging', 'neutral')
    );
    const dataBadge = $('performanceDataBadge');
    if (dataBadge) {
      dataBadge.textContent = snapshotCoverage >= 100 && verifiedCount === tradeCount ? 'DATA COMPLEET' : 'DATA IN OPBOUW';
      dataBadge.className = `badge ${snapshotCoverage >= 100 && verifiedCount === tradeCount ? 'good' : 'wait'}`;
    }

    renderEquityCurve(trades, stats);
    const directions = Object.keys(stats.per_richting || {}).length ? stats.per_richting : aggregateTrades(trades, tradeDirection);
    const symbols = Object.keys(stats.per_symbool || {}).length ? stats.per_symbool : aggregateTrades(trades, (trade) => String(trade.symbol || trade.asset || 'Onbekend').toUpperCase());
    renderBreakdown($('directionBreakdown'), directions, (key) => key === 'long' ? 'Long' : key === 'short' ? 'Short' : key);
    renderBreakdown($('symbolBreakdown'), symbols);
    $('sampleNotice').textContent = state.language === 'en'
      ? (tradeCount < 30 ? `Insufficient sample: ${tradeCount} trade${tradeCount === 1 ? '' : 's'} is too small a sample. The figures are visible, but not yet reliable enough to change your rules.` : `Sample: ${sampleLabel}. Use process quality and drawdown alongside win rate and PnL.`)
      : (tradeCount < 30 ? `Onvoldoende steekproef: ${tradeCount} trade${tradeCount === 1 ? '' : 's'} is een te kleine steekproef. De cijfers zijn zichtbaar, maar nog niet betrouwbaar genoeg om je regels te veranderen.` : `Steekproef: ${sampleLabel}. Gebruik proceskwaliteit en drawdown naast winrate en PnL.`);

    updateJournalSymbolOptions(trades); renderJournalTable(); renderDeepdives(asArray(journal.deepdives));
  }

  function exportJournalCsv() {
    const trades = filteredJournalTrades();
    if (!trades.length) return;
    const headers = ['Trade_id','Source','Source_class','Datum','Markt','Richting','Close_side','Richting_consistentie','Instap','Uitstap','Qty','Equity_snapshot','Stop','Risico_pct','R_resultaat','PnL_USD','PnL_account_pct','Open_fee','Close_fee','Fees','Funding','Slippage','MAE_R','MFE_R','Regels_gevolgd','Proces_grade','Les'];
    const csvSafe = (value) => {
      let text = String(value ?? '');
      if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`;
      return text.replaceAll('"', '""');
    };
    const quote = (value) => `"${csvSafe(value)}"`;
    const rows = trades.map((trade) => [
      trade.id, sourceLabel(trade), trade.source_class, trade.closed_at || trade.time || trade.at,
      trade.symbol || trade.asset, tradeDirection(trade), trade.close_side, trade.direction_consistency,
      trade.entry, trade.exit, trade.qty, trade.equity_snapshot, trade.stop_loss, trade.risk_pct, trade.r_multiple,
      trade.pnl, trade.pnl_pct, trade.open_fee, trade.close_fee, trade.fees, trade.funding, trade.slippage,
      trade.mae_r, trade.mfe_r, trade.rules_followed, trade.process_grade, trade.lesson
    ].map(quote).join(','));
    const blob = new Blob([`\ufeff${headers.join(',')}\n${rows.join('\n')}`], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = `mytradingbot-orderdagboek-${new Date().toISOString().slice(0,10)}.csv`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function renderKnowledgeSource() {
    const data = state.overview?.knowledge_source || {};
    $('knowledgeSourceBadge').textContent = data.processor_active && !data.last_error ? 'ACTIEF' : (data.status || 'CONTROLEREN');
    if ($('knowledgeSourceSummary')) $('knowledgeSourceSummary').textContent = state.language === 'en'
      ? `${data.processed ?? 0} lessons processed · latest source ${data.last_video_date || 'unknown'}.`
      : `${data.processed ?? 0} lessen verwerkt · laatste bron ${data.last_video_date || 'onbekend'}.`;
    $('knowledgeSourceBadge').className = `badge ${data.processor_active && !data.last_error ? 'good' : 'wait'}`;
    const root = clear($('knowledgeSourceGrid'));
    [
      ['Laatste bron', data.last_video_date || 'onbekend'],
      ['Titel', data.last_video_title || '—'],
      ['Lessen', data.stored_lessons ?? '—'],
      ['Verwerkt', data.processed ?? '—'],
      ['Wachtrij', `${data.queue ?? '—'} / ${data.queue_total ?? '—'}`],
      ['Laatste controle', data.last_attempt_at ? dateText(data.last_attempt_at) : '—']
    ].forEach(([k,v]) => { const item=create('div','source-status-item'); item.append(create('span','',k),create('strong','',String(v))); root.append(item); });

    const policyRoot = clear($('methodologyPolicy'));
    const method = state.overview?.methodology_sources || {};
    const policyHead = create('div','methodology-policy-head');
    policyHead.append(create('div','', 'Herkomst van de regels'), create('small','', 'Bron, controle en persoonlijke keuze blijven gescheiden.'));
    policyRoot.append(policyHead);
    asArray(method.rules).slice(0, 6).forEach((rule) => {
      const row = create('article','methodology-rule');
      const badge = create('span', `source-badge source-${String(rule.source_label || 'onbevestigd').toLowerCase().replace(/[^a-z0-9]+/g,'-')}`, String(rule.source_label || 'ONBEVESTIGD'));
      row.append(badge, create('strong','',rule.title || 'Regel'), create('p','',rule.statement || ''));
      policyRoot.append(row);
    });

    const timeline = clear($('ingestionTimeline'));
    asArray(state.overview?.knowledge_ingestion).slice(0, 8).forEach((event) => {
      const row = create('div', `ingestion-event ${event.status === 'failed' ? 'bad' : event.status === 'completed' ? 'good' : 'neutral'}`);
      row.append(create('time','',dateText(event.at || event.processed_at || event.started_at)), create('strong','',event.title || event.video_id || 'Video'), create('span','',event.status === 'completed' ? `${event.knowledge_count || 0} lessen` : event.status === 'failed' ? `Mislukt: ${event.error || 'onbekende fout'}` : 'Verwerking gestart'));
      timeline.append(row);
    });
    if (!timeline.childNodes.length) timeline.append(create('p','muted','Nog geen ingestielog beschikbaar.'));

    const managementSection = $('knowledgeManagementSection');
    const managementGrid = $('knowledgeManagementGrid');
    if (managementGrid) {
      clear(managementGrid);
      const rows = [
        [state.language === 'en' ? 'Public RSS' : 'Openbare RSS', data.rss_enabled && data.channel_id_configured ? (state.language === 'en' ? 'Active' : 'Actief') : (state.language === 'en' ? 'Not configured' : 'Niet geconfigureerd')],
        [state.language === 'en' ? 'Worker' : 'Worker', data.worker_running ? (state.language === 'en' ? 'Running' : 'Draait') : (state.language === 'en' ? 'Stopped' : 'Gestopt')],
        [state.language === 'en' ? 'Pending queue' : 'Openstaande wachtrij', `${data.queue ?? '—'} / ${data.queue_total ?? '—'}`],
        [state.language === 'en' ? 'Quarantined' : 'Quarantaine', data.excluded_no_transcript ?? 0],
      ];
      rows.forEach(([label,value]) => { const item=create('div','source-status-item'); item.append(create('span','',label),create('strong','',String(value))); managementGrid.append(item); });
    }
    const autoLine = $('knowledgeAutoFetchLine');
    if (autoLine) {
      if (data.last_auto_fetched_at) {
        const title = data.last_auto_video_title || data.last_auto_video_id || (state.language === 'en' ? 'new video' : 'nieuwe video');
        autoLine.textContent = state.language === 'en' ? `Last automatically fetched: ${dateText(data.last_auto_fetched_at)} · ${title}` : `Laatst automatisch opgehaald: ${dateText(data.last_auto_fetched_at)} · ${title}`;
        autoLine.className = 'notice good';
      } else if (data.rss_enabled && data.channel_id_configured) {
        autoLine.textContent = state.language === 'en' ? `Public channel last checked: ${data.last_rss_check_at ? dateText(data.last_rss_check_at) : 'not yet'}.` : `Openbaar kanaal laatst gecontroleerd: ${data.last_rss_check_at ? dateText(data.last_rss_check_at) : 'nog niet'}.`;
        autoLine.className = 'notice info';
      } else {
        autoLine.textContent = state.language === 'en' ? 'Public channel monitoring is not configured.' : 'Openbare kanaalbewaking is niet geconfigureerd.';
        autoLine.className = 'notice warning';
      }
    }
    const managementBadge = $('knowledgeManagementBadge');
    if (managementBadge) {
      const active = Boolean(data.processor_active && data.worker_running);
      managementBadge.textContent = active ? (state.language === 'en' ? 'ACTIVE' : 'ACTIEF') : (state.language === 'en' ? 'CHECK' : 'CONTROLEREN');
      managementBadge.className = `badge ${active ? 'good' : 'wait'}`;
    }
    if ($('knowledgeManagementSummary')) $('knowledgeManagementSummary').textContent = state.language === 'en'
      ? 'Public channel monitoring and manual Platinum links use the same safe queue.'
      : 'Openbare kanaalbewaking en handmatige Platinum-links gebruiken dezelfde veilige wachtrij.';

    const warningParts = [data.warning, data.last_error ? `Laatste fout: ${data.last_error}` : '', data.rss_last_error ? `RSS: ${data.rss_last_error}` : ''].filter(Boolean);
    $('knowledgeSourceWarning').textContent = warningParts.join(' · ');
    $('knowledgeSourceWarning').classList.toggle('hidden', warningParts.length === 0);
  }


  function patternEventLabel(event) {
    const labels = state.language === 'en'
      ? {suggestion_created:'Suggestion created',suggestion_expired:'Suggestion expired',rule_activated:'Rule activated by owner',rule_deactivated:'Rule deactivated by owner'}
      : {suggestion_created:'Suggestie aangemaakt',suggestion_expired:'Suggestie verlopen',rule_activated:'Regel door eigenaar geactiveerd',rule_deactivated:'Regel door eigenaar gedeactiveerd'};
    return labels[String(event || '')] || String(event || '').replaceAll('_',' ');
  }

  function renderJournalPatternGates() {
    const section = $('journalPatternGateSection');
    if (!section) return;
    const owner = String(state.overview?.principal?.role || '').toLowerCase() === 'owner';
    section.classList.toggle('hidden', !owner);
    if (!owner) return;
    const data = state.overview?.journal_pattern_gates || {};
    const open = asArray(data.open_suggestions);
    const active = asArray(data.active_rules);
    const inactive = asArray(data.inactive_rules);
    $('journalPatternGateBadge').textContent = state.language === 'en' ? `${open.length} OPEN · ${active.length} ACTIVE` : `${open.length} OPEN · ${active.length} ACTIEF`;
    $('journalPatternGateBadge').className = `badge ${active.length ? 'wait' : open.length ? 'neutral' : 'good'}`;
    $('journalPatternGateSummary').textContent = state.language === 'en'
      ? 'Patterns are suggestions only. No rule is ever activated automatically.'
      : 'Patronen zijn alleen voorstellen. Geen regel wordt ooit automatisch geactiveerd.';
    $('journalPatternGateSafety').textContent = state.language === 'en'
      ? 'Suggestions expire. Activated rules remain visible until you consciously deactivate one with confirmation and a written reason.'
      : 'Suggesties verlopen. Geactiveerde regels blijven zichtbaar tot jij er bewust één deactiveert met bevestiging en een geschreven reden.';

    const suggestions = clear($('journalPatternSuggestions'));
    open.forEach((row) => {
      const card = create('article','pattern-suggestion');
      const head = create('div','pattern-item-head');
      head.append(create('strong','',state.language === 'en' ? (row.message_en || row.label_en || 'Journal pattern') : (row.message_nl || row.label_nl || 'Dagboekpatroon')), create('span','badge wait',`${row.loss_count || 0}/${row.sample_count || 0}`));
      const evidence = create('div','pattern-evidence');
      asArray(row.evidence).forEach((trade) => evidence.append(create('span','pattern-evidence-chip',`${trade.symbol || 'TRADE'} · ${format(trade.pnl,2)} · ${trade.grade || '?'}`)));
      const meta = create('p','muted small-copy',state.language === 'en'
        ? `Evidence: ${row.loss_count || 0} losses · expires ${dateText(row.expires_at)}. Nothing is active yet.`
        : `Bewijs: ${row.loss_count || 0} verliezen · verloopt ${dateText(row.expires_at)}. Er is nog niets actief.`);
      const button = create('button','button primary',state.language === 'en' ? 'Activate extra blocker' : 'Activeer extra blokkade');
      button.type='button'; button.dataset.patternActivate=row.id;
      card.append(head,meta,evidence,button); suggestions.append(card);
    });
    if (!open.length) suggestions.append(create('div','empty-state',state.language === 'en' ? `No honest pattern meets the minimum sample of ${data.minimum_repetitions || 4} losses.` : `Geen eerlijk patroon haalt de minimumsteekproef van ${data.minimum_repetitions || 4} verliezen.`));

    const rules = clear($('journalPatternRules'));
    active.forEach((rule) => {
      const card=create('article','pattern-rule active');
      const head=create('div','pattern-item-head'); head.append(create('strong','',rule.reason || 'Dagboekregel'),create('span','badge bad',state.language === 'en'?'BLOCKS':'BLOKKEERT'));
      const meta=create('p','muted small-copy',state.language === 'en' ? `Activated ${dateText(rule.activated_at)} by ${rule.activated_by || 'owner'}. Only changes orderable from true to false.` : `Geactiveerd ${dateText(rule.activated_at)} door ${rule.activated_by || 'owner'}. Verandert orderable alleen van true naar false.`);
      const button=create('button','button quiet',state.language === 'en'?'Consciously deactivate…':'Bewust deactiveren…'); button.type='button'; button.dataset.patternDeactivate=rule.id;
      card.append(head,meta,button); rules.append(card);
    });
    inactive.slice(0,5).forEach((rule) => {
      const card=create('article','pattern-rule inactive');
      card.append(create('strong','',rule.reason || 'Dagboekregel'),create('p','muted small-copy',state.language === 'en' ? `Deactivated ${dateText(rule.deactivated_at)} · ${rule.deactivation_reason || 'reason logged'}` : `Gedeactiveerd ${dateText(rule.deactivated_at)} · ${rule.deactivation_reason || 'reden gelogd'}`));
      rules.append(card);
    });
    if (!active.length && !inactive.length) rules.append(create('div','empty-state',state.language === 'en'?'No owner-confirmed journal gates yet.':'Nog geen door de eigenaar bevestigde dagboekpoorten.'));

    const audit=clear($('journalPatternAudit'));
    asArray(data.audit).slice(0,30).forEach((row) => {
      const item=create('div','pattern-audit-item'); item.append(create('time','',dateText(row.at)),create('strong','',patternEventLabel(row.event)),create('p','',`${row.reason || '—'} · ${row.actor || 'system'}`)); audit.append(item);
    });
    if (!audit.childNodes.length) audit.append(create('p','muted',state.language === 'en'?'No audit events yet.':'Nog geen auditgebeurtenissen.'));
  }

  async function activateJournalPatternRule(suggestionId, button) {
    if (!suggestionId || button?.disabled) return;
    if (button) button.disabled=true;
    try {
      await api('/api/v1/pattern-gates/activate',{method:'POST',body:{suggestion_id:suggestionId},timeout:30000});
      await loadOverview({silent:true});
    } catch(error) {
      alert(error.message);
    } finally { if (button) button.disabled=false; }
  }

  async function deactivateJournalPatternRule(ruleId, button) {
    if (!ruleId || button?.disabled) return;
    const reason=prompt(state.language === 'en' ? 'Why are you consciously deactivating this rule? This reason is permanently logged.' : 'Waarom deactiveer je deze regel bewust? Deze reden wordt blijvend gelogd.');
    if (!reason) return;
    const confirmed=confirm(state.language === 'en' ? 'Confirm: deactivate this extra blocker. Existing engine gates remain unchanged.' : 'Bevestig: deactiveer deze extra blokkade. Bestaande motorpoorten blijven ongewijzigd.');
    if (!confirmed) return;
    if (button) button.disabled=true;
    try {
      await api('/api/v1/pattern-gates/deactivate',{method:'POST',body:{rule_id:ruleId,reason,confirm:'DEACTIVEER REGEL'},timeout:30000});
      await loadOverview({silent:true});
    } catch(error) {
      alert(error.message);
    } finally { if (button) button.disabled=false; }
  }

  function openTradeInspector(trade) {
    $('tradeInspectorTitle').textContent = `${String(trade.symbol || trade.asset || 'Trade').toUpperCase()} · ${tradeDirection(trade).toUpperCase()}`;
    $('tradeInspectorSubtitle').textContent = dateText(trade.closed_at || trade.time || trade.at);
    const root=clear($('tradeInspectorBody'));
    const sections=[
      ['Voor de trade', [['Instap',format(trade.entry,8)],['Geplande stop',format(trade.stop_loss||trade.sl,8)],['Gepland risico',trade.risk_pct==null?'—':`${format(trade.risk_pct,2)}%`],['Setup',trade.setup_type||trade.setup||'—'],['Thesis',trade.thesis||trade.reason||'Niet opgeslagen']]],
      ['Tijdens de trade', [['Uitstap',format(trade.exit,8)],['Grootte',format(trade.qty||trade.size,8)],['Lifecycle',trade.lifecycle||trade.trade_type||'Niet opgeslagen'],['Management',trade.management||trade.actions||'Niet opgeslagen']]],
      ['Na de trade', [['PnL',money(trade.pnl)],['Account %',trade.pnl_pct==null?'—':`${format(trade.pnl_pct,3)}%`],['R-resultaat',trade.r_multiple==null?'—':`${format(trade.r_multiple,2)}R`],['Bron',sourceLabel(trade)],['Trade-ID',trade.id||'—'],['Close-side',trade.close_side||'—'],['Richtingcontrole',consistencyLabel(trade.direction_consistency)],['Equity-snapshot',trade.equity_snapshot==null?'—':money(trade.equity_snapshot)],['Proces',processLabel(trade)],['Les',trade.lesson||trade.process_judgement||'Nog geen les gekoppeld']]]
    ];
    sections.forEach(([title,rows])=>{const sec=create('section','inspector-section'); sec.append(create('h3','',title)); const grid=create('div','inspector-grid'); rows.forEach(([k,v])=>{const x=create('div','');x.append(create('span','',k),create('strong','',String(v)));grid.append(x)}); sec.append(grid); root.append(sec);});
    if (trade.r_breach_alarm) {
      const alarm=create('div','notice danger r-breach-alert');
      alarm.append(
        create('strong','',state.language === 'en' ? `R < -1 alarm · ${format(trade.r_multiple,2)}R` : `R < -1-alarm · ${format(trade.r_multiple,2)}R`),
        create('span','',trade.r_breach_reason || (state.language === 'en' ? 'Check whether the technical stop was widened or execution materially deviated.' : 'Controleer of de technische stop is verruimd of de uitvoering materieel afweek.'))
      );
      root.append(alarm);
    }
    const snapshots=create('section','inspector-section'); snapshots.append(create('h3','','Grafiekbewijs 1D → 4H → 15M → 3M'),create('p','muted','Snapshots worden alleen getoond wanneer ze bij deze trade zijn opgeslagen. Ontbrekende beelden worden niet verzonnen.')); root.append(snapshots);
    $('tradeInspector').showModal();
  }

  function knowledgeStatusLabel(value) {
    const raw = String(value || '').trim().toLowerCase();
    const en = { gecontroleerd:'reviewed', reviewed:'reviewed', bevestigd:'confirmed', confirmed:'confirmed', onbevestigd:'unconfirmed', unconfirmed:'unconfirmed' };
    const nl = { gecontroleerd:'gecontroleerd', reviewed:'gecontroleerd', bevestigd:'bevestigd', confirmed:'bevestigd', onbevestigd:'onbevestigd', unconfirmed:'onbevestigd' };
    return (state.language === 'en' ? en : nl)[raw] || (raw || (state.language === 'en' ? 'status unknown' : 'status onbekend'));
  }

  function renderCoachMode() {
    const toggle = $('coachExpertMode');
    if (toggle) toggle.checked = Boolean(state.expertMode);
    const badge = $('coachModeBadge');
    if (badge) {
      badge.textContent = state.expertMode ? 'EXPERT' : (state.language === 'en' ? 'CLEAR' : 'HELDER');
      badge.className = `badge ${state.expertMode ? 'wait' : 'good'}`;
    }
    const title = $('coachStyleTitle');
    if (title) title.textContent = state.expertMode
      ? (state.language === 'en' ? 'Expert mode' : 'Expertmodus')
      : (state.language === 'en' ? 'Clear and step by step' : 'Helder en stap voor stap');
    const hint = $('coachStyleHint');
    if (hint) hint.textContent = state.expertMode
      ? (state.language === 'en' ? 'The coach answers briefly and technically, without changing any safety rule.' : 'De coach antwoordt kort en technisch, zonder één veiligheidsregel te veranderen.')
      : (state.language === 'en' ? 'By default, the coach explains difficult concepts in everyday language, with one analogy and a small example.' : 'Standaard legt de coach lastige begrippen uit in gewone taal, met één analogie en een klein voorbeeld.');
  }

  function setCoachMode(expert, { persist = true } = {}) {
    state.expertMode = Boolean(expert);
    if (persist) {
      try { localStorage.setItem(COACH_MODE_KEY, state.expertMode ? 'expert' : 'clear'); } catch {}
    }
    renderCoachMode();
  }

  function lessonExplainQuestion(row) {
    const title = String(row?.title || (state.language === 'en' ? 'this concept' : 'dit begrip')).trim();
    const summary = String(row?.summary || '').trim();
    if (state.expertMode) {
      return state.language === 'en'
        ? `Expert mode. Explain the concept "${title}" briefly and technically. Define any necessary jargon. Give one small fictional example and do not create a current setup, entry, stop or target.${summary ? ` Stay grounded in this lesson: ${summary}` : ''}`
        : `Expertmodus. Leg het begrip "${title}" kort en technisch uit. Verklaar noodzakelijke vaktermen. Geef één klein fictief voorbeeld en maak geen actuele setup, entry, stop of target.${summary ? ` Blijf bij deze les: ${summary}` : ''}`;
    }
    return state.language === 'en'
      ? `Explain the concept "${title}" as if you were explaining it to a 16-year-old. Use short sentences, one simple analogy and one small fictional example. Explain jargon immediately and do not create a current setup, entry, stop or target.${summary ? ` Stay grounded in this lesson: ${summary}` : ''}`
      : `Leg het begrip "${title}" uit alsof je het aan een 16-jarige uitlegt. Gebruik korte zinnen, één simpele analogie en één klein fictief voorbeeld. Leg jargon meteen uit en maak geen actuele setup, entry, stop of target.${summary ? ` Blijf bij deze les: ${summary}` : ''}`;
  }

  async function explainKnowledge(row) {
    const coachPanel = $('coachPanel');
    if (coachPanel) { coachPanel.open = true; updateCollapseText(coachPanel); }
    const displayQuestion = state.language === 'en' ? `Explain: ${row?.title || 'this concept'}` : `Leg uit: ${row?.title || 'dit begrip'}`;
    if (coachPanel) coachPanel.scrollIntoView({ behavior:'smooth', block:'start' });
    return askCoach(lessonExplainQuestion(row), 'coachMessages', { displayQuestion });
  }

  function renderKnowledge() {
    const rows = asArray(state.overview?.knowledge);
    $('knowledgeMeta').textContent = state.language === 'en' ? `${rows.length} lesson${rows.length === 1 ? '' : 's'}` : `${rows.length} les${rows.length === 1 ? '' : 'sen'}`;
    const filter = $('knowledgeFilter').value;
    const types = [...new Set(rows.map((row) => row.type).filter(Boolean))].sort();
    const currentOptions = [...$('knowledgeFilter').options].map((option) => option.value);
    if (types.some((type) => !currentOptions.includes(type))) {
      types.forEach((type) => { if (!currentOptions.includes(type)) { const option = create('option'); option.value = type; option.textContent = type; $('knowledgeFilter').append(option); } });
    }
    const root = clear($('knowledgeList'));
    rows.filter((row) => filter === 'all' || row.type === filter).slice(0, 30).forEach((row) => {
      const item = create('article', 'knowledge-item');
      const head = create('div','knowledge-item-head');
      head.append(create('h3','',row.title || 'Les'), create('span', `source-badge source-${String(row.source_label || 'onbevestigd').toLowerCase().replace(/[^a-z0-9]+/g,'-')}`, row.source_label || 'ONBEVESTIGD'));
      item.append(head, create('p', '', row.summary || 'Geen samenvatting.'));
      const meta = create('small','knowledge-meta', state.language === 'en' ? `${row.date || 'date unknown'} · ${row.source_title || row.type || 'source unknown'} · confidence ${row.confidence ?? 0}% · ${knowledgeStatusLabel(row.official_status)}` : `${row.date || 'datum onbekend'} · ${row.source_title || row.type || 'bron onbekend'} · betrouwbaarheid ${row.confidence ?? 0}% · ${knowledgeStatusLabel(row.official_status)}`);
      item.append(meta);
      if (row.evidence) item.append(create('p','knowledge-evidence',`${state.language === 'en' ? 'Evidence' : 'Onderbouwing'}: ${row.evidence}`));
      const actions = create('div', 'knowledge-actions');
      const explainButton = create('button', 'button quiet compact explain-lesson-button', state.language === 'en' ? 'Explain' : 'Leg uit');
      explainButton.type = 'button';
      explainButton.setAttribute('aria-label', state.language === 'en' ? `Explain ${row.title || 'this concept'}` : `Leg ${row.title || 'dit begrip'} uit`);
      explainButton.addEventListener('click', async () => {
        explainButton.disabled = true;
        try { await explainKnowledge(row); }
        finally { explainButton.disabled = false; }
      });
      actions.append(create('span','muted', state.language === 'en' ? 'The coach explains this in everyday language.' : 'De coach legt dit uit in gewone taal.'), explainButton);
      item.append(actions);
      root.append(item);
    });
    if (!root.childNodes.length) root.append(create('div', 'empty-state', 'Geen lessen voor dit filter.'));
  }

  function renderAudit() {
    const rows = asArray(state.overview?.activity);
    const errors = rows.filter((row) => /error|failed|failure|blocked|fout|mislukt|geblokkeerd/i.test(`${row.type || ''} ${row.note || ''}`));
    const latestAt = rows.map((row) => row.at).filter(Boolean).sort().at(-1) || state.overview?.updated_at;
    $('auditMeta').textContent = state.language === 'en' ? `${errors.length} error${errors.length === 1 ? '' : 's'}` : `${errors.length} fout${errors.length === 1 ? '' : 'en'}`;
    $('auditMeta').className = `badge ${errors.length ? 'bad' : 'good'}`;
    const statusLine = $('auditStatusLine');
    if (statusLine) {
      statusLine.textContent = errors.length
        ? (state.language === 'en' ? `Last run: ${errors.length} error${errors.length === 1 ? '' : 's'} · ${dateText(latestAt)}` : `Laatste run: ${errors.length} fout${errors.length === 1 ? '' : 'en'} · ${dateText(latestAt)}`)
        : (state.language === 'en' ? `Last run OK · 0 errors · ${dateText(latestAt)}` : `Laatste run OK · 0 fouten · ${dateText(latestAt)}`);
      statusLine.className = `summary-copy audit-summary-line ${errors.length ? 'bad' : 'good'}`;
    }
    const root = clear($('activityTimeline'));
    rows.slice(0, 60).forEach((row) => {
      const note = String(row.note || '');
      const confidence = note.match(/(?:·|—)?\s*(\d+(?:[.,]\d+)?)%\s+zekerheid/i);
      const cleanNote = confidence ? note.replace(confidence[0], '').trim().replace(/[·—-]\s*$/u, '').trim() : note;
      const noteText = [cleanNote, confidence ? ui('audit.confidence', { pct: confidence[1].replace(',', '.') }) : ''].filter(Boolean).join(' · ');
      const item = create('article', 'activity-item'); item.append(create('time', '', dateText(row.at)), create('p', '', `${activityLabel(row.type)}${row.timeframe ? ` · ${row.timeframe}` : ''}${noteText ? ` — ${noteText}` : ''}`)); root.append(item);
    });
    if (!root.childNodes.length) root.append(create('div', 'empty-state', 'Nog geen systeemmeldingen.'));
  }

  function activityLabel(type) {
    const labels = { chart_synced: 'Grafiek gesynchroniseerd', chart_unchanged: 'Grafiek ongewijzigd', chart_confirmed: 'Grafieklaag gecontroleerd', layer_confirmed: 'Laag opgeslagen', prepared: 'Ticket voorbereid', ticket_failed: 'Ticket geblokkeerd', submitted: 'Plaatsing geregistreerd', tp1_prepared: 'Doel 1 voorbereid', tp2_prepared: 'Doel 2 voorbereid', tp3_prepared: 'Doel 3 voorbereid' };
    return labels[type] || String(type || 'Melding').replaceAll('_', ' ');
  }

  function downloadJson(filename, value) {
    const blob = new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = filename; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function loadBetaAdmin() {
    if (state.overview?.principal?.role !== 'owner') return;
    try {
      const data = await api('/api/v2/beta/testers');
      const inviteRows = asArray(data.invites);
      const activeInvites = inviteRows.filter((row) => !row.revoked && !row.expired && Number(row.remaining || 0) > 0);
      const oldInvites = inviteRows.filter((row) => !activeInvites.includes(row));
      const testerRows = asArray(data.testers);
      const activeTesters = testerRows.filter((row) => !row.revoked);
      const oldTesters = testerRows.filter((row) => row.revoked);
      $('testerCount').textContent = String(activeTesters.length);
      $('testerHistoryCount').textContent = String(oldTesters.length);
      $('inviteCount').textContent = String(activeInvites.length);
      $('inviteHistoryCount').textContent = String(oldInvites.length);

      const renderInvite = (invite, root, historical = false) => {
        const open = !invite.revoked && !invite.expired && Number(invite.remaining || 0) > 0;
        const status = invite.revoked ? 'revoked' : invite.expired ? 'expired' : Number(invite.remaining || 0) <= 0 ? 'used' : 'open';
        const row = create('article', `tester-row ${historical ? 'revoked' : ''}`);
        const info = create('div');
        info.append(create('strong','',invite.label || 'Uitnodiging'), create('small','',`${status} · geldig tot ${dateText(invite.expires_at)} · ${invite.remaining ?? 0} gebruik(en) over`));
        const button = create('button','button quiet compact',open ? ui('invite.revoke') : ui(`invite.${status}`));
        button.type='button'; button.disabled=!open;
        button.addEventListener('click', async () => { await api('/api/v2/beta/invites/revoke',{method:'POST',body:{invite_id:invite.id}}); await loadBetaAdmin(); });
        row.append(info,button); root.append(row);
      };
      const inviteRoot = clear($('inviteList'));
      activeInvites.forEach((invite) => renderInvite(invite, inviteRoot));
      if (!inviteRoot.childNodes.length) inviteRoot.append(create('div','empty-state',ui('invite.none_open')));
      const inviteHistoryRoot = clear($('inviteHistoryList'));
      oldInvites.forEach((invite) => renderInvite(invite, inviteHistoryRoot, true));
      if (!inviteHistoryRoot.childNodes.length) inviteHistoryRoot.append(create('div','empty-state','Nog geen oude uitnodigingen.'));
      $('inviteHistoryPanel').hidden = oldInvites.length === 0;

      const renderTester = (tester, root, historical = false) => {
        const row = create('article', `tester-row ${historical ? 'revoked' : ''}`);
        const info = create('div'); info.append(create('strong','',tester.display_name || 'Tester'), create('small','',`${tester.mode || 'tester'} · ${tester.revoked ? 'ingetrokken' : 'actief'} · laatst ${dateText(tester.last_seen_at)}`));
        const button = create('button','button quiet compact',tester.revoked ? 'Ingetrokken' : 'Trek toegang in'); button.type='button'; button.disabled=Boolean(tester.revoked);
        button.addEventListener('click', async () => { await api('/api/v2/beta/testers/revoke',{method:'POST',body:{session_id:tester.id}}); await loadBetaAdmin(); });
        row.append(info,button); root.append(row);
      };
      const root = clear($('testerList'));
      activeTesters.forEach((tester) => renderTester(tester, root));
      if (!root.childNodes.length) root.append(create('div','empty-state','Geen actieve beta-testers.'));
      const testerHistoryRoot = clear($('testerHistoryList'));
      oldTesters.forEach((tester) => renderTester(tester, testerHistoryRoot, true));
      if (!testerHistoryRoot.childNodes.length) testerHistoryRoot.append(create('div','empty-state','Nog geen ingetrokken testers.'));
      $('testerHistoryPanel').hidden = oldTesters.length === 0;
    } catch (error) { $('testerList').replaceChildren(create('div','notice danger',error.message)); }
  }

  function renderBetaWorkspace() {
    const principal = state.overview?.principal || {}; const profile = state.overview?.profile || {}; const owner = principal.role === 'owner';
    $('betaModeBadge').textContent = owner ? 'OWNER LIVE' : 'TESTER PAPER'; $('betaModeBadge').className = `badge ${owner ? 'good' : 'wait'}`;
    const root = clear($('betaWorkspaceSummary'));
    [[ 'Naam', principal.display_name || '—' ], [ 'Werkruimte', principal.workspace_id || '—' ], [ 'Modus', owner ? ui('mode.owner') : ui('mode.tester') ], [ 'Rekeningwaarde', owner ? money(state.overview?.account?.equity) : money(profile.manual_equity) ]].forEach(([label,value]) => { const box=create('div'); box.append(create('span','',label),create('strong','',value)); root.append(box); });
    $('ownerBetaAdmin').classList.toggle('hidden', !owner); $('testerBetaTools').classList.toggle('hidden', owner);
    if ($('knowledgeManagementSection')) $('knowledgeManagementSection').classList.toggle('hidden', !owner);
    if ($('journalPatternGateSection')) $('journalPatternGateSection').classList.toggle('hidden', !owner);
    if (owner) loadBetaAdmin();
  }

  async function createInvite(event) {
    event.preventDefault(); const box=$('inviteResult'); box.classList.add('hidden');
    const expiry = String($('inviteExpiry').value || '24h');
    const body = { label: $('inviteLabel').value, max_uses: 1, mode: 'tester' };
    if (expiry.endsWith('m')) body.expires_minutes = Number.parseInt(expiry, 10);
    else if (expiry.endsWith('h')) body.expires_hours = Number.parseInt(expiry, 10);
    else body.expires_days = Number.parseInt(expiry, 10);
    try {
      const data=await api('/api/v2/beta/invites',{method:'POST',body});
      box.textContent=`Uitnodigingscode: ${data.invite.code} · geldig tot ${dateText(data.invite.expires_at)}. Deel deze code één-op-één.`;
      box.className='notice good'; box.classList.remove('hidden');
      await navigator.clipboard.writeText(data.invite.code).catch(()=>{});
      $('inviteForm').reset(); $('inviteExpiry').value='24h';
      await loadBetaAdmin();
    } catch(error){ box.textContent=error.message; box.className='notice danger'; box.classList.remove('hidden'); }
  }

  async function submitPlatinumLink(event) {
    event.preventDefault();
    const result = $('platinumQueueResult');
    const input = $('platinumVideoUrl');
    const button = event.submitter || event.currentTarget.querySelector('button[type="submit"]');
    result.classList.add('hidden');
    if (button) button.disabled = true;
    try {
      const response = await api('/api/v1/knowledge/queue', { method:'POST', body:{ url:input.value }, timeout:30000 });
      const status = response.result?.status || 'queued';
      const messages = {
        queued: state.language === 'en' ? 'Added to the knowledge queue. The worker will process it automatically.' : 'Toegevoegd aan de kenniswachtrij. De worker verwerkt hem automatisch.',
        already_queued: state.language === 'en' ? 'This video is already in the queue.' : 'Deze video staat al in de wachtrij.',
        already_processed: state.language === 'en' ? 'This video has already been processed.' : 'Deze video is al verwerkt.',
        quarantined_no_transcript: state.language === 'en' ? 'This video is quarantined because no usable transcript was available.' : 'Deze video staat in quarantaine omdat geen bruikbaar transcript beschikbaar was.',
      };
      result.textContent = messages[status] || status;
      result.className = `notice ${status === 'queued' ? 'good' : 'info'}`;
      result.classList.remove('hidden');
      input.value = '';
      await loadOverview({ silent:true });
    } catch (error) {
      result.textContent = error.message; result.className = 'notice danger'; result.classList.remove('hidden');
    } finally { if (button) button.disabled = false; }
  }

  async function submitFeedback(event) {
    event.preventDefault(); const status=$('feedbackStatus'); status.classList.add('hidden');
    try { await api('/api/v2/beta/feedback',{method:'POST',body:{category:$('feedbackCategory').value,message:$('feedbackMessage').value,page:location.href}}); status.textContent='Feedback veilig opgeslagen. Dank je.'; status.className='notice good'; status.classList.remove('hidden'); $('feedbackMessage').value=''; setTimeout(()=>$('feedbackDialog').close(),700); } catch(error){ status.textContent=error.message; status.className='notice danger'; status.classList.remove('hidden'); }
  }

  function renderAll() {
    renderHeader(); renderDiscipline(); renderAccountGuard(); renderFocus(); renderDayStart(); renderLayers(); renderDecisionFlow(); renderTicketReadiness(); renderParentChain(); renderMap(); renderPositions(); renderPerformance(); renderWeeklyMentor(); renderKnowledgeSource(); renderBetaWorkspace(); renderJournalPatternGates(); renderCoachMode(); renderKnowledge(); renderAudit();
    switchView(state.activeView, { persist: false });
    $('app').setAttribute('aria-busy', 'false');
    applyLanguage();
  }

  async function loadOverview({ silent = false } = {}) {
    try {
      const data = await api(`/api/v1/overview?asset=${encodeURIComponent(state.asset)}`, { timeout: 45000 });
      const nextStateId = data.state_id || data.latest?.state_id || null;
      if (state.dayStartStateId && nextStateId && state.dayStartStateId !== nextStateId) { state.dayStart = null; state.dayStartStateId = null; }
      state.overview = data;
      state.asset = data.asset || state.asset;
      renderAll();
    } catch (error) {
      if (!silent) {
        const message = friendlyFailure(error);
        state.focusAction = 'refresh';
        $('focusTitle').textContent = message.title;
        $('decisionReason').textContent = message.reason;
        $('nextAction').querySelector('strong').textContent = message.next;
        $('focusActionButton').textContent = message.actionLabel;
        $('focusActionButton').disabled = false;
        $('decisionBadge').textContent = 'ACTIE NODIG';
        $('decisionBadge').className = 'badge bad';
      }
      throw error;
    }
  }

  function stopPolling() {
    if (state.pollTimer) clearInterval(state.pollTimer);
    state.pollTimer = null;
  }

  function showLogin(message = '') {
    stopPolling();
    $('loginLayer').classList.remove('hidden');
    $('app').setAttribute('aria-hidden', 'true');
    $('loginError').textContent = message;
    $('loginError').classList.toggle('hidden', !message);
  }
  function hideLogin() { $('loginLayer').classList.add('hidden'); $('app').removeAttribute('aria-hidden'); }

  async function authenticate(token) {
    state.token = String(token || '').trim();
    if (!DEMO && state.token.length < 32) throw new Error('Gebruik het Railway-token van minimaal 32 tekens.');
    await api('/api/v1/config');
    if (!DEMO) sessionStorage.setItem(TOKEN_KEY, state.token);
    hideLogin(); await loadOverview(); startPolling();
  }

  function startPolling() {
    stopPolling();
    if (STATIC_CAPTURE) return;
    state.pollTimer = setInterval(() => { if (document.visibilityState === 'visible') loadOverview({ silent: true }).catch(() => {}); }, 30000);
  }

  function unconfirmedTimeframes() {
    const blocking = asArray(state.overview?.latest?.blocking_review_timeframes);
    return TF_ORDER.filter((tf) => blocking.includes(tf) && layerBundle(tf).source);
  }

  function renderReviewProgress() {
    const root = clear($('reviewProgress'));
    TF_ORDER.forEach((tf) => {
      const { health } = layerBundle(tf);
      const item = create('span', `review-progress-step ${tf === state.timeframe ? 'current' : health?.confirmed ? 'done' : health?.synced ? 'available' : 'missing'}`);
      item.textContent = tf;
      root.append(item);
    });
  }

  function startGuidedReview() {
    const queue = unconfirmedTimeframes();
    const tf = queue[0] || TF_ORDER.find((candidate) => layerBundle(candidate).source) || '1D';
    state.guidedReview = queue.length > 0;
    state.timeframe = tf;
    renderLayers();
    renderMap();
    const bundle = layerBundle(tf);
    openReview(bundle.draft ? 'draft' : 'layer');
  }

  function reviewValidationErrors(payload) {
    const errors = [];
    if (!payload.trend || payload.trend === 'unknown') errors.push('Kies de trend voor deze laag.');
    if (!payload.zones.length) errors.push('Minimaal één TradingView-zone is vereist.');
    payload.zones.forEach((zone, index) => {
      if (zone.role === 'unknown') errors.push(`Zone ${index + 1}: kies steun of weerstand.`);
      if (!(Number(zone.top) > 0 && Number(zone.bottom) > 0)) errors.push(`Zone ${index + 1}: vul geldige boven- en ondergrens in.`);
      if (!zone.reviewed) errors.push(`Zone ${index + 1}: bevestig prijs, rol en functie.`);
      if (!zone.reason) errors.push(`Zone ${index + 1}: noteer waarom de zone bestaat.`);
    });
    if (payload.source_timeframe === '15M' && payload.setup.detected && !payload.setup.reviewed) errors.push('Bevestig de 15m-opbouw.');
    if (payload.source_timeframe === '3M' && payload.trigger.detected && !payload.trigger.reviewed) errors.push('Bevestig het 3m-signaal.');
    if (payload.source_timeframe === '3M' && payload.trigger.ticket_requested) {
      if (!payload.trigger.entry_zone_id) errors.push('Kies de concrete instapzone voor dit ticket.');
      if (!(Number(payload.trigger.stop_loss) > 0)) errors.push('Vul één technische stop in voor dit concrete ticket.');
      if (payload.trigger.direction === 'long' && Number(payload.trigger.stop_loss) >= Number(payload.trigger.price)) errors.push('Bij een long moet de technische stop onder de signaalprijs liggen.');
      if (payload.trigger.direction === 'short' && Number(payload.trigger.stop_loss) <= Number(payload.trigger.price)) errors.push('Bij een short moet de technische stop boven de signaalprijs liggen.');
    }
    return [...new Set(errors)];
  }

  function openReview(mode) {
    const tf = state.timeframe;
    const bundle = layerBundle(tf);
    const source = mode === 'draft' ? bundle.draft : bundle.confirmed;
    if (!source) return;
    state.reviewMode = mode; state.reviewSource = clone(source);
    renderReviewProgress();
    $('reviewTitle').textContent = `${state.asset}USDT · ${tf} controleren`;
    $('reviewSubtitle').textContent = mode === 'draft' ? 'De waarden zijn automatisch ingevuld. Controleer alleen wat gemarkeerd is.' : 'Bewerk de gecontroleerde laag zonder andere tijdframes te overschrijven.';
    $('reviewAsset').value = state.asset; $('reviewTimeframe').value = tf;
    $('reviewTrend').value = source.trend || 'unknown'; $('reviewApproach').value = source.approach_direction || 'unknown'; $('reviewTradeType').value = source.trade_type || 'day';
    $('reviewRangeLow').value = source.range_low ?? ''; $('reviewRangeHigh').value = source.range_high ?? ''; $('reviewContextNote').value = source.context_note || '';
    fillSetupReview(tf, source.setup || {}); fillZoneEditor(asArray(source.zones)); fillTriggerReview(tf, source.trigger || {});
    clear($('reviewWarnings')); asArray(source.warnings).forEach((warning) => $('reviewWarnings').append(create('div', 'warning-item', translateWarning(warning))));
    const queue = unconfirmedTimeframes();
    $('confirmReview').textContent = state.guidedReview && queue.some((candidate) => candidate !== tf) ? 'Opslaan en volgende laag' : 'Controle opslaan';
    renderReviewPreview(tf); $('reviewError').classList.add('hidden'); $('reviewDialog').showModal();
  }

  function fillSetupReview(tf, setup) {
    $('setupReview').classList.toggle('hidden', tf !== '15M');
    $('setupType').value = setup.type || 'none'; $('setupDirection').value = setup.direction || 'unknown'; $('setupEvidence').value = setup.evidence || ''; $('setupConfirmed').checked = Boolean(setup.confirmed && setup.reviewed);
  }
  function populateTicketZoneOptions(selected = '') {
    const select = $('ticketEntryZone');
    if (!select) return;
    clear(select); select.append(new Option('Kies een zone', ''));
    $$('.zone-editor-row', $('zoneEditor')).forEach((row, index) => {
      const role = row.querySelector('[data-field="role"]')?.value || 'unknown';
      const top = row.querySelector('[data-field="top"]')?.value || '';
      const bottom = row.querySelector('[data-field="bottom"]')?.value || '';
      const label = `Zone ${index + 1} · ${role === 'support' ? 'Steun' : role === 'resistance' ? 'Weerstand' : 'Onbekend'} · ${bottom}–${top}`;
      select.append(new Option(label, row.dataset.id));
    });
    select.value = selected || '';
  }
  function toggleTicketFields() {
    const requested = Boolean($('ticketRequested')?.checked);
    $('ticketFields')?.classList.toggle('hidden', !requested);
  }
  function fillTriggerReview(tf, trigger) {
    $('triggerReview').classList.toggle('hidden', tf !== '3M');
    $('triggerType').value = trigger.type || 'none'; $('triggerDirection').value = trigger.direction || 'unknown'; $('triggerLocalBefore').value = trigger.local_trend_before || 'unknown'; $('triggerPrice').value = trigger.price ?? ''; $('triggerEvidenceText').value = trigger.evidence || ''; $('triggerConfirmed').checked = Boolean(trigger.confirmed && trigger.reviewed);
    const root = clear($('triggerFlagEditor'));
    Object.entries(FLAG_LABELS).forEach(([key, label]) => { const field = create('label'); const input = create('input'); input.type = 'checkbox'; input.dataset.flag = key; input.checked = Boolean(trigger.evidence_flags?.[key]); field.append(input, create('span', '', label)); root.append(field); });
    if ($('ticketRequested')) $('ticketRequested').checked = Boolean(trigger.ticket_requested);
    populateTicketZoneOptions(trigger.entry_zone_id || '');
    if ($('ticketStop')) $('ticketStop').value = trigger.stop_loss ?? '';
    toggleTicketFields();
  }
  function fillZoneEditor(zones) {
    clear($('zoneEditor'));
    const fallback = [{ role: 'unknown', intent: 'structure', top: '', bottom: '', tests: 0, confirmations: 0, reason: '', reviewed: false, confidence: 0 }];
    (zones.length ? zones : fallback).forEach(addZoneRow);
  }
  function addZoneRow(zone = {}) {
    const fragment = $('zoneTemplate').content.cloneNode(true); const row = fragment.querySelector('.zone-editor-row');
    row.dataset.id = zone.id || crypto.randomUUID(); row.querySelector('.zone-confidence').textContent = `${Math.round(finite(zone.confidence) || 0)}%`;
    ['role', 'intent', 'top', 'bottom', 'tests', 'confirmations', 'reason'].forEach((field) => { const input = row.querySelector(`[data-field="${field}"]`); if (input) input.value = (field === 'intent' && zone[field] === 'entry') ? 'structure' : (zone[field] ?? (field === 'intent' ? 'structure' : '')); });
    row.querySelector('[data-field="reviewed"]').checked = Boolean(zone.reviewed);
    row.querySelector('.remove-zone').addEventListener('click', () => { row.remove(); renumberZones(); });
    $('zoneEditor').append(row); renumberZones(); populateTicketZoneOptions($('ticketEntryZone')?.value || '');
  }
  function renumberZones() { $$('.zone-editor-row', $('zoneEditor')).forEach((row, index) => { row.querySelector('.zone-index').textContent = `ZONE ${String(index + 1).padStart(2, '0')}`; }); }

  async function renderReviewPreview(tf) {
    const image = $('reviewPreview'); const empty = $('reviewPreviewEmpty');
    if (state.reviewPreviewUrl) { URL.revokeObjectURL(state.reviewPreviewUrl); state.reviewPreviewUrl = null; }
    if (DEMO) { image.src = demoChartData(tf); image.hidden = false; empty.hidden = true; return; }
    try { const blob = await api(`/api/v1/chart/preview/${encodeURIComponent(state.asset)}/${encodeURIComponent(tf)}`, { blob: true, timeout: 20000 }); state.reviewPreviewUrl = URL.createObjectURL(blob); image.src = state.reviewPreviewUrl; image.hidden = false; empty.hidden = true; }
    catch { image.hidden = true; empty.hidden = false; }
  }

  function collectReviewPayload() {
    const tf = state.timeframe; const source = state.reviewSource || {};
    const zones = $$('.zone-editor-row', $('zoneEditor')).map((row) => {
      const get = (field) => row.querySelector(`[data-field="${field}"]`);
      const previous = asArray(source.zones).find((zone) => zone.id === row.dataset.id) || {};
      return { id: row.dataset.id, role: get('role').value, intent: get('intent').value, top: finite(get('top').value), bottom: finite(get('bottom').value), invalidation: null, tests: Number(get('tests').value || 0), confirmations: Number(get('confirmations').value || 0), reason: get('reason').value.trim(), reviewed: get('reviewed').checked, confidence: Number(previous.confidence || 100), timeframe: tf, thesis_state: previous.thesis_state || 'active' };
    });
    const setup = { detected: tf === '15M' && $('setupType').value !== 'none', type: tf === '15M' ? $('setupType').value : 'none', direction: tf === '15M' ? $('setupDirection').value : 'unknown', evidence: tf === '15M' ? $('setupEvidence').value.trim() : '', confirmed: tf === '15M' && $('setupConfirmed').checked, reviewed: tf === '15M' && $('setupConfirmed').checked, confidence: source.setup?.confidence || 100 };
    const flags = {}; $$('[data-flag]', $('triggerFlagEditor')).forEach((box) => { flags[box.dataset.flag] = box.checked; });
    const ticketRequested = tf === '3M' && Boolean($('ticketRequested')?.checked);
    const trigger = { detected: tf === '3M' && $('triggerType').value !== 'none', type: tf === '3M' ? $('triggerType').value : 'none', direction: tf === '3M' ? $('triggerDirection').value : 'unknown', local_trend_before: tf === '3M' ? $('triggerLocalBefore').value : 'unknown', price: tf === '3M' ? finite($('triggerPrice').value) : null, evidence: tf === '3M' ? $('triggerEvidenceText').value.trim() : '', confirmed: tf === '3M' && $('triggerConfirmed').checked, reviewed: tf === '3M' && $('triggerConfirmed').checked, confidence: source.trigger?.confidence || 100, evidence_flags: flags, ticket_requested: ticketRequested, entry_zone_id: ticketRequested ? ($('ticketEntryZone')?.value || null) : null, stop_loss: ticketRequested ? finite($('ticketStop')?.value) : null };
    if (ticketRequested && trigger.entry_zone_id) {
      const selected = zones.find((zone) => zone.id === trigger.entry_zone_id);
      if (selected) { selected.intent = 'entry'; selected.invalidation = trigger.stop_loss; }
    }
    const rangeLow = finite($('reviewRangeLow').value); const rangeHigh = finite($('reviewRangeHigh').value);
    return { asset: state.asset, symbol: `${state.asset}USDT`, source_timeframe: tf, chart_timeframe: tf, source_sync_id: state.reviewMode === 'draft' ? (source.revision || source.sync_id) : undefined, trend: $('reviewTrend').value, approach_direction: $('reviewApproach').value, trade_type: $('reviewTradeType').value, range_low: rangeLow, range_high: rangeHigh, range_source: rangeLow !== null && rangeHigh !== null ? 'user-confirmed' : 'missing', range_confidence: 100, overall_confidence: 100, context_note: $('reviewContextNote').value.trim(), setup, trigger, zones, reviewed: true, confirmed: true, warnings: source.warnings || [] };
  }


  function showReviewCompletionSummary() {
    const summary = $('reviewCompleteSummary');
    if (!summary) return;
    const rows = TF_ORDER.map((tf) => {
      const { source, health } = layerBundle(tf);
      return { tf, trend: translateTrend(source?.trend), zones: asArray(source?.zones).length, confirmed: Boolean(health?.confirmed) };
    });
    const totalZones = rows.reduce((sum, row) => sum + row.zones, 0);
    $('reviewCompleteTitle').textContent = 'Je marktkaart is compleet';
    $('reviewCompleteLead').textContent = `Dit zie ik: ${totalZones} zones over 4 charts. Controleer de samenvatting nog één keer; dit maakt niet automatisch een trade.`;
    const list = clear($('reviewCompleteLayers'));
    rows.forEach((row) => {
      const item = create('div', `review-summary-row ${row.confirmed ? 'done' : 'pending'}`);
      item.append(create('strong','',row.tf), create('span','',`${row.trend} · ${row.zones} zone${row.zones === 1 ? '' : 's'}`), create('em','',row.confirmed ? 'Gecontroleerd' : 'Open'));
      list.append(item);
    });
    if (typeof summary.showModal === 'function') summary.showModal(); else summary.setAttribute('open','');
  }

  async function submitReview(event) {
    event.preventDefault();
    $('reviewError').classList.add('hidden');
    const payload = collectReviewPayload();
    const validationErrors = reviewValidationErrors(payload);
    if (validationErrors.length) {
      $('reviewError').textContent = validationErrors.slice(0, 5).join(' ');
      $('reviewError').classList.remove('hidden');
      return;
    }
    $('confirmReview').disabled = true;
    const reviewedTf = state.timeframe;
    try {
      if (!DEMO) {
        const endpoint = state.reviewMode === 'draft' ? '/api/v1/chart/confirm' : '/api/v1/layer';
        await api(endpoint, { method: 'POST', body: payload, timeout: 45000 });
      } else {
        const healthRow = asArray(state.overview?.stack_health?.layers).find((row) => row.timeframe === reviewedTf);
        if (healthRow) { healthRow.confirmed = true; healthRow.review_needed = false; healthRow.state = 'VERIFIED'; }
      }
      $('reviewDialog').close();
      await loadOverview();
      if (state.guidedReview) {
        const next = unconfirmedTimeframes()[0];
        if (next) {
          state.timeframe = next;
          renderLayers(); renderMap();
          const bundle = layerBundle(next);
          openReview(bundle.draft ? 'draft' : 'layer');
        } else {
          state.guidedReview = false;
          showReviewCompletionSummary();
        }
      }
    } catch (error) {
      $('reviewError').textContent = error.message;
      $('reviewError').classList.remove('hidden');
    } finally { $('confirmReview').disabled = false; }
  }

  function dayStartAvailability() {
    const health = state.overview?.stack_health || {};
    const rows = asArray(health.layers);
    const stale = rows.some((row) => row?.present && (row?.fresh === false || row?.review_fresh === false || row?.confirmed === false));
    if (!health.capture_complete) return { ready:false, action:'charts', label:state.language === 'en' ? 'Read charts first' : 'Eerst charts lezen' };
    if (stale || health.fresh === false) return { ready:false, action:'charts', label:state.language === 'en' ? 'Refresh charts first' : 'Eerst charts vernieuwen' };
    return { ready:true, action:'briefing', label:state.language === 'en' ? 'Walk me through the day' : 'Neem de dag met me door' };
  }

  function renderDayStart() {
    const button = $('dayStartButton');
    if (!button || !state.overview) return;
    const availability = dayStartAvailability();
    button.textContent = availability.label;
    button.dataset.action = availability.action;
    button.className = `button ${availability.ready ? 'primary' : 'quiet'}`;
    const response = state.dayStart;
    const result = $('dayStartResult');
    const empty = $('dayStartEmpty');
    if (!response) {
      result.classList.add('hidden');
      empty.classList.remove('hidden');
      $('dayStartCard').classList.remove('blocked');
      return;
    }
    const briefing = response.briefings?.[state.language] || response.briefings?.nl;
    if (!briefing) return;
    empty.classList.add('hidden');
    result.classList.remove('hidden');
    $('dayStartResultTitle').textContent = briefing.title || '';
    $('dayStartSubtitle').textContent = briefing.subtitle || briefing.reason || '';
    $('dayStartBadge').textContent = briefing.blocked ? (state.language === 'en' ? 'REFRESH FIRST' : 'EERST VERNIEUWEN') : (state.language === 'en' ? 'SCENARIOS' : "SCENARIO'S");
    $('dayStartBadge').className = `badge ${briefing.blocked ? 'wait' : 'good'}`;
    $('dayStartCard').classList.toggle('blocked', Boolean(briefing.blocked));
    $('dayStartFollowupForm').classList.toggle('hidden', Boolean(briefing.blocked));
    const root = clear($('dayStartSections'));
    if (briefing.blocked) {
      const card = create('article', 'day-start-section-card no-trade prominent');
      card.append(create('h4', '', briefing.title), create('p', '', briefing.reason));
      root.append(card);
      return;
    }
    asArray(briefing.sections).forEach((section) => {
      const card = create('article', `day-start-section-card ${section.key || ''}${section.prominent ? ' prominent' : ''}`);
      card.append(create('h4', '', section.title || ''));
      if (section.body) card.append(create('p', '', section.body));
      if (asArray(section.lines).length) {
        const list = create('ul', 'day-start-lines');
        section.lines.forEach((line) => list.append(create('li', '', line)));
        card.append(list);
      }
      if (section.key === 'scenarios') {
        const list = create('ol', 'scenario-list');
        asArray(section.items).forEach((item) => {
          const row = create('li', 'scenario-item');
          row.append(create('strong', '', `${item.if} → ${item.then}`), create('small', '', item.invalidated));
          list.append(row);
        });
        if (!section.items?.length) list.append(create('li', 'scenario-item', state.language === 'en' ? 'No safe scenario can be formed from the current map.' : 'Uit de huidige kaart kan geen veilig scenario worden gevormd.'));
        card.append(list);
      } else if (asArray(section.items).length) {
        const list = create('ol', 'day-start-list');
        section.items.forEach((item) => list.append(create('li', '', typeof item === 'string' ? item : String(item))));
        card.append(list);
      }
      root.append(card);
    });
  }

  function demoDayStartResponse() {
    return {
      ok:true, blocked:false,
      briefings:{
        nl:{title:'Jouw dagstart-briefing',subtitle:"Scenario's, nooit voorspellingen. Geen trade is een volwaardige uitkomst.",blocked:false,sections:[
          {key:'position_management',title:'Eerst je lopende positie',body:'Laat de technische stop staan. TP1 verandert niets; pas na TP2, en alleen zolang het restant in winst staat, mag je de stop handmatig in profit zetten.'},
          {key:'where_we_are',title:'Waar staan we',lines:['1D is dalend, 4H is zijwaarts en 15M/3M zijn dalend / stijgend.','Prijs staat rond 50,0% van de 4H-range: midrange, dus niets doen is de standaard.']},
          {key:'scenarios',title:"Scenario's",items:[{if:'ALS prijs een bevestigde 4H-steunzone bereikt en het momentum stokt',then:'DAN beoordeel je via A-B-C of er een longidee ontstaat; dit is nog steeds geen trade',invalidated:'Dit scenario vervalt wanneer de zone op een volledige candle-close niet meer houdt.'}]},
          {key:'no_trade',title:'Het geen-trade-scenario',body:'Grote kans dat vandaag een kijkdag is omdat prijs midden in de 4H-range staat. Dat is proceswinst, geen verlies.',prominent:true},
          {key:'process_focus',title:'Jouw procesfocus vandaag',body:'Eerst locatie, dan momentum eruit, daarna confirmatie op candle-close.'},
          {key:'checklist',title:'De drie dagstart-toetsvragen',items:['Ligt dit aan het begin van de beweging?','Ben ik laat in de beweging?','Zit ik al bij het volgende HTF-level?']}
        ]},
        en:{title:'Your day-start briefing',subtitle:'Scenarios, never predictions. No trade is a valid outcome.',blocked:false,sections:[
          {key:'position_management',title:'Position management first',body:'Keep the technical stop in place. TP1 changes nothing; only after TP2 and while the remainder is profitable may you move it manually into profit.'},
          {key:'where_we_are',title:'Where we are',lines:['1D is falling, 4H is ranging, and 15M/3M are falling / rising.','Price is around 50.0% of the 4H range: midrange, so doing nothing is the default.']},
          {key:'scenarios',title:'Scenarios',items:[{if:'IF price reaches confirmed 4H support and momentum stalls',then:'THEN assess a long idea through A-B-C; this is still not a trade',invalidated:'This scenario expires if the zone no longer holds on a full candle close.'}]},
          {key:'no_trade',title:'The no-trade scenario',body:'There is a real chance today is a watching day because price is in the middle of the range. That is a process win, not a loss.',prominent:true},
          {key:'process_focus',title:'Your process focus today',body:'Location first, then loss of momentum, then candle-close confirmation.'},
          {key:'checklist',title:'Three day-start questions',items:['Is this at the start of the move?','Am I late in the move?','Am I already near the next HTF level?']}
        ]}
      }
    };
  }

  async function requestDayStart() {
    const availability = dayStartAvailability();
    if (!availability.ready) {
      const panel = $('chartWorkflowPanel');
      if (panel) { panel.open = true; updateCollapseText(panel); panel.scrollIntoView({ behavior:'smooth', block:'start' }); }
      return;
    }
    const button = $('dayStartButton');
    button.disabled = true;
    button.textContent = state.language === 'en' ? 'Building briefing…' : 'Briefing opbouwen…';
    try {
      const response = DEMO ? demoDayStartResponse() : await api('/api/v1/day-start', { method:'POST', body:{ asset:state.asset }, timeout:60000 });
      state.dayStart = response;
      if (!DEMO) await loadOverview({ silent:true });
      state.dayStart = response;
      state.dayStartStateId = state.overview?.state_id || state.overview?.latest?.state_id || null;
      renderDayStart();
      renderDiscipline();
      renderFocus();
      renderHeader();
    } catch (error) {
      state.dayStart = { briefings:{
        nl:{blocked:true,title:'Dagstart tijdelijk niet beschikbaar',reason:error.message,sections:[]},
        en:{blocked:true,title:'Day-start temporarily unavailable',reason:error.message,sections:[]}
      }};
      renderDayStart();
    } finally { button.disabled = false; }
  }

  async function askCoach(question, targetId = 'coachMessages', options = {}) {
    let text = String(question || '').trim(); if (!text) return;
    if (state.expertMode && !/^expert(?:modus| mode)/i.test(text)) text = state.language === 'en' ? `Expert mode. ${text}` : `Expertmodus. ${text}`;
    const target = $(targetId);
    const displayQuestion = String(options.displayQuestion || text).trim();
    target.append(create('p', '', `${state.language === 'en' ? 'You' : 'Jij'}: ${displayQuestion}`));
    const waiting = create('p', 'muted', state.language === 'en' ? 'Coach is analysing your charts and journal…' : 'Coach analyseert je charts en orderdagboek…'); target.append(waiting);
    try { const response = await api('/api/v1/coach', { method: 'POST', body: { question: text, asset: state.asset }, timeout: 60000 }); waiting.textContent = `Coach: ${response.answer}`; waiting.className = ''; }
    catch (error) { waiting.textContent = `Coachfout: ${error.message}`; waiting.className = 'notice danger'; }
  }

  function setupCollapsibles() {
    let saved = {};
    try { saved = JSON.parse(localStorage.getItem(COLLAPSE_KEY) || '{}'); } catch { saved = {}; }
    $$('[data-collapse-key]').forEach((details) => {
      const key = details.dataset.collapseKey; details.open = Boolean(saved[key]); updateCollapseText(details);
      details.addEventListener('toggle', () => { saved[key] = details.open; localStorage.setItem(COLLAPSE_KEY, JSON.stringify(saved)); updateCollapseText(details); });
    });
  }
  function updateCollapseText(details) { const node = details.querySelector('.collapse-text'); if (node) node.textContent = details.open ? 'Inklappen' : 'Openen'; }

  function bind() {
    $$('[data-language]').forEach((button) => button.addEventListener('click', () => setLanguage(button.dataset.language)));
    $('loginForm').addEventListener('submit', async (event) => { event.preventDefault(); try { await authenticate($('tokenInput').value); } catch (error) { showLogin(error.message); } });
    $('toggleToken').addEventListener('click', () => { const input = $('tokenInput'); input.type = input.type === 'password' ? 'text' : 'password'; $('toggleToken').textContent = input.type === 'password' ? 'Tonen' : 'Verbergen'; });
    $('logoutButton').addEventListener('click', () => { stopPolling(); sessionStorage.removeItem(TOKEN_KEY); state.token = ''; state.overview = null; showLogin('Token gewist.'); });
    $('feedbackButton').addEventListener('click', () => $('feedbackDialog').showModal());
    $('closeFeedback').addEventListener('click', () => $('feedbackDialog').close());
    $('cancelFeedback').addEventListener('click', () => $('feedbackDialog').close());
    $('feedbackForm').addEventListener('submit', submitFeedback);
    $('inviteForm').addEventListener('submit', createInvite);
    $('platinumQueueForm')?.addEventListener('submit', submitPlatinumLink);
    $('journalPatternSuggestions')?.addEventListener('click',(event)=>{const button=event.target.closest('[data-pattern-activate]');if(button)activateJournalPatternRule(button.dataset.patternActivate,button);});
    $('journalPatternRules')?.addEventListener('click',(event)=>{const button=event.target.closest('[data-pattern-deactivate]');if(button)deactivateJournalPatternRule(button.dataset.patternDeactivate,button);});
    $('addTestTradeButton').addEventListener('click', async () => { await api('/api/v2/journal/test-entry',{method:'POST',body:{pnl:125,direction:'long',entry:64000,exit:64200}}); await loadOverview(); });
    $('exportMyDataButton').addEventListener('click', async () => { const data=await api('/api/v2/beta/export'); downloadJson(`mytradingbot-${state.overview?.principal?.workspace_id||'beta'}-export.json`,data.export); });
    $('refreshButton').addEventListener('click', () => loadOverview().catch(() => {}));
    $('focusActionButton').addEventListener('click', handleFocusAction);
    $('dayStartButton').addEventListener('click', requestDayStart);
    $('noTradeDayButton')?.addEventListener('click', markNoTradeDay);
    $('commitmentForm')?.addEventListener('submit', activateCommitmentMode);
    $('dayStartFollowupForm').addEventListener('submit', (event) => { event.preventDefault(); const question=$('dayStartQuestion').value; $('dayStartQuestion').value=''; askCoach(question, 'dayStartMessages'); });
    $$('#appNav [data-view]').forEach((button) => button.addEventListener('click', () => switchView(button.dataset.view)));
    $('assetSelect').addEventListener('change', () => { state.asset = $('assetSelect').value; state.timeframe = '1D'; state.dayStart=null; state.dayStartStateId=null; loadOverview().catch(() => {}); });
    $$('#timeframeTabs button').forEach((button) => button.addEventListener('click', () => { state.timeframe = button.dataset.timeframe; renderLayers(); renderMap(); }));
    $('reviewDraftButton').addEventListener('click', () => { state.guidedReview = false; openReview('draft'); }); $('editLayerButton').addEventListener('click', () => { state.guidedReview = false; openReview('layer'); });
    $('startReviewButton').addEventListener('click', startGuidedReview);
    $('closeReview').addEventListener('click', () => { state.guidedReview = false; $('reviewDialog').close(); }); $('cancelReview').addEventListener('click', () => { state.guidedReview = false; $('reviewDialog').close(); }); $('addZoneButton').addEventListener('click', () => addZoneRow({ intent: 'structure' })); $('reviewForm').addEventListener('submit', submitReview); $('ticketRequested')?.addEventListener('change', toggleTicketFields);
    $('reviewCompleteClose')?.addEventListener('click', () => $('reviewCompleteSummary').close());
    $('reviewCompleteDone')?.addEventListener('click', () => $('reviewCompleteSummary').close());
    $('reviewCompleteMap')?.addEventListener('click', () => { $('reviewCompleteSummary').close(); const panel=$('chartWorkflowPanel'); if(panel){panel.open=true; updateCollapseText(panel);} const map=$('marketMapPanel'); if(map){map.open=true; updateCollapseText(map); map.scrollIntoView({behavior:'smooth',block:'start'});} });
    $('coachForm').addEventListener('submit', (event) => { event.preventDefault(); const question = $('coachQuestion').value; $('coachQuestion').value = ''; askCoach(question); });
    $('coachExpertMode').addEventListener('change', (event) => setCoachMode(event.target.checked));
    $('knowledgeFilter').addEventListener('change', renderKnowledge);
    $('closeTradeInspector').addEventListener('click',()=>$('tradeInspector').close());
    ['journalDirectionFilter','journalSymbolFilter','journalResultFilter','journalSourceFilter'].forEach((id) => $(id).addEventListener('change', () => { state.journalLimit = 12; renderJournalTable(); }));
    $('resetJournalFilters').addEventListener('click', () => { $('journalDirectionFilter').value = 'all'; $('journalSymbolFilter').value = 'all'; $('journalResultFilter').value = 'all'; $('journalSourceFilter').value = 'live'; state.journalLimit = 12; renderJournalTable(); });
    $('journalMoreButton').addEventListener('click', () => { state.journalLimit += 20; renderJournalTable(); });
    $('exportJournalButton').addEventListener('click', exportJournalCsv);
  }

  function demoChartData(tf) {
    const colors = { '1D': '#f3bd45', '4H': '#ff7866', '15M': '#7db7ff', '3M': '#45d49a' };
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="560"><rect width="100%" height="100%" fill="#080b0f"/><g stroke="#20262e">${[80,160,240,320,400,480].map(y=>`<line x1="0" y1="${y}" x2="1000" y2="${y}"/>`).join('')}</g><polyline fill="none" stroke="#d9dee5" stroke-width="3" points="20,420 100,390 180,440 260,340 340,360 420,260 500,300 580,210 660,230 740,150 820,180 900,110 980,140"/><rect x="40" y="365" width="920" height="42" fill="${colors[tf]}33" stroke="${colors[tf]}" stroke-width="2"/><text x="38" y="42" fill="#f4f6f8" font-family="sans-serif" font-size="22">BTCUSDT · ${tf}</text></svg>`;
    return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  }

  function demoLayer(tf, confirmed = true) {
    const zones = tf === '1D' ? [{ id:'d1',role:'resistance',top:68500,bottom:67200,reason:'Daily-bereik hoog',confidence:94,reviewed:true,intent:'structure'},{id:'d2',role:'support',top:63000,bottom:62100,reason:'Daily-steun',confidence:92,reviewed:true,intent:'structure'}]
      : tf === '4H' ? [{id:'h1',role:'resistance',top:65570,bottom:65480,reason:'4H weerstand',confidence:91,reviewed:true,intent:'structure',invalidation:65740},{id:'h2',role:'support',top:64820,bottom:64760,reason:'4H steun',confidence:90,reviewed:true,intent:'structure',invalidation:64620}]
      : tf === '15M' ? [{id:'m15',role:'support',top:64800,bottom:64770,reason:'15m lokale opbouw',confidence:88,reviewed:true,intent:'structure'}]
      : [{id:'m3',role:'support',top:64792,bottom:64778,reason:'3m instapzone',confidence:86,reviewed:true,intent:'entry',invalidation:64740}];
    return { asset:'BTC',symbol:'BTCUSDT',source_timeframe:tf,chart_timeframe:tf,trend:tf==='1D'?'down':tf==='4H'?'range':tf==='15M'?'down':'up',approach_direction:tf==='3M'?'down':'unknown',overall_confidence:90,range_low:62100,range_high:68500,zones,confirmed,reviewed:confirmed,at:new Date(Date.now()-TF_ORDER.indexOf(tf)*60000).toISOString(),revision:`demo-${tf}`,setup:tf==='15M'?{detected:true,type:'reversal',direction:'long',evidence:'Lokale dalende beweging richting de zone stabiliseert bij 4H-steun.',confirmed,reviewed:confirmed}:undefined,trigger:tf==='3M'?{detected:true,type:'local_reversal',direction:'long',local_trend_before:'down',price:64792,evidence:'De veroorzakende beweging is heroverd en de hertest houdt.',confirmed,reviewed:confirmed,evidence_flags:{zone_reaction:true,structure_break:true,retest:true,momentum_resume:true}}:undefined };
  }

  function demoOverview() {
    const layers = Object.fromEntries(TF_ORDER.map((tf) => [tf, demoLayer(tf, true)]));
    const healthRows = TF_ORDER.map((tf) => ({timeframe:tf,purpose:TF_LABELS[tf][0],present:true,synced:true,confirmed:true,review_needed:false,state:'VERIFIED',fresh:true,age_hours:.2,zones:layers[tf].zones.length,trend:layers[tf].trend}));
    const now = Date.now();
    const pnlRows = [120,-80,210,45,-55,160,95,-40,180,75,110,84];
    const trades = pnlRows.map((pnl,index)=>({id:`demo-${index}`,symbol:index%4===0?'ETHUSDT':'BTCUSDT',direction:index%3===0?'short':'long',entry:64000+index*120,exit:64000+index*120+(pnl>=0?180:-90),pnl,pnl_pct:pnl/20000*100,equity_snapshot:20000,closed_at:new Date(now-(pnlRows.length-index)*86400000).toISOString(),result:pnl>0?'win':'loss',process_grade:index%5===0?'B':'A',lesson:index%5===0?'Instap was te vroeg; wacht op de 3m-hertest.':'Goede uitvoering na bevestigde lokale kanteling.'}));
    const parentLinks = { '15M': [{ child_zone_id:'m15', child_timeframe:'15M', parent_zone_id:'h2', parent_timeframe:'4H', relation:'NESTED_SAME_ROLE', distance_pct:0.02 }], '3M': [{ child_zone_id:'m3', child_timeframe:'3M', parent_zone_id:'m15', parent_timeframe:'15M', relation:'NESTED_SAME_ROLE', distance_pct:0.01 }] };
    return {
      ok:true, version:VERSION, asset:'BTC', updated_at:new Date().toISOString(),
      principal:{id:'demo',workspace_id:'demo-paper',display_name:'Demo tester',role:'tester',mode:'tester',capabilities:['chart_sync','review','paper_journal','feedback']}, profile:{workspace_id:'demo-paper',display_name:'Demo tester',mode:'tester',manual_equity:10000},
      account:{equity:20110.76,equity_fresh:true,equity_age_seconds:40,positions:[{symbol:'BTCUSDT',side:'Buy',size:.147,entry:63955.4,mark:64210.8,stop_loss:63200,take_profit:66000,leverage:3,liq:55736.5,pnl:37.54}]},
      discipline:{release:'R25A-PROCESS-FIRST',score:86,score_band:'strong',rules:{count:10,followed:9,deviated:1,pct:90},grades:{count:10,score:84,trend:'improving',recent_score:90,previous_score:78,delta:12},routine:{observed_days:7,completed_days:6,pct:85.7},streak:{current:4,longest:7,today_complete:true,status:'earned_today',earned_by_day_start:true,earned_by_no_trade:false},today:{day_start_completed:true,no_trade_declared:false,no_trade_allowed:false,trade_activity_present:false,open_position:true},sample:{eligible_trades:12,rules_assessed:10,grades_assessed:10,routine_days_observed:7},read_only_to_trading_engine:true},
      account_guard:{release:'R25B-COMMITMENT-GUARDS',active:false,one_way:true,daily_loss_limit_pct:2,daily_loss_limit_usdt:402.22,buffer_remaining_usdt:402.22,buffer_remaining_pct:100,buffer_state:'healthy',positions_open:1,max_positions:1,cooldown_active:false,cooldown_seconds_remaining:0,ticket_blocked:false,gate_status:'COMMITMENT_OFF',next_reset_at:new Date(Date.now()+86400000).toISOString(),read_only_to_bybit:true},
      journal_pattern_gates:{release:'R25C-JOURNAL-PATTERN-GATES',open_suggestions:[],active_rules:[],inactive_rules:[],audit:[],minimum_repetitions:4,owner_action_required:true,read_only_to_bybit:true},
      stack_health:{asset:'BTC',complete:true,capture_complete:true,verified_complete:true,synced_count:4,confirmed_count:4,required_count:4,missing_timeframes:[],review_timeframes:[],layers:healthRows},
      market_stack:{assets:{BTC:{layers}},latest:{asset:'BTC',timeframe:'3M'}}, chart_drafts:{assets:{BTC:{layers}},latest:{asset:'BTC',timeframe:'3M'}},
      composite_map:{asset:'BTC',layers,parent_links:parentLinks},
      latest:{ok:true,version:VERSION,asset:'BTC',symbol:'BTCUSDT',price:64873,price_status:{ok:true,stale:false,price:64873,source:'Bybit mark price',age_seconds:12},execution_gate:{status:'ENTRY_READY',label:'INSTAP KLAAR',orderable:true,reason:'3m lokale kanteling bevestigd bij 4H-steun. Ticket mag veilig worden voorbereid; eindklik blijft handmatig.'},setup:{direction:'long',entry:64792,stop_loss:64740,take_profits:[65020,65570,67200],rr_max:46.3,risk_pct:1,trade_type:'day',parent_zone:layers['4H'].zones[1],setup_zone_15m:layers['15M'].zones[0],execution_zone:layers['3M'].zones[0]}},
      journal:{stats:{trades:12,profit_factor_display:'3,19',profit_factor:3.19,wins:9,losses:3,winrate:75,expectancy_pct:.377,expectancy_r:.61,total_pnl:904,total_pnl_pct:4.52,avg_win_pct:.6,avg_loss_pct:.292,avg_win:119.89,avg_loss:58.33,snapshot_coverage_pct:100,sample_label:'te kleine steekproef',max_drawdown_pct:1.8,max_drawdown:360,max_loss_streak:2,fees:34,funding:6,slippage:18,avg_mae_r:-.42,avg_mfe_r:1.74,per_richting:{long:760,short:144},per_symbool:{BTCUSDT:694,ETHUSDT:210}},trades,deepdives:[{title:'3m-hertest afgewacht',proces_grade:'A',oordeel:'Goede trade op basis van proces.',wat_ging_goed:'De lokale kanteling kwam binnen bevestigde 4H-steun.',les:'Blijf wachten op sweep, gain en hertest.'},{title:'Te vroege instap',proces_grade:'B',oordeel:'Winst, maar het proces was te vroeg.',wat_kan_beter:'Eerst de 3m-close en hertest afwachten.',les:'Een winst zonder bevestiging is geen A-proces.'}]},
      knowledge_source:{status:'UIT',processor_active:false,last_video_date:null,last_video_title:'',stored_videos:0,stored_lessons:0,processed:0,queue:0,queue_total:0,last_attempt_at:null,last_attempt_status:'disabled',extractor_version:'disabled',source_account:'externe kennisimport uit',warning:'Alleen inschakelen voor content waarvoor aantoonbare gebruiksrechten bestaan.'},
      methodology_sources:{rules:[{source_label:'OPERATORBELEID',title:'Risicoprofielen',statement:'Scalp 0,5%, dagtrade 1%, swingtrade 2% is een persoonlijke instelling.'},{source_label:'OPERATORBELEID',title:'Break-even',statement:'Stop pas na TP2 naar break-even en alleen wanneer de positie in winst staat.'},{source_label:'AUDIT-GEVERIFIEERD',title:'Kant-check',statement:'Een instap wordt geblokkeerd wanneer prijs de geldige orderzijde al voorbij is.'}]},
      knowledge_ingestion:[],
      knowledge:[],
      activity:[{type:'chart_confirmed',timeframe:'3M',note:'3m-laag gecontroleerd',at:new Date().toISOString()}]
    };
  }

  async function demoApi(path) {
    if (path.includes('/config')) return { ok:true,version:VERSION,chart_sync:true,diagnostics:{bybit_read_only:true,legacy_runtime:false,side_check:true,ticket_readback:true,break_even_policy:'na TP2 en in winst'} };
    if (path.includes('/overview')) return demoOverview();
    if (path.includes('/coach')) return { ok:true,answer:'De 3m draait lokaal bullish na een lokale dalende beweging richting de zone in bevestigde 4H-steun. Dat is de gewenste eerste trendkanteling, geen conflict tussen tijdframes.' };
    if (path.includes('/commitment/activate')) return { ok:true,account_guard:{...demoOverview().account_guard,active:true,daily_loss_limit_pct:2,buffer_remaining_usdt:402.22,buffer_remaining_pct:100,ticket_blocked:true,position_block:true,gate_status:'COMMITMENT_MAX_POSITION',reason:'Er staat al één positie open. Commitment Mode laat vandaag geen tweede positie toe.'} };
    return { ok:true };
  }

  // Demo-only test seam: exercises live gates, hidden dialogs and server text without exposing internals in production.
  if (DEMO) {
    window.__MYTRADINGBOT_TEST__ = {
      demoOverview,
      translateDutch,
      ui,
      applyLanguage,
      setLanguage,
      switchView,
      sourceLabel,
      consistencyLabel,
      consistencyReason,
      processLabel,
      percentageMetricsReason,
      sampleLabelForCount,
      executionReason,
      reviewReasonLabel,
      visionRole,
      visionReasonSummary,
      normaliseVisionWarning,
      zoneLinkageDetail,
      lessonExplainQuestion,
      setCoachMode,
      setOverview(overview) { state.overview = overview; renderAll(); applyLanguage(); },
      setDayStart(response) { state.dayStart = response; renderDayStart(); applyLanguage(); },
      requestDayStart,
      setGate(status, reason = '') {
        const overview = state.overview || demoOverview();
        overview.latest = overview.latest || {};
        overview.latest.execution_gate = { ...(overview.latest.execution_gate || {}), status, label: gateLabel(status), orderable: status === 'ENTRY_READY', reason };
        state.overview = overview;
        renderAll();
        applyLanguage();
      },
      setStaleState(timeframe = '3M', hours = 5.6) {
        const overview = state.overview || demoOverview();
        overview.account.positions = [];
        overview.stack_health.fresh = false;
        overview.stack_health.layers = asArray(overview.stack_health.layers).map((row) => row.timeframe === timeframe ? { ...row, synced:true, fresh:false, age_hours:hours } : { ...row, fresh:true });
        state.overview = overview;
        renderAll();
        applyLanguage();
      },
      setNoPositionState() {
        const overview = state.overview || demoOverview();
        overview.account.positions = [];
        overview.stack_health.fresh = true;
        overview.stack_health.layers = asArray(overview.stack_health.layers).map((row) => ({ ...row, synced:true, fresh:true }));
        overview.latest.execution_gate = { status:'NO_TRADE', reason:'Er is nu geen geldige setup. Dat is een normale en veilige uitkomst.', orderable:false };
        state.overview = overview;
        renderAll();
        applyLanguage();
      },
      openReview(timeframe = '1D') {
        state.timeframe = timeframe;
        renderLayers();
        renderMap();
        const bundle = layerBundle(timeframe);
        openReview(bundle.draft ? 'draft' : 'layer');
        applyLanguage();
      },
      showReviewCompletionSummary() { showReviewCompletionSummary(); applyLanguage(); },
      openFeedback() { $('feedbackDialog').showModal(); applyLanguage(); },
      openTradeInspector() {
        const trade = asArray(state.overview?.journal?.trades)[0];
        if (trade) openTradeInspector(trade);
        applyLanguage();
      },
      setServerError(message) {
        $('loginError').textContent = message;
        $('loginError').classList.remove('hidden');
        applyLanguage();
      },
    };
  }

  window.addEventListener('message', (event) => {
    if (event.source !== window || event.origin !== location.origin) return;
    const message = event.data || {};
    if (message.source !== 'mytradingbot-language-bridge' || message.action !== 'languageState') return;
    const next = message.language === 'en' ? 'en' : 'nl';
    if (next !== state.language) setLanguage(next, { persist:true, rerender:true, broadcast:false });
  });

  async function init() {
    try {
      state.activeView = localStorage.getItem(VIEW_KEY) || 'today';
      const requestedLanguage = PARAMS.get('lang');
      state.language = requestedLanguage === 'en' || requestedLanguage === 'nl' ? requestedLanguage : (localStorage.getItem(LANGUAGE_KEY) === 'en' ? 'en' : 'nl');
      state.expertMode = localStorage.getItem(COACH_MODE_KEY) === 'expert';
      if (requestedLanguage === 'en' || requestedLanguage === 'nl') localStorage.setItem(LANGUAGE_KEY, state.language);
    } catch { state.activeView = 'today'; state.language = 'nl'; state.expertMode = false; }
    bind(); setupCollapsibles(); switchView(state.activeView, { persist: false }); startLanguageObserver(); setLanguage(state.language, { persist: false, rerender: false });
    if (DEMO) $('demoBanner')?.classList.remove('hidden');
    if (DEMO) { await authenticate('demo-token-with-at-least-thirty-two-characters'); return; }
    const fragment = new URLSearchParams(location.hash.replace(/^#/,''));
    const handedOff = fragment.get('access') || '';
    if (handedOff) { history.replaceState(null, '', location.pathname + location.search); sessionStorage.setItem(TOKEN_KEY, handedOff); }
    const token = handedOff || sessionStorage.getItem(TOKEN_KEY) || '';
    $('tokenInput').value = token;
    if (token.length >= 32) { try { await authenticate(token); return; } catch (error) { showLogin(error.message); return; } }
    showLogin();
  }

  init().catch((error) => showLogin(error.message));
})();
