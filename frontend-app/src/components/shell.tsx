import type { CSSProperties } from 'react'
import { NavLink, Outlet } from 'react-router-dom'

const TABS = [
    { to: '/ranking', label: 'Ranking' },
    { to: '/factors', label: 'Faktoren' },
    { to: '/map',     label: 'Karte' },
    { to: '/quality', label: 'Datenqualität' },
] as const

const tabBase: CSSProperties = {
    fontSize: 'var(--text-small)',
    color: 'var(--muted)',
    padding: 'calc(var(--grid) * 1) 0',
    marginRight: 'calc(var(--grid) * 4)',
    borderBottom: '2px solid transparent',
    textDecoration: 'none',
    display: 'inline-block',
}

const tabActive: CSSProperties = {
    color: 'var(--fg)',
    borderBottom: '2px solid var(--fg)',
}

export function Shell() {
    return (
        <div style={{
            maxWidth: 'var(--content-max)',
            margin: '0 auto',
            padding: 'var(--pad)',
        }}>
            {/* Brand-Zeile */}
            <p style={{
                fontSize: 'var(--text-micro)',
                color: 'var(--muted)',
                textTransform: 'uppercase',
                letterSpacing: 'var(--track-label)',
                margin: 0,
                marginBottom: 'calc(var(--grid) * 1)',
            }}>
                Happiness Dashboard · World Happiness Report 2011–2025
            </p>

            {/* Tab-Leiste */}
            <nav style={{
                borderBottom: '1px solid var(--rule)',
                marginBottom: 'calc(var(--grid) * 5)',
            }}>
                {TABS.map(t => (
                    <NavLink
                        key={t.to}
                        to={t.to}
                        style={({ isActive }) => ({
                            ...tabBase,
                            ...(isActive ? tabActive : {}),
                        })}
                    >
                        {t.label}
                    </NavLink>
                ))}
                <NavLink
                    to="/styleguide"
                    style={({ isActive }) => ({
                        ...tabBase,
                        ...(isActive ? tabActive : {}),
                        float: 'right',
                        marginRight: 0,
                        fontSize: 'var(--text-micro)',
                        textTransform: 'uppercase',
                        letterSpacing: 'var(--track-label)',
                    })}
                >
                    Stilkachel
                </NavLink>
            </nav>

            {/* Hier rendert die jeweils aktive Route */}
            <Outlet />
        </div>
    )
}