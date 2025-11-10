import apiClient from './client'

export const queryAPI = {
  // Query the AI Scrum Master
  query: async (queryText, context = null) => {
    const response = await apiClient.post('/api/query/', {
      query: queryText,
      context,
    })
    return response.data
  },

  // Prioritize stories
  prioritize: async (stories, teamId = null) => {
    const response = await apiClient.post('/api/query/prioritize', {
      stories,
      team_id: teamId,
    })
    return response.data
  },

  // Get conversation history
  getConversation: async (sessionId) => {
    const response = await apiClient.get(`/api/query/conversation/${sessionId}`)
    return response.data
  },

  // List workflows
  listWorkflows: async () => {
    const response = await apiClient.get('/api/query/workflows')
    return response.data
  },
}

