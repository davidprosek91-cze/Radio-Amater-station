SDRTrunk - Profesionální SDR rádio pro radioamatéry
===================================================

Pythonová implementace profesionálního SDR rádia inspirovaná SDRTrunk (Java).
Optimalizováno pro RTL-SDR, podporuje i Airspy.

FUNKCE
------
■ SDR zařízení: RTL-SDR (plná kontrola gain, bias-T, direct sampling), Airspy
■ Demodulace: NFM, FM, WFM, AM, USB, LSB s AGC a audio filtry
■ Digitální dekodéry: DMR (sync detekce, color code), P25 (NAC, DUID), APRS
■ Tónové dekodéry: CTCSS (38 tónů), DCS, DTMF
■ Trunk tracking: P25 Phase 1, DMR/MotoTRBO
■ Spektrální analyzátor s peak hold, waterfall, band plan overlay
■ Skener s prioritními kanály a spektrálním search módem
■ Memory banky pro organizaci kanálů
■ Import/Export kanálů z/do CSV
■ Databáze českých radioamatérských retranslátorů a simplex kmitočtů
■ S-meter, nahrávání do WAV, detekce USB zařízení
■ Profesionální tmavé GUI (PyQt6)

INSTALACE
---------
pip install -r requirements.txt

Pro RTL-SDR: pip install pyrtlsdr (nainstalováno)
Pro Airspy:   pip install pyairspy (volitelné)

SPUŠTĚNÍ
--------
python main.py

Po spuštění klikněte na "🔍" (Obnovit) pro nalezení SDR zařízení.
Pak "▶ START" pro začátek příjmu.

OVLÁDÁNÍ
--------
■ VFO: Přímý vstup frekvence, kolečko myši, tlačítka +/-
■ Pásma: Výběr z menu nebo combo boxu (automaticky nastaví modulaci)
■ Modulace: NFM (VHF/UHF), FM (broadcast), USB/LSB (HF), AM (letectví)
■ Squelch: Posuvník - noise-based nebo power-based
■ AGC: Automatické řízení zesílení
■ Noise Blanker: Potlačení impulsního šumu
■ Skener: Hold/Hang čas, práh signálu, priorita kanálů
■ Dekodéry: Menu Nástroje -> DMR/P25/APRS dekodér
■ Retranslátory: Menu se seznamem českých retranslátorů
■ Banky: Organizace kanálů do paměťových bank
■ Nahrávání: Checkbox "Nahrávat" - ukládá do recordings/*.wav
■ Trunking: Záložka Trunking - přidání trunk systémů

TIPY PRO RADIOAMATÉRY
---------------------
■ 2m pásmo (144-148 MHz): NFM, 12.5 kHz krok
■ 70cm pásmo (420-450 MHz): NFM, 25 kHz krok
■ HF pásma (1.8-30 MHz): USB/LSB, 1 kHz krok
■ Retranslátory: Menu -> Retranslátory (CZ)
■ DMR: Nastavte Color Code v editoru kanálu
■ P25: Nastavte NAC v editoru kanálu
