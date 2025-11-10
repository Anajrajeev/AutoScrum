import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { Navigation } from './components/Navigation'
import { Dashboard } from './pages/Dashboard'
import { CreateFeature } from './pages/CreateFeature'
import { Analytics } from './pages/Analytics'

function App() {
  return (
    <Router>
      <div className="min-h-screen bg-dark-bg">
        <Navigation />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/create-feature" element={<CreateFeature />} />
          <Route path="/analytics" element={<Analytics />} />
        </Routes>
      </div>
    </Router>
  )
}

export default App

