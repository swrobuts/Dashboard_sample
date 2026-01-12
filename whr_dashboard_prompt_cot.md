# World Happiness Report Dashboard - Prompt & Chain of Thought

## Projektübersicht

**Ziel:** Erstellung eines interaktiven Dashboards zum World Happiness Report in zwei Varianten:
- **Power BI:** Optimale Nutzung der nativen BI-Funktionen (Drill-Down, Slicers, DAX-Measures, Q&A)
- **Python (Plotly Dash):** Interaktives Web-Dashboard mit maximaler Flexibilität und Customization

**Zielgruppe:** Lehre (Beispielprojekt für Studierende) + eigene Analysezwecke

**Datenquelle:** Offizielle World Happiness Report Website (https://worldhappiness.report/)

---

## Master-Prompt

```
Du bist ein erfahrener Data Analyst und Dashboard-Entwickler. Deine Aufgabe ist es, 
ein umfassendes, interaktives Dashboard zum World Happiness Report zu erstellen.

### Kontext:
- Datenquelle: Offizielle WHR-Daten von https://worldhappiness.report/
- Zwei Dashboard-Varianten: Power BI und Python (Plotly Dash)
- Jedes Tool soll seine spezifischen Stärken optimal nutzen
- Verwendungszweck: Akademische Lehre und eigene Datenanalyse

### Anforderungen Power BI:
- Professionelles Design mit Corporate-Look
- Interaktive Slicers (Jahr, Region, Land)
- Drill-Down-Funktionalität (Region → Land)
- DAX-Measures für KPIs und Berechnungen
- Bookmarks für verschiedene Ansichten
- Q&A-Funktion für natürlichsprachliche Abfragen
- Tooltips mit Detailinformationen
- Mobile-optimierte Ansicht

### Anforderungen Plotly Dash:
- Modularer, wartbarer Python-Code
- Responsive Layout mit Dash Bootstrap Components
- Callbacks für Echtzeit-Interaktion
- Choropleth-Weltkarte mit Hover-Details
- Zeitreihenanalyse mit Range-Slider
- Vergleichsfunktion für mehrere Länder
- Download-Funktionalität für gefilterte Daten
- Deployment-ready (z.B. für Render, Railway oder eigenen VPS)

### Analyseschwerpunkte:
1. Happiness Score im Zeitverlauf (Trends)
2. Regionale Vergleiche und Rankings
3. Korrelationen zwischen Faktoren (GDP, Social Support, Health, Freedom, etc.)
4. Top/Bottom Performer Analyse
5. Faktorenzerlegung (was trägt zum Happiness Score bei?)

### Qualitätskriterien:
- Klare, intuitive Benutzerführung
- Konsistente Farbgebung und Visualisierungssprache
- Aussagekräftige Titel und Beschriftungen
- Performance-optimiert für große Datenmengen
- Dokumentierter Code (Python) / dokumentiertes Datenmodell (Power BI)
```

---

## Chain of Thought (Schrittweise Umsetzung)

### Phase 1: Fundament
| Schritt | Beschreibung | Output |
|---------|--------------|--------|
| **1.1** | Datenbeschaffung von WHR-Website | CSV/Excel-Dateien |
| **1.2** | Datenexploration & Qualitätsprüfung | EDA-Notebook |
| **1.3** | Datenbereinigung & Transformation | Clean Dataset |
| **1.4** | Datenmodell-Design | ERD / Star-Schema |

### Phase 2: Power BI Dashboard
| Schritt | Beschreibung | Output |
|---------|--------------|--------|
| **2.1** | Datenimport & Power Query Transformation | .pbix mit Datenmodell |
| **2.2** | DAX-Measures entwickeln | Measure-Tabelle |
| **2.3** | Visualisierungen erstellen | Dashboard-Seiten |
| **2.4** | Interaktivität (Slicers, Drill-Down, Bookmarks) | Finales Dashboard |
| **2.5** | Design-Feinschliff & Mobile View | Polished Dashboard |

### Phase 3: Plotly Dash Dashboard
| Schritt | Beschreibung | Output |
|---------|--------------|--------|
| **3.1** | Projektstruktur & Dependencies | requirements.txt, Ordnerstruktur |
| **3.2** | Data Layer (Laden, Caching) | data_loader.py |
| **3.3** | Layout-Komponenten | components.py |
| **3.4** | Callbacks & Interaktivität | callbacks.py |
| **3.5** | Styling & Responsiveness | assets/style.css |
| **3.6** | Testing & Deployment | Dockerfile, deployed App |

### Phase 4: Dokumentation & Lehrmaterial
| Schritt | Beschreibung | Output |
|---------|--------------|--------|
| **4.1** | Technische Dokumentation | README.md |
| **4.2** | Tutorial/Walkthrough für Studierende | Tutorial-Dokument |
| **4.3** | Vergleich Power BI vs. Dash | Lessons Learned |

---

## Aktueller Status

### ✅ Schritt 1.1: Datenbeschaffung (ABGESCHLOSSEN)

**Datenquellen:**
1. **Kaggle WHRFinal.xlsx** – Historische Daten 2015-2023 mit allen Faktoren
2. **World_Happiness_2025.csv** – Aktuelles Ranking 2025

**Kombinierter Datensatz:**
| Eigenschaft | Wert |
|-------------|------|
| Zeilen | 1.509 |
| Jahre | 2015-2025 (10 Jahre) |
| Länder | 167 |
| Regionen | 10 |
| Spalten | 11 (Country, Year, Region, Rank, Score, GDP, Social Support, Life Expectancy, Freedom, Generosity, Corruption) |

**Hinweis:** 2025-Daten enthalten nur Rank und Score (Faktoren = NULL)

---

### ✅ Schritt 1.3 + 1.4: Datenbereinigung & Datenmodell (ABGESCHLOSSEN)

**Erstellte Dateien:**

| Datei | Beschreibung |
|-------|--------------|
| `whr_combined_2015_2025.csv` | Kombinierter, bereinigter Datensatz |
| `whr_combined_2015_2025.xlsx` | Gleiche Daten als Excel |
| `whr_supabase_postgresql.sql` | SQL-Schema für Supabase/PostgreSQL |
| `whr_mssql_server.sql` | SQL-Schema für MS SQL Server + Power BI |

**Datenmodell (Star-Schema):**
```
dim_region (10 Regionen)
     │
dim_country (167 Länder) ─── fact_happiness (1.509 Zeilen)
     │                              │
     └──────────────────────────────┘
                                    │
                            dim_year (2015-2025)
```

**Views für Analyse:**
- `v_happiness_report` – Hauptansicht (denormalisiert)
- `v_current_ranking` – Aktuelles Ranking
- `v_country_trends` – Zeitreihen mit YoY-Veränderung
- `v_regional_averages` – Regionale Durchschnitte

---

### 🔜 Schritt 2.1: Power BI Dashboard (NÄCHSTER SCHRITT)

**Aufgaben:**
1. Daten in MS SQL Server importieren
2. Power BI mit SQL Server verbinden
3. Datenmodell in Power BI validieren
4. Visualisierungen erstellen

---

*Letzte Aktualisierung: Januar 2025*
*Projekt-Owner: Robert*
