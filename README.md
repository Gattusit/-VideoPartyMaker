# Video Party Maker

MVP open source per creare video di eventi e feste.

## Funzioni

- GUI PySide6
- Drag & Drop di foto
- Ordinamento intelligente dei nomi numerati
- Durata standard delle foto
- Timeline MVP
- Importazione audio
- Registrazione voce
- Rendering MP4 con FFmpeg
- Profili 4K / 1080p / 720p / WhatsApp
- Salvataggio progetto JSON
- Build automatica Windows `.exe`

## Avvio

Installare Python 3.11+ e FFmpeg.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Poi:

```bash
python main.py
```

## Creare l'EXE

Su Windows:

```bash
build_windows.bat
```

Oppure GitHub Actions genera automaticamente l'EXE quando fai push del progetto su GitHub.

L'EXE viene creato nella cartella `dist/`.

## Licenza

MIT
