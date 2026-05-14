# Radio-Amater Station

Profesionální SDR rádio pro radioamatéry. Pythonová implementace SDR rádia inspirovaná SDRTrunk (Java). Podporuje RTL-SDR a Airspy (R2, Mini, HF+, Server).

## Funkce

- **SDR zařízení**: RTL-SDR (plná kontrola gain, bias-T, direct sampling), Airspy (nativní ctypes wrapper)
- **Demodulace**: NFM, FM, WFM, AM, USB, LSB s AGC a audio filtry
- **Digitální dekodéry**: DMR (sync detekce, color code), P25 (NAC, DUID), APRS
- **Tónové dekodéry**: CTCSS (38 tónů), DCS, DTMF
- **Trunk tracking**: P25 Phase 1, DMR/MotoTRBO
- **Spektrální analyzátor** s peak hold, waterfall, band plan overlay
- **Skener s automatickým band scanningem**: Prochází všechna amatérská pásma (160m–23cm) a automaticky se zastaví na aktivních frekvencích. Hold/hang time pro plynulé skenování.
- **Memory banky** pro organizaci kanálů
- **Import/Export** kanálů z/do CSV
- **Databáze českých radioamatérských retranslátorů** a simplex kmitočtů
- S-meter, nahrávání do WAV, detekce USB zařízení
- Profesionální tmavé GUI (PyQt6)

## Požadavky

- Python 3.10+
- PyQt6, numpy, scipy, sounddevice, pyrtlsdr, pyserial
- Pro Airspy: `libairspy0` (systémový balíček)

### Instalace systémových závislostí

```bash
# Pro RTL-SDR
sudo apt install librtlsdr0

# Pro Airspy
sudo apt install libairspy0

# Pro HackRF (volitelné)
sudo apt install libhackrf0
```

## Instalace

```bash
git clone https://github.com/davidprosek91-cze/Radio-Amater-station.git
cd Radio-Amater-station
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Spuštění

```bash
python main.py
```

Po spuštění:
1. Klikněte na **🔍** (Obnovit) pro nalezení SDR zařízení
2. Vyberte zařízení v combo boxu
3. Klikněte na **▶ START** pro spuštění příjmu
4. Pro automatické skenování všech amatérských pásem klikněte na **🔍 Scan**

## Ovládání

| Prvek | Popis |
|-------|-------|
| VFO | Přímý vstup frekvence, kolečko myši, tlačítka +/− |
| Pásma | Výběr z menu nebo combo boxu (automaticky nastaví modulaci) |
| Modulace | NFM (VHF/UHF), FM (broadcast), USB/LSB (HF), AM (letectví) |
| Squelch | Posuvník — noise-based signal detection |
| AGC | Automatické řízení zesílení |
| Noise Blanker | Potlačení impulsního šumu |
| Skener | Hold/Hang čas, práh signálu, automatický band scan |
| Dekodéry | Menu Nástroje → DMR/P25/APRS dekodér |
| Retranslátory | Menu s českými retranslátory |
| Banky | Organizace kanálů do paměťových bank |
| Nahrávání | Checkbox "Nahrávat" — ukládá do `recordings/*.wav` |
| Trunking | Záložka Trunking — přidání trunk systémů |

## Tipy pro radioamatéry

| Pásmo | Frekvence | Modulace | Krok |
|-------|-----------|----------|------|
| 160m | 1.8–2.0 MHz | LSB | 1 kHz |
| 80m | 3.5–4.0 MHz | LSB | 1 kHz |
| 40m | 7.0–7.3 MHz | LSB | 1 kHz |
| 20m | 14.0–14.35 MHz | USB | 1 kHz |
| 15m | 21.0–21.45 MHz | USB | 1 kHz |
| 10m | 28.0–29.7 MHz | USB | 1 kHz |
| 6m | 50–54 MHz | NFM | 5 kHz |
| 2m | 144–148 MHz | NFM | 12.5 kHz |
| 70cm | 420–450 MHz | NFM | 25 kHz |

### Rychlé tipy
- **2m pásmo (144–148 MHz)**: NFM, 12.5 kHz krok
- **70cm pásmo (420–450 MHz)**: NFM, 25 kHz krok
- **HF pásma (1.8–30 MHz)**: USB/LSB, 1 kHz krok
- **Retranslátory**: Menu → Retranslátory (CZ)
- **DMR**: Nastavte Color Code v editoru kanálu
- **P25**: Nastavte NAC v editoru kanálu
- **Skener**: Automaticky prochází všechna pásma a zastavuje se na aktivních frekvencích

## Technické detaily

- Audio sample rate: 48 kHz
- SDR sample rate: 2.4 MHz (RTL-SDR) / 10 MHz (Airspy)
- Airspy podpora: nativní ctypes wrapper nad `libairspy.so.0` (není potřeba pyairspy)
- Dekodéry DMR a P25 jsou v základní/simulované implementaci
