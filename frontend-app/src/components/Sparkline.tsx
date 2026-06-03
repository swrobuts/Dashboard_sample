type SparklineProps = {
    data: number[]
    width?: number
    height?: number
    stroke?: string
    strokeWidth?: number
}

/**
 * Tufte-Sparkline: pure SVG, keine Achsen, keine Labels.
 * Eine Linie, die Bewegung über die Zeit zeigt.
 */
export function Sparkline({
                              data,
                              width = 60,
                              height = 16,
                              stroke = 'var(--ink)',
                              strokeWidth = 1.25,
                          }: SparklineProps) {
    if (data.length < 2) return null

    const min = Math.min(...data)
    const max = Math.max(...data)
    const range = max - min || 1

    const points = data
        .map((v, i) => {
            const x = (i / (data.length - 1)) * width
            const y = height - ((v - min) / range) * height
            return `${x},${y}`
        })
        .join(' ')

    return (
        <svg
            width={width}
            height={height}
            viewBox={`0 0 ${width} ${height}`}
            role="img"
            aria-label="Zeitreihe"
        >
            <polyline
                points={points}
                fill="none"
                stroke={stroke}
                strokeWidth={strokeWidth}
                strokeLinejoin="round"
            />
        </svg>
    )
}