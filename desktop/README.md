# NEXCAP Desktop · PetrDevelop

NEXCAP Desktop je rozpracovaná aplikace pro Windows 10/11 x64. Přijímá video přes samostatný nativní proces postavený nad libchiaki, vybírá spodní část obrazu pro anglické OCR a posílá český překlad kompatibilnímu LG webOS přijímači na UDP portu 41989. Profil videa používá H.264, 720p při 30 fps. Audio větev je v Remote Play vypnutá. Obraz hry se dál sleduje na PS5 přes HDMI.

## Test přijímače

1. Na LG otevři stávající přijímač, vyber vstup HDMI a zadej v NEXCAP jeho IPv4 adresu.
2. Klikni na **Ověřit přijímač**. Odpověď potvrzuje síťovou dostupnost UDP služby.
3. Klikni na **Odeslat titulek**. Vykreslení víceřádkového textu ověř na HDMI obrazu televizoru. Pokud zároveň odesílá Android, jeho IP může po posledním paketu ještě pět sekund držet aktivní relaci.

## Remote Play a překlad

1. Nainstaluj FFmpeg a Tesseract s anglickým modelem `eng` a přidej jejich spustitelné soubory do Windows PATH. Instalátor obsahuje místní model EN → CS, který běží na CPU. Pole LibreTranslate může zůstat prázdné. Při vyplnění se použije kompatibilní server bez API klíče. U vzdáleného serveru použij HTTPS. Server pak dostává rozpoznaný anglický text.
2. Pro první párování použij IPv4 PS5, osmibajtové PSN Account ID v Base64 pro sekundární účet a osmimístný kód z nabídky Remote Play v PS5. Použij už uložené párování NEXCAP Desktop, pokud pro stejnou IP funguje. Klíče z BlueStacks se automaticky neimportují. Po úspěšném párování v NEXCAP Desktop zůstávají v NEXCAP jen klíče Remote Play zašifrované přes Windows DPAPI pro aktuální účet Windows. Kód ani identifikátor účtu se neukládají.
3. Klikni na **Ověřit PS5** pro samostatný test příjmu a dekódování videa. Poté vyber **Spustit překlad**. Při výpadku obrazu NEXCAP opakuje spojení s prodlevou 2 až 30 sekund. Během překladu aplikace kontroluje dostupnost LG a zobrazuje i poslední český titulek přímo v okně. Tlačítko **Do lišty** skryje okno. Překlad lze zastavit i z ikony v systémové liště.
4. Hraj pod hlavním účtem na PS5. Současné hraní, chování ovladačů s připojeným sekundárním účtem, průběžné OCR ve hře a HDMI překryv patří do hardwarové přejímky.

## Sestavení

Ve Windows spusť `bash desktop/native/build-msys2.sh` v prostředí MSYS2 MINGW64 s balíčky z desktopového workflow. Poté v PowerShellu spusť z adresáře `desktop`:

```powershell
python -m pip install -r requirements-build.txt
python prepare_model.py
python -m PyInstaller --noconfirm --windowed --name 'NEXCAP Desktop' --icon nexcap.ico --hidden-import pystray._win32 --add-data 'nexcap.ico:.' --add-data 'nexcap.png:.' --add-data 'translate-en-cs:translate-en-cs' --collect-all ctranslate2 --collect-data sacremoses --copy-metadata ctranslate2 --copy-metadata sacremoses --copy-metadata subword-nmt nexcap.py
Copy-Item -Recurse build-native/runtime 'dist/NEXCAP Desktop/_internal/native'
Copy-Item -Recurse build-native/notices 'dist/NEXCAP Desktop/Open-source notices'
Copy-Item ../LICENSE 'dist/NEXCAP Desktop/LICENSE-PlayCaption.txt'
Copy-Item README.md 'dist/NEXCAP Desktop/README.md'
& "${env:ProgramFiles(x86)}/Inno Setup 6/ISCC.exe" installer.iss
```

Instalátor je v `desktop/dist/NEXCAP-Desktop-PetrDevelop-Setup-x64.exe`.

