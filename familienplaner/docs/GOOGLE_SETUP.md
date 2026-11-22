# Google-Kalender verbinden

Der Familienplaner greift mit einem **eigenen Google-Zugang** (OAuth-Client) auf deine Kalender zu.
Die Daten gehen direkt vom Raspberry Pi zu Google, es gibt keinen Zwischenserver.
Die Einrichtung ist einmalig und dauert etwa 10 Minuten.

## 1. Google-Cloud-Projekt anlegen

1. <https://console.cloud.google.com/> öffnen und mit deinem Google-Konto anmelden.
2. Oben links **Projekt auswählen → Neues Projekt**, Name z. B. `Familienplaner`.
3. **APIs & Dienste → Bibliothek** öffnen, nach **Google Calendar API** suchen und **Aktivieren** wählen.

## 2. Zustimmungsbildschirm (OAuth consent screen)

1. **APIs & Dienste → OAuth-Zustimmungsbildschirm** öffnen (in neueren Oberflächen „Google Auth Platform“).
2. Nutzertyp **Extern** wählen. App-Name `Familienplaner`, Support- und Kontakt-E-Mail ist deine Adresse.
3. Unter **Zielgruppe/Testnutzer** die Google-Konten eintragen, die verbunden werden sollen.
4. **Wichtig:** Anschließend **„App veröffentlichen“** (Status *In Produktion*) wählen.
   Im Status *Test* laufen die Anmeldungen nach **7 Tagen** ab und du müsstest dich jede Woche neu anmelden.
   Eine Überprüfung durch Google ist für den privaten Gebrauch nicht nötig. Bei der Anmeldung erscheint dann
   der Hinweis „Google hat diese App nicht überprüft“: **Erweitert → Weiter zu Familienplaner**.

## 3. OAuth-Client erstellen

1. **APIs & Dienste → Anmeldedaten → Anmeldedaten erstellen → OAuth-Client-ID**.
2. Anwendungstyp: **Desktop-App**, Name `Familienplaner Pi`.
3. **Client-ID** (endet auf `.apps.googleusercontent.com`) und **Client-Secret** notieren.

> Warum „Desktop-App“ und nicht „TV und Geräte mit begrenzter Eingabe“? Die Code-Anmeldung für TV-Geräte
> erlaubt keinen Kalenderzugriff. Der Desktop-Typ nutzt eine Weiterleitung an `127.0.0.1` (den Pi selbst).

## 4. Im Familienplaner eintragen

Am Handy oder Laptop `http://familienplaner.local:8000/#/settings` öffnen (oder direkt am Pi) und
ggf. mit der Admin-PIN entsperren:

1. **Verknüpfte Konten → Einrichten**: Client-ID und Client-Secret eintragen und speichern.
   (Alternativ in `/etc/familienplaner/config.yaml` unter `google:` eintragen.)
2. **+ Google-Konto verbinden**:
   - **Am Pi:** Die Google-Anmeldung öffnet sich im Kiosk-Browser. Nach der Zustimmung geht es automatisch zurück.
   - **Am Handy/Laptop:** Die Google-Anmeldung öffnet sich in einem neuen Tab. Nach der Zustimmung zeigt der
     Browser eine Fehlerseite („127.0.0.1 nicht erreichbar“). Das ist richtig so. Die **komplette Adresse**
     aus der Adresszeile kopieren, im Familienplaner einfügen und **Verbinden** wählen.
     Der Vorgang muss innerhalb von 15 Minuten abgeschlossen sein.
3. Die Kalender des Kontos erscheinen unter **Kalender**. Dort lassen sie sich ausblenden, einfärben und einer
   Person zuordnen („gehört zu“).

## Wie synchronisiert wird

- **Neue Termine:** Nach dem Verbinden wird der Hauptkalender des Google-Kontos automatisch **Standard**.
  Neu angelegte Termine (auch aus der Aktivitätensuche) erscheinen dadurch auf allen Geräten. Das gilt nur,
  solange vorher ein lokaler Kalender Standard war. Ändern lässt sich das unter **Einstellungen → Kalender → Als Standard**.
  Im Termin-Dialog kannst du den Kalender außerdem pro Termin wählen.
- Alle 5 Minuten (`sync.interval_minutes`) sowie 2 Sekunden nach jeder Änderung am Familienplaner.
- Änderungen gehen in beide Richtungen. Wurde ein Termin auf beiden Seiten geändert, gewinnt die jüngere Änderung.
- Die Zuordnung zu Familienmitgliedern wird unsichtbar im Google-Termin gespeichert (`extendedProperties`).
  In Google Kalender selbst ist sie nicht zu sehen.
- Schreibgeschützte Kalender (z. B. Feiertage, freigegebene Kalender ohne Schreibrecht) werden nur angezeigt.
- **Trennen** entfernt das Konto und die gespiegelten Termine nur vom Pi. In Google bleibt alles erhalten.

## Fehlerbehebung

| Meldung | Lösung |
|---|---|
| „Google-Anmeldung abgelaufen – bitte neu verbinden“ | App noch im Status *Test* (7-Tage-Grenze) oder Zugriff widerrufen. App veröffentlichen, dann **Neu verbinden**. |
| „Google hat kein Refresh-Token geliefert“ | Unter <https://myaccount.google.com/permissions> den Zugriff von „Familienplaner“ entfernen und neu verbinden. |
| „Anmeldevorgang unbekannt oder abgelaufen“ | Mehr als 15 Minuten vergangen oder Backend neu gestartet. Verbinden erneut starten. |
| `redirect_uri_mismatch` | Client-Typ ist nicht „Desktop-App“, oder `google.redirect_uri` in der Konfiguration ist falsch. |
