function App() {
  return (
    <main style={{
      maxWidth: 'var(--content-max)',
      margin: '0 auto',
      padding: 'var(--pad)',
    }}>
      <p style={{
        fontSize: 'var(--text-micro)',
        color: 'var(--muted)',
        textTransform: 'uppercase',
        letterSpacing: 'var(--track-label)',
        margin: 0,
      }}>
        Happiness Dashboard · Designsystem v0
      </p>

      <h1 style={{
        fontSize: 'var(--text-display)',
        fontWeight: 'var(--weight-medium)',
        letterSpacing: 'var(--track-display)',
        lineHeight: 'var(--leading-tight)',
        margin: '0.5rem 0 2rem',
      }}>
        Wie zufrieden lebt die Welt?
      </h1>

      <p style={{
        fontSize: 'var(--text-body)',
        color: 'var(--ink)',
        maxWidth: '54ch',
        lineHeight: 'var(--leading-loose)',
      }}>
        Wenn dieser Text in Inter erscheint, auf warmweißem Hintergrund, mit
        ruhigem Anthrazit für die Schrift und gedämpften Mikrolabels in Großbuchstaben
        — dann ist das Designsystem geladen. Die Stilkachel mit Farbpalette und
        Chart-Primitiven folgt im nächsten Schritt.
      </p>
    </main>
  );
}

export default App;
