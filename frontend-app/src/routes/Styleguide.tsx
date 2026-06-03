import { Fragment } from 'react'
import type { CSSProperties } from 'react'
import { Sparkline } from '../components/Sparkline'

// Finnland 2011–2025 (echte Werte aus dem WHR-Datensatz, ohne 2013)
const finlandData = [
    7.40, 7.39, 7.41, 7.41, 7.43, 7.55, 7.63, 7.78, 7.84, 7.81, 7.82, 7.74, 7.74, 7.76,
]

const microLabel: CSSProperties = {
    fontSize: 'var(--text-micro)',
    color: 'var(--muted)',
    textTransform: 'uppercase',
    letterSpacing: 'var(--track-label)',
    margin: 0,
    marginBottom: 'calc(var(--grid) * 2)',
}

const section: CSSProperties = {
    marginTop: 'calc(var(--grid) * 8)',
}

const typeScale = [
    { label: 'Display 40 px', size: 'var(--text-display)', weight: 'var(--weight-medium)',  track: 'var(--track-display)', sample: 'Wie zufrieden lebt die Welt?' },
    { label: 'Title 28 px',   size: 'var(--text-title)',   weight: 'var(--weight-medium)',  track: 'var(--track-display)', sample: 'Ranking 2025 — die zehn glücklichsten Länder' },
    { label: 'H2 20 px',      size: 'var(--text-h2)',      weight: 'var(--weight-medium)',  track: '0',                    sample: 'Faktoren der Lebensbewertung' },
    { label: 'Body 16 px',    size: 'var(--text-body)',    weight: 'var(--weight-regular)', track: '0',                    sample: 'Finnland führt seit 2018 ununterbrochen. Dänemark und Island folgen knapp dahinter.' },
    { label: 'Small 14 px',   size: 'var(--text-small)',   weight: 'var(--weight-regular)', track: '0',                    sample: 'Datenstand 2025 · World Happiness Report' },
    { label: 'Micro 12 px',   size: 'var(--text-micro)',   weight: 'var(--weight-regular)', track: 'var(--track-label)',   sample: 'ACHSENBESCHRIFTUNG · LABEL' },
]

const colors = [
    { token: '--bg',     value: '#fafaf7', role: 'Hintergrund' },
    { token: '--fg',     value: '#1a1a1a', role: 'Text primär' },
    { token: '--ink',    value: '#2a2a2a', role: 'Datentinte' },
    { token: '--muted',  value: '#737368', role: 'Sekundärtext' },
    { token: '--rule',   value: '#e5e5dd', role: 'Trennlinien' },
    { token: '--accent', value: '#7c9eb2', role: 'Selektion' },
    { token: '--neg',    value: '#a04848', role: 'Negativ-Delta' },
    { token: '--pos',    value: '#5a7c4a', role: 'Positiv-Delta' },
]

