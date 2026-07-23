# Changelog

## UX 8.2.7 / Coach R18 — Dagstart-coach

- Nieuwe tweetalige dagstartbriefing met vaste vijfdelige mentorstructuur.
- Lopende positie krijgt voorrang met de bindende TP1/TP2-managementregel.
- Ontbrekende, verlopen of niet-gecontroleerde chartlagen weigeren scenario's.
- Alleen ALS-DAN-scenario's met tekstuele invalidatie; geen concrete orderprijzen.
- Journalpatronen sturen de procesfocus, inclusief losing-streakprotocol.
- Bronstripping geldt voor alle coachantwoordpaden.
- Videotitels en URLs zijn uit de LLM-promptpayload verwijderd.
- Engelse stophunt-termen selecteren liquiditeitsdossier 10.
- Handelsmotor, Smart Review, watcher, journal en orderpoorten blijven ongewijzigd.

## 8.2.6 — Code-based i18n and shared language state

- Server-provided source, origin, direction-consistency, process and metric labels are rendered from stable codes instead of raw Dutch labels.
- Real engine statuses select client-side reason keys; raw `execution_gate.reason` text is not displayed directly in English mode.
- ENTRY_READY uses the production `setup.trigger` and `parent_zone` payload shape.
- Cockpit and extension language synchronise in both directions through extension storage.
- Real-payload tests cover journal codes, metric coverage, audit confidence and all decision-relevant engine statuses.
- Stored lesson, deepdive, video and user content deliberately stays in its source language.
- Trading engine remains byte-identical to v8.2.2.

## 8.2.5 — State-key i18n for live cockpit states

- Verouderde-kaart-, lege-positie-, prijsbron-, fout- en gate-toestanden worden op render-moment uit taalsleutels opgebouwd.
- Dynamische parameters zoals timeframe, leeftijd en aantallen gebruiken locale-correcte getalnotatie.
- De gemelde halfvertaalde stale-map en no-position scenario's zijn met echte gerenderde payloads afgedekt.
- Popup- en zijpaneelteksten kregen uitgebreidere statusdekking; opgeslagen broncontent bleef bewust onvertaald.
- De motor bleef byte-identiek aan v8.2.2 / schema 86.

## 8.2.4 — Brede NL/EN-dekking en Midnight Gold polish

- Cockpit, dagboek, leren, beheer, dialogs, popup en TradingView-paneel kregen een brede NL/EN-presentatielaag.
- Emoji-vlaggen zijn vervangen door consistente CSS-vlaggen, zodat Windows geen dubbele landcodes toont.
- De visuele shell volgt de midnight-navy/gold editorial richting van World Cup Bet Buddy, zonder de handelsworkflow in een marketingsite te veranderen.
- Focus-states, reduced-motion, mobiele rangschikking en premium kaart-/navigatiestijlen zijn doorgetrokken.
- Latere live-audits vonden nog samengestelde toestandsteksten en rauwe serverlabels; die zijn vervolgens structureel opgelost in 8.2.5 en 8.2.6.
- Geen wijziging aan watcher, Smart Review, journal, risico, orderticket of eindklik. De motor bleef v8.2.2 / schema 86.

## 8.2.2 — Zone drift cap

- Smart Review begrenst toegestane middenpuntdrift op `min(2 × zonebreedte, 1%)`.
- Overlappende brede zones kunnen de vaste 1%-cap niet omzeilen.
- Drift boven 1% maakt uitsluitend de betreffende chart opnieuw controleplichtig.
- Kleine vision-jitter blijft toegestaan wanneer die binnen de begrensde zonetolerantie valt.
- Twee regressietests dekken brede-zonedrift en de overlaproute.
- Testlog-provenance verwijst weer naar de juiste v8.2.2-werkmap.

## 8.2.1 — Smart Review fail-closed en veilige migratie

- Verdwenen, toegevoegde of materieel verschoven zones vereisen gerichte hercontrole.
- Reviewgeldigheid loopt vanaf de menselijke controle: 1D 96u, 4H 36u, 15M 12u en 3M 2u.
- Een verse equivalente capture verlengt de menselijke reviewtijd niet.
- Tijdelijke fallback voor de vorige Railway-secretnamen.
- Tijdelijke acceptatie van zowel de nieuwe als de vorige extensietokenheader.

## 8.2.0 — Premium NL/EN en gebundeld motoronderhoud

- Volledige zichtbare rebranding naar MyTradingBot.
- Nederlandse en Engelse interface in cockpit, popup en TradingView-paneel.
- Premium Focus Cockpit met positie-eerst ontwerp en taakgerichte uitklappers.
- Smart Review behoudt ongewijzigde chartcontroles en vraagt alleen gerichte hercontrole.
- Deelvullingen worden per poll/order gebundeld; maximaal één positiesnapshot per entrybatch.
- Dubbele sluitmeldingen verwijderd; closed-PnL is de gezaghebbende sluitbron.
- Journaalwrites blijven idempotent en deepdive/procesgrade koppelen aan dezelfde journaalrij.
- Handmatig geopende posities krijgen een herkenbaar bronlabel en maximaal één processpiegel.

## 8.1.1 — Focus Cockpit live-positiehotfix

- Productievelden `entry`, `mark` en `pnl` worden in cockpit, popup en zijpaneel correct gelezen.
- Demo- en testdata gebruiken hetzelfde schema als de productiepayload.
- Open positie toont instap, huidige prijs, open resultaat, stop, doel, grootte, leverage en liquidatie.
- Charts, marktkaart en techniek blijven tijdens een open positie standaard ingeklapt.
- Terminologie, foutmeldingen en wizard-eindsamenvatting zijn vereenvoudigd.

## 8.1.0 — Focus Cockpit presentatielaag

- Nieuwe navigatie: Vandaag, Dagboek, Leren en Beheer.
- Lopende positie en rekeninginformatie staan centraal.
- Marktkaart, chartcontrole, diagnostiek en beheer zijn uit de dagelijkse hoofdflow gehaald of ingeklapt.
- TradingView-paneel en popup zijn compacter gemaakt.
- De geverifieerde 8.0.4-motor bleef voor deze UX-release ongewijzigd.

## 8.0.4 — Acceptatie- en statefix

- Cockpit, popup en zijpaneel gebruiken één backend-overview-state.
- Koude/stale prijs-cache veroorzaakt geen valse eerste prijsfout meer.
- TradingView OHLC-prijslezing is robuuster en bewaart bronmetadata.
- Journaal toont bronbadges, werkende bronfilter en richtingwaarschuwingen.
- CSV bevat auditvelden en datakwaliteit wordt expliciet gerapporteerd.
- `Benadering` heet **Lokale beweging richting zone** met ondubbelzinnige opties.
- Uitnodigingen respecteren minuten, uren of dagen exact in UTC en kunnen worden ingetrokken.
- Multi-workspace testerisolatie, paper-mode, eenmalige invites, intrekbare sessies en gehashte credentials.
- Consent-first onboarding, zelfdiagnose en dubbele instrumentvalidatie voor `BYBIT:BTCUSDT.P`.
- Dashboardtoken via URL-fragment naar `sessionStorage`.
- 4/4 gelezen leidt naar begeleide controle, niet naar schijnbare ordergereedheid.
- Alle v7.0.1-veiligheidsfixes behouden.
