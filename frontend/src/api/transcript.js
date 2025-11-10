import apiClient from './client'

export const transcriptAPI = {
  // Get all available weeks from the database
  getWeeks: async () => {
    try {
      const response = await apiClient.get('/api/transcript/weeks')
      return response.data
    } catch (error) {
      console.error('Error fetching weeks:', error)
      throw error
    }
  },

  // Run transcript analysis for a specific week
  analyzeWeek: async (weekIdentifier) => {
    try {
      const response = await apiClient.post('/api/transcript/analyze', {
        week_identifier: weekIdentifier
      })
      return response.data
    } catch (error) {
      console.error('Error analyzing week:', error)
      throw error
    }
  }
}
