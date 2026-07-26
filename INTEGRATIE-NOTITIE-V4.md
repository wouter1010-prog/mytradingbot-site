# Integratienotitie v4 — MyTradingBot Cursus (basis 19 lessen + Advanced 15 lessen)

Datum: 26 juli 2026 · Vervangt v3 volledig. Zelfde serveropzet als v3; alleen nieuwe
build + extra media + extra audio-namen. Bestaande rewrite-regel en /cursus-data blijven gelijk.

## 1. Wat is er nieuw t.o.v. v3

- **Basiscursus: 19 lessen** (was 16). Nieuw: les 17 (tradetypes), les 18 (TP-plannen)
  en les 19 "Wanneer je niet mag traden". Examen: 18 vragen, zakgrens 14.
- **Advanced-cursus: 15 lessen**, volledig gevuld (route `/cursus/advanced` en
  `/cursus/advanced/les/1` t/m `/les/15`). Les 15 = eindtoets "Twee weken livegang"
  met Advanced-certificaat.
- **Ontgrendeling** (client-side, localStorage): Advanced opent na 19 basislessen;
  elke Advanced-les opent na de vorige. Reviewmodus: `?review=1` achter een URL
  opent alles (alleen bekijken); reset-knop in de header wist voortgang.
- **EN**: basiscursus volledig tweetalig (goedgekeurde vertalingen les 17/18/19 zitten
  erin). Advanced toont in EN-stand voorlopig de NL-tekst met een nette melding —
  goedgekeurde EN-vertalingen volgen in een latere build.
- Mini-correctie les 8 Advanced (kop "De vierde weg: de flip") zit erin.

## 2. Zip-inhoud

```
cursus/            ← productie-build, base /cursus/ (index.html + assets/)
cursus/manus-storage/   ← 66 media-bestanden (41 webp, 6 mp4, 1 jpg, 18 hero-png's)
INTEGRATIE-NOTITIE-V4.md
audio-namen.txt    ← volledige audio-namenlijst (zie ook §4)
```

Deploy: inhoud van `cursus/` op dezelfde plek als v3 zetten (vervang alles).
De map `manus-storage/` bevat GEEN audio — die host jij, zie §4.

## 3. Routes (SPA — zelfde rewrite als v3: alles naar index.html)

| Route | Inhoud |
|---|---|
| `/cursus/` | Home (19 lessen + niveau-keuze) |
| `/cursus/les/0` … `/cursus/les/18` | Basislessen 1–19 (intern 0-gebaseerd) |
| `/cursus/examen` | Eind-examen (18 vragen) |
| `/cursus/certificaat` | Certificaat basiscursus |
| `/cursus/advanced` | Advanced-overzicht (15 lessen) |
| `/cursus/advanced/les/1` … `/les/15` | Advanced-lessen (1-gebaseerd) |

Beacon: ongewijzigd, POST `/cursus-data` (sendBeacon, faalt stil). Nieuwe
event-types: `adv-les-start`, `adv-les-afgerond`, `adv-certificaat` (payload-formaat gelijk).

## 4. Audio-namenlijst (32 bestaand + 32 nieuw = 64 mp3's, map `manus-storage/`)

- **Bestaand (v3, ongewijzigd):** `les00-nl.mp3` … `les15-nl.mp3` en `les00-en.mp3` … `les15-en.mp3`
- **Nieuw — basiscursus:** `les16-nl.mp3`, `les16-en.mp3`, `les17-nl.mp3`, `les17-en.mp3`,
  `les18-nl.mp3`, `les18-en.mp3` (les 17, 18 en 19 van de cursus; intern 0-gebaseerd)
- **Nieuw — Advanced:** `adv01-nl.mp3` … `adv15-nl.mp3` en `adv01-en.mp3` … `adv15-en.mp3`

Ontbreekt een mp3, dan toont de speler "Audio wordt toegevoegd" — niets breekt.
Zelfde cache-advies als v3: korte cache op mp3's (geen hash in de naam).

## 5. Test-checklist na deploy

1. `/cursus/` laadt, teller zegt 19 lessen / 7 delen.
2. Deep-link `/cursus/les/18` en `/cursus/advanced/les/15` laden direct (rewrite OK).
3. `/cursus/advanced` toont 15 kaarten, vergrendeld voor nieuwe bezoekers.
4. `?review=1` achter een URL opent alles; reset-knop in header wist voortgang.
5. Taal-toggle EN: basislessen volledig Engels; Advanced toont NL + melding.
6. Audio speelt op een les waarvan de mp3 al bestaat (bijv. `/cursus/les/3`).
7. Beacon: quiz-antwoord geven → POST op `/cursus-data` zichtbaar in de log.
