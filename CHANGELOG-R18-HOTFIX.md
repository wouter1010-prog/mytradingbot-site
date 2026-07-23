# UX 8.2.8 - lege tabbladen hotfix

## Oorzaak
De afsluitende `</section>` van `#dayStartSection` ontbrak. Daardoor parseerde de browser `Dagboek`, `Leren` en `Beheer` als kinderen van de Vandaag-sectie. `switchView()` zette de gekozen sectie zelf correct zichtbaar, maar de verborgen Vandaag-ouder hield de volledige inhoud onzichtbaar.

## Fix
- `#dayStartSection` wordt direct na de dagstartkaart afgesloten.
- Frontendversie en cache-busters zijn verhoogd naar UX 8.2.8.
- Nieuwe real-schema regressietest controleert zes journaalrecords, actieve kennisimport, ontbrekende optionele velden en lege beheerhistorie.
- De test controleert zichtbaarheid door de volledige voorouderketen en verbiedt view-secties binnen een andere view.

## Onaangetast
Handelsmotor, poorten, watcher, journaalwriter, dagstart-backend, kennisimport, queue en coachretrieval zijn byte-identiek aan de goedgekeurde R18-release.
