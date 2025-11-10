import { useState } from 'react'
import { FileText } from 'lucide-react'
import { motion } from 'framer-motion'

export const FeatureInput = ({ onSubmit, isLoading }) => {
  const [featureName, setFeatureName] = useState('')
  const [description, setDescription] = useState('')
  
  const handleSubmit = (e) => {
    e.preventDefault()
    if (featureName.trim() && description.trim() && !isLoading) {
      onSubmit({ name: featureName.trim(), description: description.trim() })
    }
  }
  
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card p-8"
    >
      <div className="flex items-center gap-4 mb-6">
        <div className="w-12 h-12 bg-gradient-to-br from-openai-blue to-openai-green rounded-lg flex items-center justify-center">
          <FileText className="w-6 h-6 text-white" />
        </div>
        <div>
          <h3 className="text-xl font-semibold text-white">Feature Details</h3>
          <p className="text-base text-gray-300">Describe your new feature</p>
        </div>
      </div>
      
      <form onSubmit={handleSubmit} className="space-y-6">
        <div>
          <label className="block text-base font-medium text-gray-300 mb-3">
            Feature Name
          </label>
          <input
            type="text"
            value={featureName}
            onChange={(e) => setFeatureName(e.target.value)}
            placeholder="E.g., User Authentication"
            disabled={isLoading}
            className="input-glass text-base px-4 py-3"
            required
          />
        </div>
        
        <div>
          <label className="block text-base font-medium text-gray-300 mb-3">
            Description
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe the new feature in plain language..."
            disabled={isLoading}
            rows={6}
            className="input-glass text-base px-4 py-3 resize-none"
            required
          />
        </div>
        
        <button
          type="submit"
          disabled={isLoading || !featureName.trim() || !description.trim()}
          className="btn-primary w-full px-6 py-4 text-base disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isLoading ? 'Starting Clarification...' : 'Start Clarification'}
        </button>
      </form>
    </motion.div>
  )
}

