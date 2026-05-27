# Frontend-Konventionen

Kurzdoku, kein vollständiges Scaffold. Die Vorgaben adressieren F9 und F10 aus dem Pre-Mortem.

## Architektur in drei Schichten — auch *innerhalb* des Frontends

```
src/
├── api/         ← Data-Layer: einzige Stelle, die fetcht
├── state/       ← URL-State + reine UI-Toggles
├── components/  ← reine Präsentation, bekommt Daten als Props
└── routes/      ← Komposition der Seiten
```

**Regel 1: Nur `src/api/` darf `fetch()` oder `supabase` aufrufen.**
Kein Component-Code fetcht inline. Wer das tut, bricht F10 (Logik-Verdoppelung).

**Regel 2: TanStack Query für Server-State, URL für Cross-Tab-Zustand, `useState` nur für lokales UI** (Hover, offener Tooltip, expandierter Block).

## URL-as-State (gegen F9)

Jeder Filter, der einen Permalink verdient (Jahr, Land, Top-N, Tab), lebt in der URL. Damit funktionieren Browser-Back, Teilen und Bookmarks ohne weitere Logik.

```typescript
// src/state/url-state.ts
import { useSearchParams } from "react-router-dom";

export type DashboardState = {
  year: number;
  iso3: string | null;
  tab: "ranking" | "factors" | "map" | "quality";
};

export function useDashboardState(): [DashboardState, (p: Partial<DashboardState>) => void] {
  const [params, setParams] = useSearchParams();
  const state: DashboardState = {
    year: Number(params.get("y")) || 2025,
    iso3: params.get("c"),
    tab:  (params.get("t") as DashboardState["tab"]) || "ranking",
  };
  const patch = (p: Partial<DashboardState>) => {
    const next = new URLSearchParams(params);
    if (p.year !== undefined) next.set("y", String(p.year));
    if (p.iso3 !== undefined) {
      p.iso3 ? next.set("c", p.iso3) : next.delete("c");
    }
    if (p.tab !== undefined) next.set("t", p.tab);
    setParams(next, { replace: false });
  };
  return [state, patch];
}
```

## API-Layer (gegen F10 — SSOT)

Eine Datei pro View. Jede Funktion ruft *eine* View und liefert typisierte Daten. Keine Aggregation, kein Sort, kein Filter im Frontend, der schon in SQL stattfindet.

```typescript
// src/api/happiness.ts
import { createClient } from "@supabase/supabase-js";

const sb = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY,
);

export type HappinessRow = {
  iso3: string; country: string; year: number; rank: number;
  life_evaluation: number;
  has_factor_decomposition: boolean;
  /* … */
};

export async function getRanking(year: number, limit = 25) {
  const { data, error } = await sb
    .from("v_ranking")          // ← View, nicht Tabelle
    .select("*")
    .eq("year", year)
    .limit(limit);
  if (error) throw error;
  return data as HappinessRow[];
}

export async function getCountryTimeseries(iso3: string) {
  const { data, error } = await sb
    .from("v_country_year_grid") // ← liefert auch Gaps explizit
    .select("*")
    .eq("iso3", iso3)
    .order("year");
  if (error) throw error;
  return data;
}
```

## Lücken zeigen statt verschweigen (F6/F7)

Wenn `v_country_year_grid` einen `is_gap = true` liefert, **nicht interpolieren**. Recharts kennt `connectNulls={false}` — explizit setzen.

```tsx
<Line dataKey="life_evaluation" connectNulls={false} />
```

Zusätzlich eine kleine Pille im Chart-Header: `2013 nicht erhoben · Haiti ab 2021 keine Daten` — kommt aus `v_data_quality`.

## Faktor-Charts gracefully degradieren (F2)

Vor jeder Faktor-Visualisierung auf `has_factor_decomposition` prüfen. Wenn FALSE: Komponente zeigt einen kurzen Hinweis statt leerer Achsen.

```tsx
{row.has_factor_decomposition
  ? <FactorBars row={row} />
  : <Notice>Faktor-Zerlegung erst ab 2019 verfügbar</Notice>}
```

## Story-Anker (gegen F11)

Maximal **vier** Tabs. Jeder beantwortet eine Frage, die im Hichert-Stil als analytischer Titel oben steht:

1. **Ranking** — „Wer führt 2025, wer rutscht?"
2. **Faktoren** — „Was erklärt den Score? (ab 2019)"
3. **Karte** — „Wo liegen die glücklichen Länder?"
4. **Datenqualität** — „Was steckt — und was nicht?"

Mehr Tabs heißt: vorher die Frage formulieren, sonst nicht hinzufügen.
