# Radio-Amater Station

Profesionální SDR rádio pro radioamatéry s podporou RTL-SDR a Airspy.
Implementováno v Pythonu s PyQt6 tmavým GUI. Inspirováno SDRTrunk (Java).

## Vlastnosti

### SDR zařízení
- **RTL-SDR** (R820T2, E4000) — plná kontrola gain, bias-T, direct sampling
- **Airspy** (R2, Mini, HF+, Server) — nativní ctypes wrapper nad `libairspy.so.0`
- Automatická detekce USB zařízení, demo režim bez HW

### Demodulace
- **NFM** — úzkopásmové FM (VHF/UHF pásma)
- **FM** — široké FM (rozhlas)
- **WFM** — velmi široké FM
- **AM** — amplitudová modulace (letectví)
- **USB/LSB** — horní/dolní postranní pásmo (HF)

### Profesionální ovládání
- **Dvojité VFO (A/B)** s prohozením
- **Rychlá tlačítka pásem** (160m–23cm) s automatickou modulací
- **Tlačítka módů** (NFM/FM/AM/USB/LSB/WFM)
- **Velký frekvenční displej** s laděním po krocích
- **Nezávislé ovládání LNA/Mixer/VGA gain** (Airspy)
- **3 paměťové sloty** (M1–M3, Shift+klik = uložení)
- **S-meter** s kalibrovanými S-jednotkami (S1–S9+60) + audio VU metr

### Skener
- **Automatický band scanning** — prochází všechna amatérská pásma
- **Signal hold** — zastaví se na aktivní frekvenci
- **Hang time** — po odeznění signálu vyčká a pokračuje
- Prioritní kanály, vyhledávání podle frekvence

### Digitální dekodéry
- DMR (sync detekce, color code)
- P25 Phase 1 (NAC, DUID)
- APRS
- CTCSS (38 tónů), DTMF

### Vizualizace
- Spektrální analyzátor s peak hold
- Waterfall s historií 512 řádků
- Band plan overlay pro všechna pásma
- S-meter s audio VU metrem

### Další funkce
- Nahrávání do WAV (automatický název s frekvencí a módem)
- Import/Export kanálů CSV
- Databáze českých retranslátorů a simplex kmitočtů
- Trunk tracking (P25 Phase 1, DMR/MotoTRBO)
- Memory banky pro organizaci kanálů

## Požadavky

- Python 3.10+
- PyQt6, numpy, scipy, sounddevice, pyrtlsdr, pyserial
- RTL-SDR: `librtlsdr0` (systémový)
- Airspy: `libairspy0` (systémový)

### Instalace

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

1. **Obnovit** — vyhledá SDR zařízení
2. Vyberte zařízení
3. **RX** — spuštění příjmu
4. **Scan** — automatické skenování všech amatérských pásem
5. Klikněte na pásmo (160m–23cm) pro rychlý skok

## Ovládání

| Prvek | Popis |
|-------|-------|
| VFO A/B | Přepínání mezi dvěma nezávislými VFO |
| ⇄ Prohodit | Prohození frekvencí VFO A a VFO B |
| Frekvenční displej | Velký 5-místný displej |
| Krok | 1 kHz–100 kHz |
| ◀ ▶ | Ladění nahoru/dolů |
| M1–M3 | Paměťové sloty (Shift+klik = uložení) |
| Pásma (160m–23cm) | Rychlý skok s automatickou modulací |
| Módy (NFM/FM/AM/USB/LSB/WFM) | Přepínání modulace |
| SQL | Squelch (0–100) |
| VOL | Hlasitost |
| LNA/Mixer/VGA | Nezávislé gainy (Airspy) |
| AGC | Automatické řízení zesílení |
| NB | Noise blanker |
| REC | Nahrávání do WAV |
| Scan | Automatické skenování pásem |

## Pásma a modulace

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
| 23cm | 1240–1300 MHz | NFM | 25 kHz |

## Technické detaily

- Audio sample rate: 48 kHz
- SDR sample rate: 2.4 MHz (RTL-SDR) / 10 MHz (Airspy)
- Airspy: nativní ctypes wrapper bez závislosti na `pyairspy`
- Dekodéry DMR a P25: simulační implementace
- Platforma: Linux (aarch64/amd64)

