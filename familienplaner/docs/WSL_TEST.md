# Familienplaner auf dem Windows-PC testen (WSL)

So probierst du den Familienplaner auf deinem PC aus, bevor er auf den Raspberry Pi kommt.
Der Planer läuft in WSL (Linux unter Windows), die Bedienung erfolgt im normalen Windows-Browser.

## 1. Voraussetzungen (einmalig)

**WSL mit Ubuntu** (falls noch nicht vorhanden): PowerShell **als Administrator** öffnen und
`wsl --install` ausführen, danach den PC neu starten. Beim ersten Start von „Ubuntu“ legst du Benutzername und Passwort an.

Alle folgenden Befehle laufen im **Ubuntu-Terminal**:

```bash
# Python, Git
sudo apt update && sudo apt install -y git python3 python3-venv

# Node.js 22 über nvm (die Ubuntu-Version ist zu alt)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
exec bash            # Terminal neu laden
nvm install 22
```

Unter Ubuntu 22.04 statt `python3 python3-venv` die Pakete `python3.11 python3.11-venv` installieren.
Die Versionen prüfst du mit `lsb_release -a`, `python3 -V` und `node -v`.

## 2. Projekt holen

**Wichtig:** Im Linux-Dateisystem klonen (`~`), nicht unter `/mnt/c/…`. Dort sind npm und Python sehr langsam.

```bash
cd ~
git clone https://github.com/VitusM123/VitusM123.git
cd VitusM123
git checkout claude/familienplaner-architecture-hyr1q4
cd familienplaner
```

Ist das Repository privat, fragt Git nach Zugangsdaten. Dann ein
[Personal Access Token](https://github.com/settings/tokens) als Passwort verwenden oder `gh auth login` nutzen.

## 3. Testen und starten

```bash
scripts/dev.sh --test      # automatische Tests (beim ersten Mal ca. 1–2 min wegen Installation)
scripts/dev.sh --demo      # Beispieldaten anlegen und starten
```

Dann im **Windows-Browser** öffnen:

| Adresse | Was |
|---|---|
| <http://localhost:8000> | normale Ansicht |
| <http://localhost:8000/?kiosk=1> | wie später am Pi: Bildschirmtastatur, nach 5 min zurück zu „Heute“ |
| <http://localhost:8000/docs> | API-Dokumentation |

Tipp: Mit **F11** auf Vollbild schalten. In den Entwicklertools des Browsers (F12 → Gerätesymbol) lässt sich
die Displaygröße einstellen, z. B. 1280 × 800 für ein 10"-Display.

Beenden mit **Strg+C**. Die Daten bleiben in `backend/data/` erhalten. Neu beginnen: `scripts/dev.sh --reset --demo`.

## 4. Was du ausprobieren kannst

- **Kalender:** Woche, Monat und Familie. Ins Raster tippen legt einen Termin an. Mit den Pfeilen blätterst du (am Touchscreen auch durch Wischen).
- **Serien:** Einen „Schwimmtraining“-Termin öffnen, die Uhrzeit ändern und „Nur diesen Termin“ wählen.
- **Aktivitäten:** „Nächste 30 Tage“, Kategorien filtern, „+ Kalender“.
- **Einstellungen:** Farbschema, Familienmitglieder, Wohnort. Unter **Admin-PIN** eine PIN festlegen und danach sperren.
- **Google:** Einrichtung nach [GOOGLE_SETUP.md](GOOGLE_SETUP.md). In WSL leitet Google direkt an
  `127.0.0.1:8000` zurück, die Anmeldung schließt sich also automatisch ab.
- **iCloud:** nach [ICLOUD_SETUP.md](ICLOUD_SETUP.md).
- **Echte Veranstaltungen:** Quelle unter Einstellungen → Veranstaltungsquellen anlegen ([ACTIVITIES_SETUP.md](ACTIVITIES_SETUP.md)).
  Die Beispiel-Veranstaltungen kannst du dort löschen.

## Vom Handy im WLAN zugreifen (optional)

WSL hängt standardmäßig hinter einem eigenen Netzwerk, das Handy erreicht es daher nicht direkt.
Am einfachsten ist der **gespiegelte Netzwerkmodus**: In Windows die Datei `%UserProfile%\.wslconfig` anlegen mit

```ini
[wsl2]
networkingMode=mirrored
```

Dann in PowerShell `wsl --shutdown` ausführen und Ubuntu neu öffnen. Das Handy erreicht den Planer anschließend unter
`http://<IP-des-PCs>:8000`. Die IP zeigt `ipconfig` in Windows. Die Windows-Firewall fragt beim ersten Zugriff nach.

## Probleme

| Meldung | Lösung |
|---|---|
| `Python 3.11 oder neuer fehlt` | Siehe Schritt 1 (Ubuntu 22.04: `python3.11`). |
| `venv konnte nicht angelegt werden` | `sudo apt install python3-venv` (bzw. `python3.11-venv`). |
| `Node.js fehlt` / `zu alt` | nvm wie in Schritt 1, dann `nvm install 22`. |
| `address already in use` | Läuft schon eine Instanz? Sonst anderen Port nutzen: `PORT=8080 scripts/dev.sh` |
| Seite lädt nicht im Browser | Läuft das Skript noch (Terminal offen)? Adresse `http://localhost:8000` statt `127.0.0.1` probieren. |
| Uhrzeit falsch | Der Planer rechnet in `Europe/Berlin`, der Browser in der Windows-Zeitzone. Beide sollten übereinstimmen. |
