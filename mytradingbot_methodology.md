# MyTradingBot operationeel handelsbeleid

Dit bestand bevat uitsluitend configureerbaar productbeleid. Het is geen beleggingsadvies en voorspelt de markt niet.

## Werkvolgorde

1. **1D — context:** grote trend, range en hoofdlocaties.
2. **4H — structuur:** relevante higher-timeframe zones en marktstructuur.
3. **15M — opbouw:** lokale benadering, reversal, breakout, continuation of range-rotatie.
4. **3M — uitvoering:** eerste lokale kanteling en concrete uitvoering.

Een tegengestelde 3M-beweging kan juist de eerste lokale reversal bij een geldige higher-timeframe locatie zijn. De 3M-richting hoeft dus niet vooraf gelijk te zijn aan de 1D/4H-trend.

## Slimme menselijke controle

- Een eenmaal gecontroleerde chart blijft goedgekeurd zolang de handelsbetekenis niet materieel verandert.
- Een nieuwe screenshot of revision-id alleen is nooit reden voor hercontrole.
- 1D of 4H wordt opnieuw gevraagd bij een materiële trend-, range- of zonewijziging.
- 15M wordt pas opnieuw gevraagd wanneer een concrete nieuwe setup verschijnt.
- 3M wordt pas opnieuw gevraagd wanneer een concreet lokaal signaal of ticketkandidaat verschijnt.
- Bij een lopende positie blokkeert chartcontrole nooit het volgen van balans, PnL, stop of doel.

## Risico en ticketbeleid

- Risicoprofielen: scalp 0,5%, day 1,0%, swing 2,0%.
- Een ticket met minder dan 3R tot het geldige einddoel is niet orderbaar.
- Positiegrootte wordt bepaald uit rekeningwaarde, risico en technische stop.
- Leverage verandert het vooraf gekozen risico niet.
- De gebruiker kiest één concrete instapzone en één technische stop pas tijdens ticketvoorbereiding.
- Drie doelen verdelen de positie in drie vrijwel gelijke delen.
- De stop blijft na TP1 staan; pas na TP2 en alleen wanneer de resterende positie in winst staat mag de stop naar break-even.
- De software bereidt voor en leest terug, maar voert nooit de definitieve orderklik uit.

## Databeleid

- Open orders, entry-, stop-, take-profit-, actuele-prijs- en signaallijnen zijn geen marktzone.
- Vision mag voorstellen doen, maar kan nooit zelfstandig een order vrijgeven.
- Ontbrekende of tegenstrijdige gegevens blokkeren fail-closed.
- Historische prestaties gebruiken uitsluitend reproduceerbare brondata; ontbrekende historische equity wordt niet met huidige equity ingevuld.

## Commercieel gebruik

Alle externe lessen, video's, merknamen en cursusinhoud staan standaard uit. Alleen content waarvoor de operator aantoonbaar rechten bezit mag worden toegevoegd.
## Kennisbank en bronhiërarchie

- **OPERATORBELEID** en **PRODUCTVEILIGHEID** zijn altijd leidend.
- Externe videolessen zijn uitsluitend educatieve context; ze kunnen nooit risico, minimale R:R, menselijke eindklik, fail-closed gedrag of andere productveiligheid overschrijven.
- De coach gebruikt alleen korte, gestructureerde parafrases. Herkomst blijft intern auditbaar, maar bronverwijzingen worden standaard niet in coachantwoorden getoond. Volledige transcripties worden niet via de coach- of kennis-API vrijgegeven.
- Een video kan nooit zelfstandig een actuele setup, entry, stop of target maken.
- Tegenstrijdige of onzekere videolessen worden als interpretatie of onbevestigd gemarkeerd.
- De Doopie Cash-bronnen in deze kennisbank staan standaard op privégebruik zonder bevestigde commerciële licentie. Voor verkoop of distributie is afzonderlijke schriftelijke toestemming nodig.

