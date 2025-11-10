import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, MessageSquare, TrendingUp, Users, Activity, ArrowRight, Play, Loader } from 'lucide-react'
import { motion } from 'framer-motion'
import { ChatInterface } from '../components/ChatInterface'
import { queryAPI, analyticsAPI, featuresAPI, transcriptAPI } from '../api'

export const Dashboard = () => {
  const navigate = useNavigate()
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: 'Hello! I\'m your AI Scrum Master assistant. Ask me anything about your sprint progress, team capacity, or project status.'
    }
  ])
  const [isLoading, setIsLoading] = useState(false)
  const [dashboardData, setDashboardData] = useState(null)
  const [teamHealth, setTeamHealth] = useState(null)
  const [recentFeatures, setRecentFeatures] = useState([])

  // Weekly analysis state
  const [weeks, setWeeks] = useState([])
  const [selectedWeek, setSelectedWeek] = useState('')
  const [analysisResult, setAnalysisResult] = useState(null)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  
  useEffect(() => {
    loadDashboardData()
    loadWeeks()
  }, [])
  
  const loadDashboardData = async () => {
    try {
      const [dashboard, health, features] = await Promise.all([
        analyticsAPI.getDashboard(),
        analyticsAPI.getTeamHealth(),
        featuresAPI.list(0, 5)
      ])
      
      setDashboardData(dashboard)
      setTeamHealth(health)
      setRecentFeatures(features.slice(0, 5))
    } catch (error) {
      console.error('Error loading dashboard:', error)
    }
  }

  const loadWeeks = async () => {
    try {
      const response = await transcriptAPI.getWeeks()
      setWeeks(response.weeks)
      if (response.weeks.length > 0) {
        setSelectedWeek(response.weeks[0].week_identifier)
      }
    } catch (error) {
      console.error('Error loading weeks:', error)
    }
  }

  const runWeeklyAnalysis = async () => {
    if (!selectedWeek) return

    setIsAnalyzing(true)
    setAnalysisResult(null)

    try {
      const result = await transcriptAPI.analyzeWeek(selectedWeek)
      setAnalysisResult(result)
    } catch (error) {
      console.error('Error running analysis:', error)
      setAnalysisResult({ error: error.message || 'Failed to analyze week' })
    } finally {
      setIsAnalyzing(false)
    }
  }
  
  const handleSendMessage = async (message) => {
    // Add user message
    setMessages(prev => [...prev, { role: 'user', content: message }])
    setIsLoading(true)
    
    try {
      // Query the Scrum Master
      const response = await queryAPI.query(message)
      
      // Add assistant response
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: response.response 
      }])
    } catch (error) {
      console.error('Error querying:', error)
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: 'I\'m sorry, I encountered an error. Please try again.'
      }])
    } finally {
      setIsLoading(false)
    }
  }
  
  return (
    <div className="min-h-screen p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-5xl font-bold text-white mb-3">Query Your Scrum Master</h1>
          <p className="text-xl text-gray-300">
            Get instant insights about your project and team
          </p>
        </div>
        
        <button
          onClick={() => navigate('/create-feature')}
          className="btn-primary flex items-center gap-3 px-6 py-3 text-lg"
        >
          <Plus className="w-6 h-6" />
          Create Feature
        </button>
      </div>
      
      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="glass-card p-8"
        >
          <div className="flex items-center justify-between mb-4">
            <span className="text-gray-300 text-lg font-medium">Total Features</span>
            <TrendingUp className="w-7 h-7 text-openai-green" />
          </div>
          <div className="text-5xl font-bold text-white">
            {dashboardData?.features?.total || 0}
          </div>
          <div className="text-base text-gray-400 mt-2">
            {dashboardData?.features?.with_context || 0} with context
          </div>
        </motion.div>
        
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="glass-card p-8"
        >
          <div className="flex items-center justify-between mb-4">
            <span className="text-gray-300 text-lg font-medium">Stories</span>
            <MessageSquare className="w-7 h-7 text-openai-green" />
          </div>
          <div className="text-5xl font-bold text-white">
            {dashboardData?.stories?.total || 0}
          </div>
          <div className="text-base text-gray-400 mt-2">
            {dashboardData?.stories?.completion_rate?.toFixed(0) || 0}% complete
          </div>
        </motion.div>
        
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="glass-card p-8"
        >
          <div className="flex items-center justify-between mb-4">
            <span className="text-gray-300 text-lg font-medium">Sprints</span>
            <Activity className="w-7 h-7 text-openai-green" />
          </div>
          <div className="text-5xl font-bold text-white">
            {dashboardData?.sprints?.total || 0}
          </div>
          <div className="text-base text-gray-400 mt-2">
            Active sprints
          </div>
        </motion.div>
        
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="glass-card p-8"
        >
          <div className="flex items-center justify-between mb-4">
            <span className="text-gray-300 text-lg font-medium">Team Health</span>
            <Users className="w-7 h-7 text-openai-green" />
          </div>
          <div className="flex items-center gap-3">
            <div className="text-5xl font-bold text-white">
              {teamHealth?.health_score?.toFixed(0) || 'N/A'}
            </div>
            {teamHealth?.status && (
              <span className={`text-sm px-3 py-1 rounded-full font-medium ${
                teamHealth.status === 'excellent' ? 'bg-green-500/20 text-green-400' :
                teamHealth.status === 'good' ? 'bg-blue-500/20 text-blue-400' :
                teamHealth.status === 'fair' ? 'bg-yellow-500/20 text-yellow-400' :
                'bg-red-500/20 text-red-400'
              }`}>
                {teamHealth.status}
              </span>
            )}
          </div>
        </motion.div>
      </div>
      
      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 lg:items-stretch">
        {/* Left Column - Recent Features & Quick Actions */}
        <div className="lg:col-span-1 space-y-6 flex flex-col">
          {/* Quick Actions */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5 }}
            className="glass-card p-8"
          >
            <h3 className="text-2xl font-semibold text-white mb-6">Quick Actions</h3>
            <div className="space-y-3">
              <button
                onClick={() => navigate('/create-feature')}
                className="w-full glass-card-hover p-4 text-left flex items-center justify-between group"
              >
                <div className="flex items-center gap-4">
                  <Plus className="w-6 h-6 text-openai-green" />
                  <span className="text-base text-white font-medium">Create New Feature</span>
                </div>
                <ArrowRight className="w-5 h-5 text-gray-400 group-hover:text-openai-green transition-colors" />
              </button>
              
              <button
                onClick={() => navigate('/analytics')}
                className="w-full glass-card-hover p-4 text-left flex items-center justify-between group"
              >
                <div className="flex items-center gap-4">
                  <TrendingUp className="w-6 h-6 text-openai-green" />
                  <span className="text-base text-white font-medium">View Analytics</span>
                </div>
                <ArrowRight className="w-5 h-5 text-gray-400 group-hover:text-openai-green transition-colors" />
              </button>
            </div>
          </motion.div>
          
          {/* Recent Features */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.6 }}
            className="glass-card p-8 flex-1"
          >
            <h3 className="text-2xl font-semibold text-white mb-6">Recent Features</h3>
            <div className="space-y-4">
              {recentFeatures.length > 0 ? (
                recentFeatures.map((feature) => (
                  <div key={feature.id} className="glass-card p-4">
                    <h4 className="text-base font-medium text-white mb-2">{feature.name}</h4>
                    <p className="text-sm text-gray-400 line-clamp-2">{feature.description}</p>
                  </div>
                ))
              ) : (
                <div className="text-center py-12">
                  <p className="text-base text-gray-400">No features yet</p>
                  <button
                    onClick={() => navigate('/create-feature')}
                    className="text-sm text-openai-green hover:text-openai-blue transition-colors mt-3"
                  >
                    Create your first feature
                  </button>
                </div>
              )}
            </div>
          </motion.div>
        </div>
        
        {/* Right Column - Chat Interface */}
        <div className="lg:col-span-2 flex h-full">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.7 }}
            className="w-full h-full"
          >
            <ChatInterface
              messages={messages}
              onSendMessage={handleSendMessage}
              isLoading={isLoading}
              title="Ask Your Scrum Master"
            />
          </motion.div>
        </div>
      </div>

      {/* Weekly Team Analysis Section */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.8 }}
        className="mt-12 glass-card p-8"
      >
        <div className="flex items-center gap-4 mb-8">
          <Activity className="w-8 h-8 text-openai-green" />
          <h2 className="text-3xl font-semibold text-white">Weekly Team Analysis</h2>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Week Selection */}
          <div className="lg:col-span-1">
            <label className="block text-base font-medium text-gray-300 mb-3">
              Select Week
            </label>
            <select
              value={selectedWeek}
              onChange={(e) => setSelectedWeek(e.target.value)}
              className="w-full input-glass cursor-pointer"
              disabled={weeks.length === 0}
            >
              {weeks.length === 0 ? (
                <option value="">No weeks available</option>
              ) : (
                weeks.map((week) => (
                  <option 
                    key={week.week_identifier} 
                    value={week.week_identifier}
                  >
                    {week.display_name}
                  </option>
                ))
              )}
            </select>
          </div>

          {/* Analysis Button */}
          <div className="lg:col-span-1 flex items-end">
            <button
              onClick={runWeeklyAnalysis}
              disabled={!selectedWeek || isAnalyzing}
              className="btn-primary flex items-center gap-3 px-6 py-4 text-base disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isAnalyzing ? (
                <>
                  <Loader className="w-5 h-5 animate-spin" />
                  <span>Analyzing...</span>
                </>
              ) : (
                <>
                  <Play className="w-5 h-5" />
                  <span>Run Weekly Team Analysis</span>
                </>
              )}
            </button>
          </div>

          {/* Results Summary */}
          <div className="lg:col-span-1">
            {analysisResult && !analysisResult.error && (
              <div className="glass-card p-6">
                <h4 className="text-base font-medium text-white mb-3">Analysis Summary</h4>
                <div className="space-y-2 text-base text-gray-300">
                  <div>Warnings: {analysisResult.summary?.warnings || 0}</div>
                  <div>Blockers: {analysisResult.summary?.blocker_tickets || 0}</div>
                  <div>Help Tasks: {analysisResult.summary?.help_tasks || 0}</div>
                  <div>Total Actions: {analysisResult.summary?.total_actions || 0}</div>
                </div>
              </div>
            )}
            {analysisResult?.error && (
              <div className="glass-card p-6 border-red-500/20">
                <h4 className="text-base font-medium text-red-400 mb-3">Analysis Error</h4>
                <p className="text-sm text-red-300">{analysisResult.error}</p>
              </div>
            )}
          </div>
        </div>

        {/* Detailed Results */}
        {analysisResult && !analysisResult.error && analysisResult.actions && analysisResult.actions.length > 0 && (
          <div className="mt-8">
            <h3 className="text-2xl font-medium text-white mb-6">Analysis Details</h3>
            <div className="space-y-4">
              {analysisResult.actions.map((action, index) => (
                <motion.div
                  key={index}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.1 }}
                  className={`glass-card p-6 ${
                    action.type === 'warning' ? 'border-yellow-500/20' :
                    action.type === 'blocker_ticket' ? 'border-red-500/20' :
                    action.type === 'help_task' ? 'border-blue-500/20' : ''
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-3">
                        <span className={`text-sm px-3 py-1 rounded-full font-medium ${
                          action.type === 'warning' ? 'bg-yellow-500/20 text-yellow-400' :
                          action.type === 'blocker_ticket' ? 'bg-red-500/20 text-red-400' :
                          action.type === 'help_task' ? 'bg-blue-500/20 text-blue-400' :
                          'bg-gray-500/20 text-gray-400'
                        }`}>
                          {action.type === 'warning' ? 'Warning' :
                           action.type === 'blocker_ticket' ? 'Blocker' :
                           action.type === 'help_task' ? 'Help Request' : action.type}
                        </span>
                        <span className="text-base text-gray-300 font-medium">
                          {action.person_name || action.person}
                        </span>
                      </div>

                      {action.message && (
                        <p className="text-base text-white mb-3">{action.message}</p>
                      )}

                      {action.evidence && (
                        <p className="text-sm text-gray-400 mb-3">
                          <strong className="text-gray-300">Evidence:</strong> {action.evidence}
                        </p>
                      )}

                      {action.recommended_action && (
                        <p className="text-sm text-gray-400 mb-3">
                          <strong className="text-gray-300">Recommended:</strong> {action.recommended_action}
                        </p>
                      )}

                      {action.confidence && (
                        <div className="text-sm text-gray-400">
                          <strong className="text-gray-300">Confidence:</strong> {(action.confidence * 100).toFixed(0)}%
                        </div>
                      )}

                      {action.ticket_result && (
                        <div className="mt-3 text-sm">
                          <strong className="text-gray-300">ServiceNow Ticket:</strong>
                          {action.ticket_result.error ? (
                            <span className="text-red-400 ml-2">{action.ticket_result.error}</span>
                          ) : (
                            <span className="text-green-400 ml-2">Created successfully</span>
                          )}
                        </div>
                      )}

                      {action.task_result && (
                        <div className="mt-3 text-sm">
                          <strong className="text-gray-300">Jira Task:</strong>
                          {action.task_result.error ? (
                            <span className="text-red-400 ml-2">{action.task_result.error}</span>
                          ) : (
                            <span className="text-green-400 ml-2">
                              Created for {action.task_result.assignee || 'team member'}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>
          </div>
        )}
      </motion.div>
    </div>
  )
}

