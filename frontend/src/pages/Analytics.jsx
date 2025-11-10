import { useState, useEffect } from 'react'
import { TrendingUp, Activity, Users, AlertCircle } from 'lucide-react'
import { motion } from 'framer-motion'
import { analyticsAPI } from '../api'

export const Analytics = () => {
  const [dashboardData, setDashboardData] = useState(null)
  const [teamHealth, setTeamHealth] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  
  useEffect(() => {
    // Prevent page scroll on mount
    window.scrollTo(0, 0)
    loadAnalytics()
  }, [])
  
  const loadAnalytics = async () => {
    try {
      const [dashboard, health] = await Promise.all([
        analyticsAPI.getDashboard(),
        analyticsAPI.getTeamHealth()
      ])
      
      setDashboardData(dashboard)
      setTeamHealth(health)
    } catch (error) {
      console.error('Error loading analytics:', error)
    } finally {
      setIsLoading(false)
    }
  }
  
  if (isLoading) {
    return (
      <div className="min-h-screen p-6 flex items-center justify-center">
        <div className="text-center">
          <div className="loading-pulse mb-4">
            <Activity className="w-12 h-12 text-openai-green mx-auto" />
          </div>
          <p className="text-gray-400">Loading analytics...</p>
        </div>
      </div>
    )
  }
  
  return (
    <div className="min-h-screen p-8">
      {/* Header */}
      <div className="mb-10">
        <h1 className="text-6xl font-bold text-white mb-4">Team Analytics</h1>
        <p className="text-2xl text-gray-300">
          Comprehensive insights into your team's performance and health
        </p>
      </div>
      
      {/* Team Health Card */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-card p-12 mb-10"
      >
        <div className="flex items-center justify-between mb-10">
          <div>
            <h2 className="text-4xl font-bold text-white mb-4">Team Health Score</h2>
            <p className="text-xl text-gray-300">Based on recent sentiment analysis and velocity</p>
          </div>
          <Users className="w-20 h-20 text-openai-green" />
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-4 gap-10">
          <div className="text-center">
            <div className={`text-7xl font-bold mb-4 ${
              teamHealth?.status === 'excellent' ? 'text-green-400' :
              teamHealth?.status === 'good' ? 'text-blue-400' :
              teamHealth?.status === 'fair' ? 'text-yellow-400' :
              'text-red-400'
            }`}>
              {teamHealth?.health_score?.toFixed(0) || 'N/A'}
            </div>
            <div className="text-lg text-gray-300 font-medium">Overall Score</div>
            {teamHealth?.status && (
              <div className={`mt-4 inline-block px-5 py-2.5 rounded-full text-base font-medium ${
                teamHealth.status === 'excellent' ? 'bg-green-500/20 text-green-400' :
                teamHealth.status === 'good' ? 'bg-blue-500/20 text-blue-400' :
                teamHealth.status === 'fair' ? 'bg-yellow-500/20 text-yellow-400' :
                'bg-red-500/20 text-red-400'
              }`}>
                {teamHealth.status}
              </div>
            )}
          </div>
          
          <div className="text-center">
            <div className="text-6xl font-bold text-white mb-4">
              {dashboardData?.stories?.total || 0}
            </div>
            <div className="text-lg text-gray-300 font-medium">Total Stories</div>
            <div className="text-base text-gray-500 mt-3">All time</div>
          </div>
          
          <div className="text-center">
            <div className="text-6xl font-bold text-white mb-4">
              {dashboardData?.stories?.closed || dashboardData?.stories?.completed || 0}
            </div>
            <div className="text-lg text-gray-300 font-medium">Closed Stories</div>
            <div className="text-base text-gray-500 mt-3">From Jira</div>
          </div>
          
          <div className="text-center">
            <div className="text-6xl font-bold text-white mb-4">
              {dashboardData?.stories?.completion_rate?.toFixed(0) || 0}%
            </div>
            <div className="text-lg text-gray-300 font-medium">Completion Rate</div>
            <div className="text-base text-gray-500 mt-3">Based on stories</div>
          </div>
        </div>
      </motion.div>
      
      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-10 mb-10">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="glass-card p-10"
        >
          <div className="flex items-center gap-5 mb-8">
            <div className="w-16 h-16 bg-gradient-to-br from-openai-blue to-openai-green rounded-lg flex items-center justify-center">
              <TrendingUp className="w-8 h-8 text-white" />
            </div>
            <h3 className="text-2xl font-semibold text-white">Features</h3>
          </div>
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-lg text-gray-300">Total</span>
              <span className="text-2xl font-semibold text-white">
                {dashboardData?.features?.total || 0}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-lg text-gray-300">With Context</span>
              <span className="text-2xl font-semibold text-white">
                {dashboardData?.features?.with_context || 0}
              </span>
            </div>
          </div>
        </motion.div>
        
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="glass-card p-10"
        >
          <div className="flex items-center gap-5 mb-8">
            <div className="w-16 h-16 bg-gradient-to-br from-openai-blue to-openai-green rounded-lg flex items-center justify-center">
              <Activity className="w-8 h-8 text-white" />
            </div>
            <h3 className="text-2xl font-semibold text-white">Stories</h3>
          </div>
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-lg text-gray-300">Total</span>
              <span className="text-2xl font-semibold text-white">
                {dashboardData?.stories?.total || 0}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-lg text-gray-300">Active</span>
              <span className="text-2xl font-semibold text-white">
                {dashboardData?.stories?.active || 0}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-lg text-gray-300">Closed</span>
              <span className="text-2xl font-semibold text-white">
                {dashboardData?.stories?.closed || dashboardData?.stories?.completed || 0}
              </span>
            </div>
            <div className="w-full bg-white/10 rounded-full h-4 mt-6">
              <div
                className="bg-gradient-to-r from-openai-blue to-openai-green h-4 rounded-full transition-all"
                style={{ width: `${dashboardData?.stories?.completion_rate || 0}%` }}
              />
            </div>
          </div>
        </motion.div>
        
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="glass-card p-10"
        >
          <div className="flex items-center gap-5 mb-8">
            <div className="w-16 h-16 bg-gradient-to-br from-openai-blue to-openai-green rounded-lg flex items-center justify-center">
              <AlertCircle className="w-8 h-8 text-white" />
            </div>
            <h3 className="text-2xl font-semibold text-white">Sprints</h3>
          </div>
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-lg text-gray-300">Total Sprints</span>
              <span className="text-2xl font-semibold text-white">
                {dashboardData?.sprints?.total || 0}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-lg text-gray-300">Active</span>
              <span className="text-2xl font-semibold text-white">
                {dashboardData?.sprints?.active || 0}
              </span>
            </div>
          </div>
        </motion.div>
      </div>
      
      {/* Team Health Note */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
        className="glass-card p-10"
      >
        <h3 className="text-3xl font-semibold text-white mb-8">Team Health Metrics</h3>
        <div className="text-center py-16">
          <div className="text-xl text-gray-300 mb-4">
            Team health is calculated based on story completion rates.
          </div>
          <div className="text-lg text-gray-400">
            Health score reflects the percentage of completed stories in the last 30 days.
          </div>
        </div>
      </motion.div>
    </div>
  )
}

