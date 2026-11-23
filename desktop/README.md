# NEXCAP Desktop · PetrDevelop

**Stav: první funkční prototyp přenosu titulků, nikoli hotový PS5 překladač.**

Samostatná aplikace pro Windows 10/11, bez BlueStacks. První krok používá pouze standardní knihovnu Pythonu a umí poslat testovací český titulek přes UDP na existující LG webOS přijímač.

## Spuštění
1. Nainstaluj Python 3.11+ pro Windows.
2. V PowerShellu v kořeni repozitáře spusť `py desktop/nexcap.py`.
3. Na LG otevři kompatibilní přijímač, zvol vstup HDMI a nech ho spuštěný.
4. Zadej IP LG a klikni **Odeslat testovací titulek na LG**.

Paket odpovídá protokolu `webos/service/protocol.js`: `PCT1<TAB>id<TAB>duration<TAB>text<TAB>hint`, UDP port 41989. Odeslání paketu samo o sobě **nepotvrzuje zobrazení**; vyžaduje test na TV.

## Plán implementace
- Windows-native PS5 Remote Play přes Chiaki/libchiaki (ne Android JNI).
- Příjem a dekódování videa, OCR titulků a překlad.
- Odesílání překladů na LG, potlačení duplicit a časování.
- Windows tray aplikace a instalátor .exe; bezpečné ukládání PSN údajů.
- Automatické testy, balení a přejímka s fyzickou PS5/LG.

**Bezpečnost:** PSN údaje se zatím nikam nezadávají ani neukládají. Nepřenášej tokeny ze staré aplikace do testovacího prototypu.

**Licence:** AGPL-3.0-or-later; tento fork vychází z původního projektu PlayCaption. Zachovat upstream oznámení o autorských právech a licence.
