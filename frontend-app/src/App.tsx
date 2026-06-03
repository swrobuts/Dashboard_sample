import { Routes, Route, Navigate } from 'react-router-dom'
import { Shell } from './components/shell'
import { Styleguide } from './routes/Styleguide'
import { Ranking } from './routes/ranking.tsx'
import { Factors } from './routes/factors.tsx'
import { Map } from './routes/map'
import { Quality } from './routes/quality'

function App() {
    return (
        <Routes>
            {/* Shell als Layout, darunter die einzelnen Tabs */}
            <Route element={<Shell />}>
                <Route path="/" element={<Navigate to="/ranking" replace />} />
                <Route path="/ranking" element={<Ranking />} />
                <Route path="/factors" element={<Factors />} />
                <Route path="/map" element={<Map />} />
                <Route path="/quality" element={<Quality />} />
                <Route path="/styleguide" element={<Styleguide />} />
            </Route>
        </Routes>
    )
}

export default App