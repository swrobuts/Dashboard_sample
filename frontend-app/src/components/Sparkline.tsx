type SparklineProps = {
    data: readonly (number | null)[]
    width?: number
    height?: number
    stroke?: string
    strokeWidth?: number
    /** Index in `data`, der als ausgefüllter Punkt hervorgehoben wird. */
    highlightIndex?: number
    /** Farbe des Hervorhebungspunkts. Default: Akzent-Selektionsfarbe. */
    highlightColor?: string
    /** Externe Y-Skala. Wenn unbestimmt: Auto-Skala aus den eigenen Daten. */
    scaleMin?: number
    scaleMax?: number
}

/**
 * Tufte-Sparkline mit ehrlicher Lückendarstellung (F6/F7) und optionalem
 * Hervorhebungspunkt für das gerade gewählte Jahr.
 */
export function Sparkline({
                              data,
                              width = 60,
                              height = 16,
                              stroke = 'var(--ink)',
                              strokeWidth = 1.25,
                              highlightIndex,
                              highlightColor = 'var(--accent)',
                              scaleMin,
                              scaleMax,
                          }: SparklineProps) {
    const validValues = data.filter((v): v is number => v != null)
    if (validValues.length < 2) return null

    const min = scaleMin ?? Math.min(...validValues)
    const max = scaleMax ?? Math.max(...validValues)
    const range = max - min || 1

    // Horizontales Padding nur, wenn ein Punkt hervorgehoben wird —
    // sonst hat sein Halo am Rand keinen Platz.
    const pad = highlightIndex !== undefined ? 5 : 0
    const innerWidth = width - 2 * pad

    // Path mit 'M' (move) für Segmentsprünge, 'L' (line to) für Fortsetzung.
    let d = ''
    let inSegment = false
    data.forEach((v, i) => {
        if (v == null) {
            inSegment = false
            return
        }
        const x = pad + (i / (data.length - 1)) * innerWidth
        const y = height - ((v - min) / range) * height
        d += (inSegment ? ' L' : ' M') + `${x.toFixed(2)},${y.toFixed(2)}`
        inSegment = true
    })

    // Position des Highlight-Punkts (nur wenn Index existiert und Wert nicht null)
    let highlight: { x: number; y: number } | null = null
    if (
        highlightIndex !== undefined &&
        highlightIndex >= 0 &&
        highlightIndex < data.length
    ) {
        const v = data[highlightIndex]
        if (v != null) {
            const x = pad + (highlightIndex / (data.length - 1)) * innerWidth
            const y = height - ((v - min) / range) * height
            highlight = { x, y }
        }
    }

    return (
        <svg
            width={width}
            height={height}
            viewBox={`0 0 ${width} ${height}`}
            role="img"
            aria-label="Zeitreihe"
        >
            <path
                d={d.trim()}
                fill="none"
                stroke={stroke}
                strokeWidth={strokeWidth}
                strokeLinejoin="round"
                strokeLinecap="round"
            />
            {highlight && (
                <circle
                    cx={highlight.x}
                    cy={highlight.y}
                    r={4.0}
                    fill={highlightColor}
                    stroke="var(--bg)"
                    strokeWidth={0.5}
                />
            )}
        </svg>
    )
}