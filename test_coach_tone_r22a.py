from pathlib import Path

ROOT = Path(__file__).resolve().parent
text = (ROOT / 'coach_knowledge' / '00-COACH-INSTRUCTIE.md').read_text(encoding='utf-8')
low = text.lower()

required = [
    'alsof de trader 16 is',
    'gebruik korte zinnen',
    'één simpele analogie',
    'expertmodus',
    'answer fully in the language of the user' if False else 'antwoord volledig in de taal van de gebruiker',
    'scalp 0,5%',
    'daytrade 1%',
    'swingtrade 2%',
    'lager dan 3r is niet orderbaar',
    'range 40–60%',
    'menselijke eindklik',
]
for value in required:
    assert value in low, f'ontbrekende coachregel: {value}'

assert 'level-2-stop achter de invalidatie' in low
assert 'zet je stop niet op de meest voor de hand liggende plek' in low
assert 'english: clear everyday english' in low
assert 'noem geen actuele entry-, stoploss- of take-profitprijs' in low
print('PASS R22A: coach instruction defaults to clear 16-year-old language, supports expert mode, NL/EN, and preserves product guardrails')
