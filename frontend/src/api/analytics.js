import apiClient from './client'

export const analyticsAPI = {
  // Get sprint analytics
  getSprintAnalytics: async (sprintId) => {
    const response = await apiClient.get(`/api/analytics/sprint/${sprintId}`)
    return response.data
  },

  // List sprints
  listSprints: async (skip = 0, limit = 100) => {
    const response = await apiClient.get('/api/analytics/sprints', {
      params: { skip, limit }
    })
    return response.data
  },

  // Create sprint
  createSprint: async (data) => {
    const response = await apiClient.post('/api/analytics/sprints', data)
    return response.data
  },

  // Get sentiment logs
  getSentimentLogs: async (sprintId = null, limit = 50) => {
    const params = { limit }
    if (sprintId) params.sprint_id = sprintId
    
    const response = await apiClient.get('/api/analytics/sentiment/logs', { params })
    return response.data
  },

  // Get agent logs
  getAgentLogs: async (agentName = null, limit = 100) => {
    const params = { limit }
    if (agentName) params.agent_name = agentName
    
    const response = await apiClient.get('/api/analytics/agent-logs', { params })
    return response.data
  },

  // Get dashboard data
  getDashboard: async () => {
    const response = await apiClient.get('/api/analytics/dashboard')
    return response.data
  },

  // Get team health
  getTeamHealth: async () => {
    const response = await apiClient.get('/api/analytics/team-health')
    return response.data
  },
}

