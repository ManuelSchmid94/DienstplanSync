# Dienstplan Sync – Setup & Build

## Voraussetzungen

- macOS 12+ auf Apple Silicon (M1/M2)
- Python 3.11+ (arm64): `brew install python@3.11`
- Homebrew: https://brew.sh

---

## 1. Google Cloud Credentials einrichten

1. Google Cloud Console öffnen: https://console.cloud.google.com
2. Neues Projekt erstellen (z. B. „DienstplanSync")
3. **APIs & Dienste → APIs aktivieren:**
   - Google Calendar API
4. **APIs & Dienste → Anmeldedaten:**
   - „Anmeldedaten erstellen" → „OAuth-Client-ID"
   - Anwendungstyp: **Desktop-App**
   - Name: „DienstplanSync"
   - JSON herunterladen
5. Datei umbenennen zu `credentials.json` und ablegen unter:
   ```
   ~/Library/Application Support/DienstplanSync/credentials.json
   ```

---

## 2. Entwicklungsumgebung aufsetzen

```bash
cd DienstplanSync

# Virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Abhängigkeiten
pip install -r requirements.txt

# Playwright Chromium Browser
playwright install chromium

# App-Icon erstellen (einmalig, benötigt Pillow)
pip install Pillow
python create_icon.py
```

---

## 3. App starten (Entwicklung)

```bash
source .venv/bin/activate
python main.py
```

---

## 4. macOS App (.app + .dmg) bauen

```bash
./build_dmg.sh
```

Ausgabe:
```
dist/DienstplanSync.app
dist/DienstplanSync-1.0.0.dmg
```

Das DMG kann per USB-Stick oder E-Mail verteilt werden.

---

## 5. App verwenden

1. `DienstplanSync.app` starten
2. **OSK Zugangsdaten** eingeben → „Zugangsdaten speichern"
   - Das Passwort wird sicher im macOS Keychain gespeichert
3. **„Google verbinden"** klicken
   - Browser öffnet sich, Google-Konto autorisieren
   - Token wird lokal unter `~/Library/Application Support/DienstplanSync/token.json` gespeichert
4. Kalender aus Dropdown wählen
5. **„Jetzt synchronisieren"** klicken

Der Sync-Vorgang:
1. Öffnet OSK DPlan (headless Chrome)
2. Loggt ein und navigiert zum Stundennachweis
3. Wechselt zum kommenden Monat
4. Lädt die Druckansicht als PDF
5. Parst alle Schichten aus dem PDF
6. Legt die Schichten im Google Kalender an / aktualisiert sie

---

## 6. Datenablage

| Datei | Inhalt |
|-------|--------|
| `~/Library/Application Support/DienstplanSync/credentials.json` | Google OAuth Client-ID (manuell ablegen) |
| `~/Library/Application Support/DienstplanSync/token.json` | Google Access-Token (automatisch) |
| `~/Library/Application Support/DienstplanSync/settings.json` | Einstellungen (Benutzername, Kalender-ID) |
| `~/Library/Application Support/DienstplanSync/cache.pdf` | Letzter heruntergeladener Dienstplan |
| macOS Keychain | OSK-Passwort (sicher verschlüsselt) |

---

## 7. Hinweise zu OSK DPlan Selektoren

Die Web-Automatisierung verwendet mehrere Fallback-Selektoren für jedes Element,
da das OSK DPlan-System auf ASP.NET WebForms basiert und die genauen Element-IDs
variieren können. Sollte ein Schritt fehlschlagen, die Fehlermeldung im Log
prüfen – sie zeigt, welches Element nicht gefunden wurde.

Falls nötig, können die Selektoren in `core/osk_client.py` angepasst werden
(Zeilen mit `*_candidates = [...]`).

---

## 8. Auto-Sync

Die Checkbox „Auto-Sync täglich" startet den Sync automatisch beim App-Start.
Für einen echten täglichen Hintergrund-Sync kann ein macOS LaunchAgent
eingerichtet werden. Beispiel-Plist auf Anfrage.
