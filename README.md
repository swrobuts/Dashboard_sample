# World Happiness Report Dashboard

Minimalistisches Dashboard zur Analyse der Lebensqualität weltweit (2015-2025).

**Design-Prinzipien:** Tufte/Cleveland – hohe Data-Ink Ratio, keine unnötige Dekoration.

## 🚀 Installation

```bash
# 1. Virtuelle Umgebung erstellen
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# oder: venv\Scripts\activate  # Windows

# 2. Abhängigkeiten installieren
pip install -r requirements.txt

# 3. Dashboard starten
python app.py
```

Das Dashboard ist dann unter **http://localhost:8050** erreichbar.

## 📊 Features

- **Weltkarte:** Choropleth-Visualisierung der Happiness Scores
- **Ranking:** Top 15 Länder nach Jahr und Region filterbar
- **Trends:** Zeitliche Entwicklung für ausgewählte Länder
- **Faktoren:** Aufschlüsselung nach GDP, Soziale Unterstützung, etc.
- **Scatter:** Korrelation GDP vs. Happiness mit Trendlinie
- **Regionen:** Vergleich der regionalen Durchschnitte

## ⚙️ Konfiguration

Die Supabase-Verbindung ist in `.env` konfiguriert:

```env
SUPABASE_URL=https://supabase.butscher.cloud
SUPABASE_KEY=eyJhbG...
```

**Wichtig:** Der `Accept-Profile: WorldHappiness` Header ist bereits im Code integriert.

## 📁 Projektstruktur

```
whr_dashboard/
├── app.py              # Hauptanwendung mit Callbacks
├── data_loader.py      # Supabase API-Verbindung
├── requirements.txt    # Python-Abhängigkeiten
├── .env                # Konfiguration
├── assets/
│   └── style.css       # Minimalistisches CSS
└── README.md
```

## 🎨 Design

- **Typografie:** Source Serif Pro (Headlines), Source Sans Pro (Body)
- **Farben:** Dezente Palette, Fokus auf Daten
- **Layout:** Responsive Grid mit klaren Proportionen
- **Charts:** Keine 3D-Effekte, dezente Gridlines, versteckte Toolbar

## 🔧 Deployment (Produktion)

```bash
# Mit Gunicorn
gunicorn app:server -b 0.0.0.0:8050 -w 4

# Oder als Systemd-Service
sudo nano /etc/systemd/system/whr-dashboard.service
```

Beispiel Systemd-Service:

```ini
[Unit]
Description=World Happiness Dashboard
After=network.target

[Service]
User=www-data
WorkingDirectory=/path/to/whr_dashboard
ExecStart=/path/to/venv/bin/gunicorn app:server -b 127.0.0.1:8050 -w 2
Restart=always

[Install]
WantedBy=multi-user.target
```

## 📈 Datenbank-Schema

Das Dashboard greift auf das `WorldHappiness` Schema in Supabase zu:

- `dim_region` – 10 Regionen
- `dim_country` – 167 Länder
- `fact_happiness` – 1.509 Datensätze (2015-2025)

---

Erstellt mit 💙 Plotly Dash | Daten: World Happiness Report
