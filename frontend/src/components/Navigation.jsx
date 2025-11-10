import { Link, useLocation } from 'react-router-dom'
import { Home, FileText, BarChart3, Bell, User } from 'lucide-react'

export const Navigation = () => {
  const location = useLocation()
  
  const isActive = (path) => location.pathname === path
  
  return (
    <nav className="glass-card mx-6 mt-6 px-8 py-4">
      <div className="flex items-center justify-between">
        {/* Logo */}
        <Link to="/" className="flex items-center space-x-3 group">
          <div className="w-8 h-8 bg-gradient-to-br from-openai-blue to-openai-green rounded-lg flex items-center justify-center">
            <span className="text-white font-bold text-lg">A</span>
          </div>
          <span className="text-xl font-bold text-white group-hover:text-openai-green transition-colors">
            AutoScrum
          </span>
        </Link>
        
        {/* Navigation Links */}
        <div className="flex items-center flex-1 justify-center space-x-12">
          <Link
            to="/"
            className={`text-base font-medium transition-colors ${
              isActive('/') ? 'text-openai-green' : 'text-gray-400 hover:text-white'
            }`}
          >
            Dashboard
          </Link>
          <Link
            to="/create-feature"
            className={`text-base font-medium transition-colors ${
              isActive('/create-feature') ? 'text-openai-green' : 'text-gray-400 hover:text-white'
            }`}
          >
            Features
          </Link>
          <Link
            to="/analytics"
            className={`text-base font-medium transition-colors ${
              isActive('/analytics') ? 'text-openai-green' : 'text-gray-400 hover:text-white'
            }`}
          >
            Team
          </Link>
        </div>
        
        {/* Right Actions */}
        <div className="flex items-center space-x-4">
          <button className="p-2 rounded-lg hover:bg-white/10 transition-colors">
            <Bell className="w-5 h-5 text-gray-400" />
          </button>
          <button className="w-10 h-10 rounded-full bg-gradient-to-br from-openai-blue to-openai-green flex items-center justify-center">
            <User className="w-5 h-5 text-white" />
          </button>
        </div>
      </div>
    </nav>
  )
}

