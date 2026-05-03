# AI Dashboard Generator für Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue)](https://www.home-assistant.io/)

Ein vollautomatischer **KI-gestützter Dashboard-Generator** für Home Assistant. Analysiert alle deine Entities, gruppiert sie nach Räumen und erstellt ein modernes, ansprechendes Lovelace-Dashboard – auf Knopfdruck.

![Screenshot des AI Dashboard Generators](docs/screenshot.png)

---

## ✨ Features

- 🤖 **KI-Analyse** – Optionale Anbindung an OpenAI (GPT-4o), Anthropic (Claude 3.5) oder Google (Gemini 2.5 Flash) für smarte Benennungen und Beschreibungen
- 🧮 **Offline-Modus** – Komplett ohne API-Key, regelbasierter KI-Ersatz
- 🏠 **Raum-basiertes Design** – Automatische Gruppierung nach HA-Bereichen (Areas)
- 🖼️ **Raumbilder** – Eigene Fotos für jeden Raum hochladen
- 🎨 **Modernes Design** – Nutzt [Mushroom Cards](https://github.com/piitaya/lovelace-mushroom) für ein zeitgemäßes Aussehen
- 🔍 **Smarte Filterung** – Blendet technische/irrelevante Entities automatisch aus
- 🏷️ **Auto-Umbenennung** – Entfernt Raumpräfixe, verbessert Entity-Namen
- 🔄 **Refresh** – Ein Klick aktualisiert das Dashboard mit allen neuen Geräten
- 📱 **Mobil-optimiert** – Dashboard funktioniert auf allen Geräten
- 🌍 **Mehrsprachig** – Deutsch & Englisch

---

## 📦 Installation via HACS

### 1. Repository als benutzerdefiniertes Repository hinzufügen

1. Öffne **HACS** in Home Assistant
2. Klicke oben rechts auf die **drei Punkte** (⋮)
3. Wähle **"Benutzerdefinierte Repositories"**
4. Trage ein:
   - **Repository URL:** `https://github.com/YOUR_USERNAME/ai-dashboard-generator`
   - **Kategorie:** `Integration`
5. Klicke auf **Hinzufügen**

### 2. Integration installieren

1. Suche in HACS nach **"AI Dashboard Generator"**
2. Klicke auf **Herunterladen**
3. Starte Home Assistant **neu**

### 3. Integration einrichten

1. Gehe zu **Einstellungen → Geräte & Dienste**
2. Klicke auf **+ Integration hinzufügen**
3. Suche nach **"AI Dashboard Generator"**
4. Folge dem Einrichtungsassistenten:
   - **KI-Anbieter** wählen (Offline für kostenlose Nutzung)
   - Optionaler **API-Schlüssel** für bessere KI-Ergebnisse
   - **Dashboard-Titel** festlegen

---

## 🚀 Erste Schritte

### Empfohlene Voraussetzung: Mushroom Cards

Installiere [Mushroom Cards](https://github.com/piitaya/lovelace-mushroom) über HACS (Frontend → Suche "Mushroom") für das beste Aussehen.

### Dashboard generieren

1. Öffne **"AI Dashboard"** in der HA-Seitenleiste
2. (Optional) Lade Raumbilder im Tab **"Räume & Bilder"** hoch
3. Klicke auf **"Dashboard erstellen"**
4. Warte auf die Analyse (30–60 Sekunden mit KI, ~5 Sekunden offline)
5. Klicke auf **"Auf Dashboard anwenden"**
6. Das neue Dashboard erscheint in der Seitenleiste als **"AI Dashboard"**

---

## ⚙️ Konfiguration

### KI-Anbieter

| Anbieter | Qualität | Kosten | API-Key nötig |
|----------|----------|--------|---------------|
| **Offline** | Gut | Kostenlos | ❌ |
| **OpenAI GPT-4o-mini** | Sehr gut | ~$0.001/Nutzung | ✅ |
| **OpenAI GPT-4o** | Exzellent | ~$0.005/Nutzung | ✅ |
| **Claude 3.5 Haiku** | Sehr gut | ~$0.001/Nutzung | ✅ |
| **Claude 3.5 Sonnet** | Exzellent | ~$0.003/Nutzung | ✅ |
| **Gemini 2.5 Flash** | Sehr gut | Kostenlos (Limit) | ✅ |

### Was wird gefiltert?

Folgende Entities werden automatisch ausgeblendet:
- Signal-Stärke-Sensoren (`_rssi`, `_lqi`, `_signal_strength`)
- Spannungs-Sensoren (`_voltage`)
- Debug/interne Entities (`_debug`, `_raw`, `_internal`)
- Uptime & technische Zähler
- Entities mit internen Hash-IDs
- Domains: `automation`, `script`, `scene`, `update`

### Welche Karten werden generiert?

Das Dashboard nutzt diese Card-Typen:
- `mushroom-light-card` – Lichter mit Helligkeit & Farbsteuerung
- `mushroom-climate-card` – Thermostate
- `mushroom-media-player-card` – TV, Lautsprecher
- `mushroom-cover-card` – Rollos, Jalousien
- `mushroom-entity-card` – Schalter, Sensoren
- `mushroom-person-card` – Personen/Anwesenheit
- `mushroom-template-card` – Begrüßung, Raumnavigation
- `mushroom-chips-card` – Statusübersicht
- `weather-forecast` – Wettervorhersage

---

## 🔄 Dashboard aktualisieren

Nach dem Hinzufügen neuer Geräte oder Räume:

1. Stelle sicher, dass alle Geräte in **Einstellungen → Bereiche & Zonen** einem Raum zugewiesen sind
2. Öffne den **AI Dashboard Generator** in der Seitenleiste
3. Klicke auf **🔄 Räume neu laden** (oben rechts)
4. Klicke auf **"Neu generieren"**
5. Klicke auf **"Auf Dashboard anwenden"**

### Über Home Assistant Service

Du kannst auch automatisieren:

```yaml
service: ai_dashboard.generate_dashboard
data:
  auto_apply: true
```

---

## 🎨 Dashboard-Struktur

Das generierte Dashboard hat folgende Struktur:

```
📊 Übersicht (Home-Tab)
├── 🕐 Begrüßung & Datum
├── 🌤 Wetter
├── 👤 Personen
├── 🏠 Raumnavigation (mit Bildern)
├── 💡 Aktive Lichter
└── 🌡️ Klimaübersicht

🛋️ Wohnzimmer
├── 📸 Raumbild (optional)
├── 💡 Lichter
├── 🌡️ Heizung
├── 📺 Medien
└── 📊 Sensoren

🛏 Schlafzimmer
├── ...
```

---

## 🐛 Probleme & Support

- **Issues:** [GitHub Issues](https://github.com/YOUR_USERNAME/ai-dashboard-generator/issues)
- **Logs:** Einstellungen → System → Protokolle → nach `ai_dashboard` suchen

### Häufige Probleme

**"Mushroom Cards fehlen"**: Installiere [Mushroom Cards](https://github.com/piitaya/lovelace-mushroom) via HACS → Frontend.

**"Dashboard wird nicht angezeigt"**: Starte HA einmal neu und lade dann die Seite hart neu (Strg+Shift+R).

**"KI-Fehler"**: Prüfe deinen API-Schlüssel unter Einstellungen → AI Dashboard Generator.

---

## 📋 Anforderungen

- Home Assistant **2024.1.0** oder neuer
- [HACS](https://hacs.xyz/) installiert
- (Empfohlen) [Mushroom Cards](https://github.com/piitaya/lovelace-mushroom) via HACS

---

## 📄 Lizenz

MIT License – Freie Nutzung, auch kommerziell.

---

## ⭐ Unterstützung

Wenn dir dieses Plugin gefällt, gib ihm einen ⭐ auf GitHub!

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=YOUR_USERNAME&repository=ai-dashboard-generator&category=integration)
