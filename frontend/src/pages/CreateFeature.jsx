import { useState, useEffect } from 'react'
import { Sparkles } from 'lucide-react'
import { motion } from 'framer-motion'
import { ChatInterface } from '../components/ChatInterface'
import { FeatureInput } from '../components/FeatureInput'
import { ContextSummary } from '../components/ContextSummary'
import { DecorativeGraphic } from '../components/DecorativeGraphic'
import { featuresAPI } from '../api'

export const CreateFeature = () => {
  const [step, setStep] = useState('input') // 'input', 'clarifying', 'complete', 'stories', 'prioritization', 'approval', 'success'
  const [featureId, setFeatureId] = useState(null)
  const [featureData, setFeatureData] = useState(null)
  const [messages, setMessages] = useState([])
  const [context, setContext] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isGeneratingStories, setIsGeneratingStories] = useState(false)
  const [stories, setStories] = useState([])
  const [prioritization, setPrioritization] = useState(null)
  const [isPrioritizing, setIsPrioritizing] = useState(false)
  const [creationResult, setCreationResult] = useState(null) // Store creation results
  const [errorMessage, setErrorMessage] = useState(null) // Store error messages
  
  const handleFeatureSubmit = async (data) => {
    setIsLoading(true)
    try {
      // Create feature
      const feature = await featuresAPI.create(data)
      setFeatureId(feature.id)
      setFeatureData(data)
      
      // Start clarification - add initial agent message with actual question from backend
      const firstQuestion = feature.first_question || "Hello! I'm here to help you refine your feature description. What are the key goals of this feature?"
      
      setMessages([
        {
          role: 'assistant',
          content: firstQuestion
        }
      ])
      
      setStep('clarifying')
    } catch (error) {
      console.error('Error creating feature:', error)
      setErrorMessage('Failed to create feature. Please try again.')
      setTimeout(() => setErrorMessage(null), 5000)
    } finally {
      setIsLoading(false)
    }
  }
  
  const handleSendMessage = async (message) => {
    // Add user message
    setMessages(prev => [...prev, { role: 'user', content: message }])
    setIsLoading(true)
    
    try {
      // Send to clarification endpoint
      const response = await featuresAPI.clarify(featureId, message)
      
      // Add agent response if not complete
      if (!response.is_complete && response.question) {
        setMessages(prev => [...prev, { role: 'assistant', content: response.question }])
      }
      
      // Update context
      if (response.context_summary) {
        setContext(response.context_summary)
      }
      
      // If complete, automatically generate stories
      if (response.is_complete) {
        setMessages(prev => [...prev, { 
          role: 'assistant', 
          content: "Perfect! I have all the information I need. Now let me generate user stories for you..."
        }])
        setStep('complete')
        
        // Auto-generate stories preview
        setTimeout(() => handleGenerateStories(), 1000)
      }
    } catch (error) {
      console.error('Error in clarification:', error)
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: "I'm sorry, I encountered an error. Please try again."
      }])
    } finally {
      setIsLoading(false)
    }
  }
  
  const handleGenerateStories = async () => {
    setIsGeneratingStories(true)
    try {
      // Generate stories preview
      const result = await featuresAPI.generateStoriesPreview(featureId)
      
      setStories(result.stories)
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: `Great! I've generated ${result.stories.length} user stories. Now let me assign them to the team based on their capacity and skills...`
      }])
      setStep('stories')
      
      // Auto-run prioritization
      setTimeout(() => handlePrioritization(result.stories), 1000)
    } catch (error) {
      console.error('Error generating stories:', error)
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: "I'm sorry, I encountered an error generating stories. Please try again."
      }])
    } finally {
      setIsGeneratingStories(false)
    }
  }
  
  const handlePrioritization = async (storiesToPrioritize) => {
    setIsPrioritizing(true)
    try {
      // Generate prioritization preview
      const result = await featuresAPI.prioritizePreview(featureId, storiesToPrioritize)
      
      setPrioritization(result.prioritization)
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: `Perfect! I've assigned all stories to team members. Please review the assignments below and approve to create them in Jira.`
      }])
      setStep('approval')
    } catch (error) {
      console.error('Error prioritizing stories:', error)
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: "I'm sorry, I encountered an error during prioritization. Please try again."
      }])
    } finally {
      setIsPrioritizing(false)
    }
  }
  
  const handleApproveAndCreate = async () => {
    setIsLoading(true)
    setCreationResult(null)
    setErrorMessage(null)
    try {
      const result = await featuresAPI.approveAndCreate(featureId, stories, prioritization, true)
      
      // Store creation results
      setCreationResult(result)
      setStep('success')
      
      // Add success message to chat
      const successCount = result.jira_results.filter(r => r.success).length
      const totalCount = result.stories.length
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: `✅ Successfully created ${successCount} out of ${totalCount} stories in Jira! ${successCount < totalCount ? 'Some stories failed to create - check the details below.' : ''}`
      }])
    } catch (error) {
      console.error('Error creating stories:', error)
      setErrorMessage('Failed to create stories in Jira. Please try again.')
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: "❌ I'm sorry, I encountered an error creating stories in Jira. Please try again."
      }])
    } finally {
      setIsLoading(false)
    }
  }
  
  // Prevent page scroll on mount
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [])
  
  return (
    <div className="min-h-screen p-6">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-5xl font-bold text-white mb-3">Create a New Feature</h1>
        <p className="text-xl text-gray-300">
          Describe your feature and let our AI assistant help you refine it
        </p>
      </div>
      
      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column - Feature Input / Context */}
        <div className="lg:col-span-1 space-y-6">
          {step === 'input' ? (
            <FeatureInput onSubmit={handleFeatureSubmit} isLoading={isLoading} />
          ) : (
            <>
              {/* Feature Info Card */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="glass-card p-8"
              >
                <h3 className="text-xl font-semibold text-white mb-3">
                  {featureData?.name}
                </h3>
                <p className="text-base text-gray-300">
                  {featureData?.description}
                </p>
              </motion.div>
              
              {/* Context Summary */}
              <ContextSummary context={context} isComplete={step === 'complete'} />
            </>
          )}
          
          {/* Decorative Graphic */}
          {step === 'input' && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.2 }}
            >
              <DecorativeGraphic />
            </motion.div>
          )}
          
          {/* Stories Preview */}
          {(step === 'stories' || step === 'approval') && stories.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="glass-card p-8"
            >
              <h3 className="text-xl font-semibold text-white mb-6">
                Generated Stories ({stories.length})
              </h3>
              <div className="space-y-4 max-h-96 overflow-y-auto">
                {stories.map((story, idx) => (
                  <div key={idx} className="bg-dark-800/50 p-5 rounded-lg border border-dark-700">
                    <h4 className="text-base font-semibold text-white mb-3">{story.title}</h4>
                    <p className="text-sm text-gray-400 mb-3">{story.description}</p>
                    <div className="flex items-center gap-4 text-sm">
                      <span className="text-openai-green font-medium">SP: {story.story_points}</span>
                      {prioritization && prioritization.assignments && (
                        <span className="text-green-400 font-medium">
                          Assigned: {prioritization.assignments.find(a => a.story_title === story.title)?.assignee || 'Unassigned'}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>
          )}
          
          {/* Approve Button */}
          {step === 'approval' && (
            <motion.button
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              onClick={handleApproveAndCreate}
              disabled={isLoading}
              className="btn-primary w-full flex items-center justify-center gap-3 px-6 py-4 text-base disabled:opacity-50"
            >
              <Sparkles className="w-6 h-6" />
              {isLoading ? 'Creating in Jira...' : 'Approve & Create in Jira'}
            </motion.button>
          )}

          {/* Success Results */}
          {step === 'success' && creationResult && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="glass-card p-8"
            >
              <div className="flex items-center gap-3 mb-6">
                <div className="w-12 h-12 bg-green-500/20 rounded-full flex items-center justify-center">
                  <span className="text-2xl">✅</span>
                </div>
                <div>
                  <h3 className="text-2xl font-semibold text-white">
                    Stories Created Successfully!
                  </h3>
                  <p className="text-sm text-gray-400">
                    {creationResult.jira_results.filter(r => r.success).length} out of {creationResult.stories.length} stories created in Jira
                  </p>
                </div>
              </div>

              <div className="space-y-4 max-h-96 overflow-y-auto custom-scrollbar">
                {creationResult.jira_results.map((result, idx) => {
                  // Match story by story_id from jira_results with id from stories
                  const story = creationResult.stories.find(s => s.id === result.story_id) || 
                               creationResult.stories[idx] || 
                               stories[idx]
                  return (
                    <div
                      key={result.story_id || idx}
                      className={`p-5 rounded-lg border ${
                        result.success
                          ? 'bg-green-500/10 border-green-500/30'
                          : 'bg-red-500/10 border-red-500/30'
                      }`}
                    >
                      <div className="flex items-start justify-between mb-2">
                        <h4 className="text-base font-semibold text-white flex-1">
                          {story?.title || `Story ${idx + 1}`}
                        </h4>
                        {result.success ? (
                          <span className="text-green-400 text-sm font-medium flex items-center gap-1">
                            <span>✓</span> Created
                          </span>
                        ) : (
                          <span className="text-red-400 text-sm font-medium flex items-center gap-1">
                            <span>✗</span> Failed
                          </span>
                        )}
                      </div>
                      
                      {result.success && result.jira_key && (
                        <div className="mt-3 space-y-2 text-sm">
                          <div className="flex items-center gap-2">
                            <span className="text-gray-400">Jira Key:</span>
                            <span className="text-openai-green font-mono font-semibold">
                              {result.jira_key}
                            </span>
                          </div>
                          {story?.assignee && (
                            <div className="flex items-center gap-2">
                              <span className="text-gray-400">Assigned to:</span>
                              <span className="text-green-400 font-medium">
                                {story.assignee}
                              </span>
                            </div>
                          )}
                          {story?.story_points && (
                            <div className="flex items-center gap-2">
                              <span className="text-gray-400">Story Points:</span>
                              <span className="text-openai-green font-medium">
                                {story.story_points}
                              </span>
                            </div>
                          )}
                        </div>
                      )}
                      
                      {!result.success && result.error && (
                        <div className="mt-3 text-sm text-red-400">
                          <span className="font-medium">Error:</span> {typeof result.error === 'string' ? result.error : JSON.stringify(result.error)}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>

              <div className="mt-6 flex gap-4">
                <button
                  onClick={() => window.location.href = '/'}
                  className="btn-primary flex-1 flex items-center justify-center gap-2 px-6 py-3"
                >
                  Go to Dashboard
                </button>
                <button
                  onClick={() => {
                    setStep('input')
                    setCreationResult(null)
                    setFeatureId(null)
                    setFeatureData(null)
                    setMessages([])
                    setStories([])
                    setPrioritization(null)
                  }}
                  className="btn-secondary flex-1 flex items-center justify-center gap-2 px-6 py-3"
                >
                  Create Another Feature
                </button>
              </div>
            </motion.div>
          )}

          {/* Error Message Banner */}
          {errorMessage && (
            <motion.div
              initial={{ opacity: 0, y: -20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="glass-card p-4 bg-red-500/20 border border-red-500/30"
            >
              <div className="flex items-center gap-3">
                <span className="text-2xl">❌</span>
                <p className="text-red-400 font-medium">{errorMessage}</p>
              </div>
            </motion.div>
          )}
        </div>
        
        {/* Right Column - Chat Interface */}
        <div className="lg:col-span-2">
          {step !== 'input' ? (
            <ChatInterface
              messages={messages}
              onSendMessage={handleSendMessage}
              isLoading={isLoading}
              title="Clarification Chat"
            />
          ) : (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="glass-card p-12 h-[600px] flex items-center justify-center"
            >
              <div className="text-center">
                <div className="w-20 h-20 mx-auto mb-6 bg-gradient-to-br from-openai-blue to-openai-green rounded-2xl flex items-center justify-center">
                  <Sparkles className="w-10 h-10 text-white" />
                </div>
                <h3 className="text-2xl font-semibold text-white mb-4">
                  Start Your Feature Journey
                </h3>
                <p className="text-lg text-gray-300 max-w-md mx-auto">
                  Fill in the feature details on the left to begin the AI-powered clarification process
                </p>
              </div>
            </motion.div>
          )}
        </div>
      </div>
    </div>
  )
}

