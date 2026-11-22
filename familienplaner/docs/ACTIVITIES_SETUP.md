# Freizeitaktivitäten: Quellen einrichten

Der Familienplaner sucht Veranstaltungen nicht „im ganzen Internet“, sondern in **Quellen, die du festlegst**.
So bleiben die Ergebnisse regional, zuverlässig und frei von Werbung. Alle 12 Stunden werden die Quellen
abgerufen (90 Tage voraus). Die Suche läuft danach lokal und schnell.

## 1. Wohnort festlegen

**Einstellungen → Wohnort & Freizeitaktivitäten**: Adresse oder Ort eingeben und **Ort suchen & speichern**.
Der Ort wird über OpenStreetMap in Koordinaten umgerechnet und dient als Mittelpunkt der Umkreissuche.

## 2. Quellen finden und hinzufügen

| Typ | Wofür | So findest du die Adresse |
|---|---|---|
| **iCal-Feed** | Veranstaltungskalender von Stadt/Gemeinde, Museen, Messegeländen, Hochschulen, Bibliotheken, Volkshochschulen, Vereinen | Auf der Veranstaltungsseite nach „iCal“, „ICS“, „Kalender abonnieren“, „In Outlook/Google übernehmen“ oder einem Kalendersymbol suchen. Die Adresse endet oft auf `.ics` oder beginnt mit `webcal://`. |
| **RSS-Feed** | Veranstaltungs-News von Museen, Kulturämtern, Zeitungen | Nach „RSS“ oder dem orangefarbenen Feed-Symbol suchen. Termine werden aus Titel/Text erkannt (z. B. „28.11.2026, 10 Uhr“). |
| **Ticketmaster** | Konzerte, Shows, Musicals, Familienveranstaltungen, Sport | Kostenlos registrieren auf <https://developer.ticketmaster.com>. Unter „My Apps“ steht der **Consumer Key**, das ist der API-Schlüssel. Sucht automatisch im Umkreis des Wohnorts. |
| **Webseite** | Seiten ohne Feed (z. B. Vereinsseite) | Für Fortgeschrittene: Mit den Entwicklerwerkzeugen des Browsers CSS-Selektoren für „ein Termin“, Titel und Datum ermitteln. Nutzungsbedingungen der Seite beachten. |

**Tipps für typische Wünsche:**

- **Tag der offenen Tür:** Schulen, Gymnasien und Hochschulen (Hochschulinformationstag), Feuerwehr, Kläranlage,
  Betriebe. Hochschulen und Städte bieten oft iCal-Kalender an.
- **Messen:** Die Veranstaltungskalender der Messegelände (Messe München, Messe Stuttgart …) gibt es meist als iCal.
- **Ausstellungen:** Museumsportale der Städte und Länder, Kunsthallen (häufig RSS).
- **Märkte und Feste:** Stadtmarketing bzw. Tourismusinformation der Stadt.

Mit **Testen** siehst du vor dem Speichern, wie viele Veranstaltungen gefunden werden, und einige Beispiele.

## 3. Suchen und eintragen

Unter **Aktivitäten** wählst du Umkreis, Zeitraum, Kategorien und optional einen Suchbegriff oder einen anderen Ort.
Ein Tipp auf eine Veranstaltung zeigt Details. **+ Kalender** trägt sie mit den gewählten Personen ein.

## Wie es funktioniert

- **Kategorien** werden aus Titel und Beschreibung erkannt (z. B. „Tag der offenen Tür“, „Ausbildungsmesse“,
  „Vernissage“, „Flohmarkt“). Pro Quelle kann eine Standardkategorie gesetzt werden (`category` in der
  config.yaml).
- **Orte** werden über OpenStreetMap/Nominatim ermittelt: höchstens eine Anfrage pro Sekunde, Ergebnisse
  werden dauerhaft gespeichert. Termine ohne Ortsangabe erscheinen nicht in der Umkreissuche. Für solche Quellen
  `lat`/`lon` als Standardort in der config.yaml hinterlegen.
- **Doppelte Einträge** (gleicher Titel, gleicher Tag, gleicher Ort) aus mehreren Quellen werden zusammengefasst.
- Vergangene Veranstaltungen werden automatisch entfernt. Bereits in den Kalender übernommene bleiben erhalten.

Ortsdaten © OpenStreetMap-Mitwirkende (ODbL).
