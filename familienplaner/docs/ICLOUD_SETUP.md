# iCloud-Kalender verbinden

Der Familienplaner greift über **CalDAV** auf deine iCloud-Kalender zu. Dafür brauchst du ein
**app-spezifisches Passwort**, nicht dein normales Apple-ID-Passwort. Die Daten gehen direkt vom
Raspberry Pi zu Apple.

## 1. App-spezifisches Passwort erstellen

1. <https://account.apple.com> öffnen und mit deiner Apple-ID anmelden (Zwei-Faktor-Authentifizierung muss aktiv sein).
2. **Anmeldung und Sicherheit → App-spezifische Passwörter** wählen.
3. **+** wählen, Name `Familienplaner` eingeben, erstellen.
4. Das angezeigte Passwort (Format `abcd-efgh-ijkl-mnop`) notieren. Apple zeigt es nur einmal an.

## 2. Im Familienplaner eintragen

**Einstellungen → Verknüpfte Konten → + iCloud-Kalender verbinden** wählen und
Apple-ID (E-Mail-Adresse) sowie das app-spezifische Passwort eintragen.

Die Kalender erscheinen unter **Kalender**. Dort lassen sie sich ausblenden, einfärben und einer Person zuordnen.
Erinnerungslisten werden nicht übernommen. Mit dir geteilte Kalender ohne Schreibrecht werden nur angezeigt.

## Wie synchronisiert wird

- Alle 5 Minuten sowie 2 Sekunden nach jeder Änderung am Familienplaner, in beide Richtungen.
- Wurde ein Termin auf beiden Seiten geändert, gewinnt die jüngere Änderung.
- Serien und ihre geänderten Einzeltermine werden wie in Apple Kalender gemeinsam gespeichert.
- Die Zuordnung zu Familienmitgliedern steht unsichtbar im Termin (`X-FAMILIENPLANER-MEMBERS`).
- **Trennen** entfernt das Konto nur vom Pi. In iCloud bleibt alles erhalten.
  Das app-spezifische Passwort kannst du danach auf account.apple.com widerrufen.

## Andere CalDAV-Server

Unter **Anderer CalDAV-Server** lässt sich statt iCloud z. B. Nextcloud (`https://…/remote.php/dav`),
mailbox.org oder Radicale verbinden. Dort gilt das jeweilige Passwort bzw. App-Passwort des Dienstes.

## Fehlerbehebung

| Meldung | Lösung |
|---|---|
| „Bitte ein app-spezifisches Passwort … verwenden“ | Es wurde das normale Apple-ID-Passwort eingegeben. Siehe Schritt 1. |
| „Apple-ID oder app-spezifisches Passwort ungültig“ | Tippfehler, oder das Passwort wurde widerrufen bzw. das Apple-ID-Passwort geändert (dabei verfallen alle app-spezifischen Passwörter). Neues erstellen und **Neu verbinden**. |
| Kalender fehlt | In Apple Kalender prüfen, ob es ein iCloud-Kalender ist (nicht „Auf meinem iPhone“). Abonnierte Kalender (z. B. Feiertage-Abos) liegen nicht in iCloud-CalDAV. |
