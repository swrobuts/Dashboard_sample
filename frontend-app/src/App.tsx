import { Routes, Route, Navigate } from 'react-router-dom'
import { Styleguide } from './routes/Styleguide'

function App() {
  return (
      <Routes>
        <Route path="/" element={<Navigate to="/styleguide" replace />} />
        <Route path="/styleguide" element={<Styleguide />} />
      </Routes>
  )
}

export default App