export function Styleguide() {
    return (
        <>
            {/* Kopfzeile */}
            <p style={microLabel}>Happiness Dashboard · Stilkachel</p>
            <h1 style={{
                fontSize: 'var(--text-display)',
                fontWeight: 'var(--weight-medium)',
                letterSpacing: 'var(--track-display)',
                lineHeight: 'var(--leading-tight)',
                margin: 0,
            }}>
                Designsystem v0
            </h1>
            <p style={{
                fontSize: 'var(--text-body)',
                color: 'var(--muted)',
                maxWidth: '54ch',
                marginTop: 'calc(var(--grid) * 2)',
                lineHeight: 'var(--leading-loose)',
            }}>
                Lebende Spezifikation. Jede Komponente im Dashboard hält sich an die hier
                gezeigten Größen, Farben und Chart-Primitive. Referenzen: Tufte (Data-Ink),
                Few (Wahrnehmung), Aicher (HfG Ulm).
            </p>

            {/* Typografie */}
            <section style={section}>
                <p style={microLabel}>Typografie</p>
                <div style={{
                    display: 'grid',
                    gridTemplateColumns: '160px 1fr',
                    rowGap: 'calc(var(--grid) * 3)',
                    alignItems: 'baseline',
                }}>
                    {typeScale.map(t => (
                        <Fragment key={t.label}>
                            <div style={{
                                fontSize: 'var(--text-micro)',
                                color: 'var(--muted)',
                                textTransform: 'uppercase',
                                letterSpacing: 'var(--track-label)',
                            }}>{t.label}</div>
                            <div style={{
                                fontSize: t.size,
                                fontWeight: t.weight,
                                letterSpacing: t.track,
                                color: 'var(--fg)',
                                lineHeight: 'var(--leading-tight)',
                            }}>{t.sample}</div>
                        </Fragment>
                    ))}
                </div>
            </section>

            {/* Farben */}
            <section style={section}>
                <p style={microLabel}>Farbpalette</p>
                <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(4, 1fr)',
                    gap: 'var(--gutter)',
                }}>
                    {colors.map(c => (
                        <div key={c.token}>
                            <div style={{
                                width: '100%',
                                height: 80,
                                background: c.value,
                                border: '1px solid var(--rule)',
                            }} />
                            <div style={{ marginTop: 'var(--grid)' }}>
                                <div style={{
                                    fontSize: 'var(--text-small)',
                                    color: 'var(--fg)',
                                    fontWeight: 'var(--weight-medium)',
                                    fontFamily: 'ui-monospace, monospace',
                                }}>{c.token}</div>
                                <div style={{
                                    fontSize: 'var(--text-micro)',
                                    color: 'var(--muted)',
                                    fontFamily: 'ui-monospace, monospace',
                                }}>{c.value}</div>
                                <div style={{
                                    fontSize: 'var(--text-micro)',
                                    color: 'var(--muted)',
                                    marginTop: 2,
                                }}>{c.role}</div>
                            </div>
                        </div>
                    ))}
                </div>
            </section>

            {/* Chart-Primitive */}
            <section style={section}>
                <p style={microLabel}>Chart-Primitive</p>
                <div style={{
                    display: 'grid',
                    gridTemplateColumns: '160px 1fr',
                    rowGap: 'calc(var(--grid) * 4)',
                    alignItems: 'center',
                }}>
                    {/* Sparkline-Zeile */}
                    <div style={{
                        fontSize: 'var(--text-micro)',
                        color: 'var(--muted)',
                        textTransform: 'uppercase',
                        letterSpacing: 'var(--track-label)',
                    }}>Sparkline</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 'calc(var(--grid) * 2)' }}>
                        <span style={{ fontSize: 'var(--text-small)', color: 'var(--fg)', minWidth: 80 }}>Finnland</span>
                        <span style={{
                            fontSize: 'var(--text-small)',
                            color: 'var(--fg)',
                            fontVariantNumeric: 'tabular-nums',
                            minWidth: 40,
                        }}>7,76</span>
                        <Sparkline data={finlandData} width={120} height={20} />
                        <span style={{ fontSize: 'var(--text-micro)', color: 'var(--muted)' }}>2011 → 2025</span>
                    </div>

                    {/* Whisker-Zeile */}
                    <div style={{
                        fontSize: 'var(--text-micro)',
                        color: 'var(--muted)',
                        textTransform: 'uppercase',
                        letterSpacing: 'var(--track-label)',
                    }}>Whisker</div>
                    <div>
                        <svg width={240} height={40} viewBox="0 0 240 40" role="img" aria-label="Konfidenzintervall">
                            {/* Mittellinie */}
                            <line x1="40" y1="20" x2="200" y2="20" stroke="var(--rule)" strokeWidth="0.5" />
                            {/* Lower whisker */}
                            <line x1="70" y1="12" x2="70" y2="28" stroke="var(--ink)" strokeWidth="0.5" opacity="0.5" />
                            {/* Point */}
                            <line x1="120" y1="8" x2="120" y2="32" stroke="var(--ink)" strokeWidth="1.25" />
                            {/* Upper whisker */}
                            <line x1="170" y1="12" x2="170" y2="28" stroke="var(--ink)" strokeWidth="0.5" opacity="0.5" />
                            {/* Achsenpunkte */}
                            <text x="70"  y="38" fontSize="11" fill="var(--muted)" textAnchor="middle">7,69</text>
                            <text x="120" y="38" fontSize="11" fill="var(--muted)" textAnchor="middle">7,76</text>
                            <text x="170" y="38" fontSize="11" fill="var(--muted)" textAnchor="middle">7,84</text>
                        </svg>
                    </div>

                    {/* Range-Frame-Zeile */}
                    <div style={{
                        fontSize: 'var(--text-micro)',
                        color: 'var(--muted)',
                        textTransform: 'uppercase',
                        letterSpacing: 'var(--track-label)',
                    }}>Range-Frame</div>
                    <div>
                        <svg width={240} height={40} viewBox="0 0 240 40" role="img" aria-label="Range-Achse">
                            {/* Tufte: Achse zeigt nur das tatsächliche Datenmin/max */}
                            <line x1="40" y1="20" x2="200" y2="20" stroke="var(--ink)" strokeWidth="1" />
                            <line x1="40" y1="16" x2="40" y2="24" stroke="var(--ink)" strokeWidth="1" />
                            <line x1="200" y1="16" x2="200" y2="24" stroke="var(--ink)" strokeWidth="1" />
                            <text x="40"  y="38" fontSize="11" fill="var(--muted)" textAnchor="middle">1,36</text>
                            <text x="200" y="38" fontSize="11" fill="var(--muted)" textAnchor="middle">7,86</text>
                            <text x="120" y="38" fontSize="11" fill="var(--muted)" textAnchor="middle">Lebensbewertung 2011–2025</text>
                        </svg>
                    </div>
                </div>
            </section>

            {/* Fußnote */}
            <p style={{ ...microLabel, marginTop: 'calc(var(--grid) * 10)' }}>
                Tufte · Few · Aicher · v0
            </p>
        </>
    )
}