## Ověření

- `node desktop/test_transport.cjs` ověřuje pomocí skutečných UDP socketů diagnostickou odpověď a doručení českého titulku do produkčního parseru a příjemce webOS. Nahrazené jsou rozhraní služby webOS a síťová identita TV.
- `python desktop/test_pipeline.py` ověřuje skutečný dekodér FFmpeg, anglické OCR přes Tesseract, formát požadavku a odpovědi LibreTranslate přes lokální testovací HTTP server a UDP výstup. Vstupem je syntetické H.264 video a server vrací pevný očekávaný překlad.
- Na fyzické PS5 a LG ověř párování sekundárního účtu, stabilní obraz bez přehrávání zvuku, obnovu po výpadku a projekci přes HDMI. Kvalita OCR závisí na umístění a stylu titulků ve hře.

## Android a závislosti

Android používá párování a relaci v `RemotePlay.kt` a `RemotePlayService.kt`, ML Kit v `Ctecka.kt` a `Prekladac.kt` a upravené knihovny Android NDK v `native/`. Desktop přímo kompiluje nativní libchiaki z pevně určeného commitu projektu chiaki-ng a používá jeho registrační a video callbacky. Část FFmpeg a Tesseract se instaluje samostatně. Android a LG mají vlastní existující úložiště a desktop je nepoužívá.

NEXCAP Desktop a PlayCaption používají AGPL-3.0-or-later. Instalátor přikládá licenci PlayCaption a upstream licence a odkaz na zdrojový commit chiaki-ng (AGPL-3.0 s výjimkou pro OpenSSL). Zachovány jsou zásluhy původních autorů Chiaki a přispěvatelů chiaki-ng, nanopb, GF-Complete, Jerasure a curl.

Instalátor obsahuje model Argos EN-CS 1.9.6 odvozený z OPUS-MT (CC BY 4.0). Původní atribuce a odkaz na zdroj jsou přibalené u modelu.

## Současný výstup na více obrazovek

V nabídce **Televize** můžeš nastavit jeden nebo oba výstupy:

- **Přímý příjem LG** přijímá PCT1. U více kompatibilních přijímačů odděl jejich IPv4 adresy čárkou. Seznam se načte při spuštění překladu.
- **Webový přijímač** zapni v NEXCAP a jeho adresu otevři na každé televizi, tabletu nebo HDMI zařízení s použitelným webovým prohlížečem. Všechna zařízení musí mít síťový přístup k PC. Stejná adresa funguje současně na více zařízeních. Pokud používáš jen web, pole LG může být prázdné. Pokud se stránka nenačte, zkontroluj IPv4 PC, izolaci klientů a povolení NEXCAP v bráně Windows pro soukromou síť. Adresa se vytvoří při každém zapnutí a titulky jsou dostupné každému, kdo ji zná a může se k PC připojit. Nepřesměrovávej port na internet.
- **Kopírovat pro OBS** připraví adresu průhledného zdroje pro OBS Browser Source. Do OBS přidej hru ze samostatného zdroje, například z capture karty. Běžný prohlížeč na TV zobrazuje svou vlastní stránku a souběžné zobrazení přes HDMI závisí na schopnostech konkrétního zařízení. Pro samostatný monitor můžeš otevřít lokální náhled a použít F11.

NEXCAP je nezávislý nástroj. Kompatibilita OCR s konkrétní hrou a skutečný HDMI překryv se ověřují na cílové sestavě. Při komerční distribuci dodrž licenci AGPL a podmínky distribuovaných závislostí a herních ochranných známek.

V **Přehledu** zvol oblast OCR před spuštěním překladu. **Dialogy** čtou dolní pruh, **Herní telefon** pravou část a **Cíle a nápověda** horní část obrazu. Volba **Celý obraz** je širší, může ale zachytit další prvky herního rozhraní. Současně se zpracovává jedna oblast. Předvolby jsou obecné a vyžadují ověření v konkrétní hře.
