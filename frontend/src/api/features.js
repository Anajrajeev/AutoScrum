import apiClient from './client'

export const featuresAPI = {
  // Create a new feature
  create: async (data) => {
    const response = await apiClient.post('/api/features/create', data)
    return response.data
  },

  // Continue clarification conversation
  clarify: async (featureId, userResponse) => {
    const response = await apiClient.post('/api/features/clarify', {
      feature_id: featureId,
      user_response: userResponse,
    })
    return response.data
  },

  // Generate stories preview (without saving)
  generateStoriesPreview: async (featureId) => {
    const response = await apiClient.post(`/api/features/${featureId}/generate-stories-preview`)
    return response.data
  },

  // Generate prioritization preview
  prioritizePreview: async (featureId, stories) => {
    const response = await apiClient.post(`/api/features/${featureId}/prioritize-preview`, stories)
    return response.data
  },

  // Approve and create stories in Jira
  approveAndCreate: async (featureId, stories, prioritization, pushToJira = true) => {
    const response = await apiClient.post(`/api/features/${featureId}/approve-and-create`, {
      stories,
      prioritization,
      push_to_jira: pushToJira
    })
    return response.data
  },

  // Get feature by ID
  get: async (featureId) => {
    const response = await apiClient.get(`/api/features/${featureId}`)
    return response.data
  },

  // List all features
  list: async (skip = 0, limit = 100) => {
    const response = await apiClient.get('/api/features/', {
      params: { skip, limit }
    })
    return response.data
  },

  // Get feature stories
  getStories: async (featureId) => {
    const response = await apiClient.get(`/api/features/${featureId}/stories`)
    return response.data
  },
}

