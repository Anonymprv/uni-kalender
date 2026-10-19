# Uni-Kalender (FSU Jena / Friedolin)

Dieser Kalender wird alle 2 Stunden automatisch aus den öffentlichen Friedolin-Daten neu gebaut:

- Zeiten, Räume und neue Einzeltermine kommen direkt aus Friedolin.
- Ausfallende Termine bleiben sichtbar und heißen **„❌ Fällt aus: …“**, mit Grund aus Friedolin.
- Jeder Termin hat einen Link zur Veranstaltungsseite in Friedolin.

## Abonnieren

Abo-Adresse:

```
https://raw.githubusercontent.com/Anonymprv/uni-kalender/main/kalender.ics
```

- **Mac:** Kalender-App → Ablage → Neues Kalenderabonnement → Adresse einfügen → Speicherort **iCloud**, automatisch aktualisieren: **alle 15 Minuten** oder **stündlich**.
- **iPhone:** Einstellungen → Apps → Kalender → Accounts → Account hinzufügen → Andere → Kalenderabo hinzufügen. Mit Speicherort iCloud auf dem Mac ist das nicht nötig.

## Kurse ändern

Neue Kurse kommen in `kurse.json`. Die `id` steht in der Friedolin-URL der Veranstaltung (`publishid=…`). `titel` ist optional, ohne Angabe wird der Friedolin-Titel verwendet. Nach dem Speichern baut sich der Kalender sofort neu.

## Manuell aktualisieren

Reiter **Actions** → „Kalender aktualisieren“ → **Run workflow**.
