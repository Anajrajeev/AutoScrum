import { useState } from 'react'
import { FileText, ChevronDown, ChevronUp, Check } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

export const ContextSummary = ({ context, isComplete }) => {
  const [isExpanded, setIsExpanded] = useState(false)
  
  if (!context) {
    return (
      <div className="glass-card p-8">
        <div className="text-center text-gray-300">
          <FileText className="w-16 h-16 mx-auto mb-4 opacity-50" />
          <p className="text-base">No context available yet</p>
          <p className="text-sm mt-2">Start the clarification to build context</p>
        </div>
      </div>
    )
  }
  
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className="glass-card p-8"
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <h3 className="text-xl font-semibold text-white">Context Summary</h3>
            {isComplete && (
              <div className="flex items-center gap-1 px-3 py-1 bg-green-500/20 text-green-400 text-sm rounded-full font-medium">
                <Check className="w-4 h-4" />
                <span>Complete</span>
              </div>
            )}
          </div>
          <p className="text-base text-gray-300">
            Auto-generated summary of the feature based on the conversation
          </p>
        </div>
        
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="btn-secondary py-3 px-5 text-base"
        >
          {isExpanded ? (
            <>
              <ChevronUp className="w-5 h-5 inline mr-2" />
              Collapse
            </>
          ) : (
            <>
              <ChevronDown className="w-5 h-5 inline mr-2" />
              View
            </>
          )}
        </button>
      </div>
      
      {/* Context Details */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3 }}
            className="space-y-4 mt-4 pt-4 border-t border-white/10"
          >
            {context.goals && context.goals.length > 0 && (
              <div>
                <h4 className="text-base font-semibold text-openai-green mb-3">Goals</h4>
                <ul className="space-y-2">
                  {context.goals.map((goal, index) => (
                    <li key={index} className="text-base text-gray-300 flex items-start gap-3">
                      <span className="text-openai-green mt-1 text-lg">•</span>
                      <span>{goal}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            
            {context.user_personas && context.user_personas.length > 0 && (
              <div>
                <h4 className="text-base font-semibold text-openai-green mb-3">User Personas</h4>
                <div className="flex flex-wrap gap-3">
                  {context.user_personas.map((persona, index) => (
                    <span key={index} className="px-4 py-2 bg-white/10 rounded-full text-sm text-gray-300 font-medium">
                      {persona}
                    </span>
                  ))}
                </div>
              </div>
            )}
            
            {context.key_features && context.key_features.length > 0 && (
              <div>
                <h4 className="text-base font-semibold text-openai-green mb-3">Key Features</h4>
                <ul className="space-y-2">
                  {context.key_features.map((feature, index) => (
                    <li key={index} className="text-base text-gray-300 flex items-start gap-3">
                      <span className="text-openai-green mt-1 text-lg">•</span>
                      <span>{feature}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            
            {context.acceptance_criteria && context.acceptance_criteria.length > 0 && (
              <div>
                <h4 className="text-base font-semibold text-openai-green mb-3">Acceptance Criteria</h4>
                <ul className="space-y-2">
                  {context.acceptance_criteria.map((criteria, index) => (
                    <li key={index} className="text-base text-gray-300 flex items-start gap-3">
                      <Check className="w-5 h-5 text-green-400 mt-0.5 flex-shrink-0" />
                      <span>{criteria}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            
            {context.technical_constraints && context.technical_constraints.length > 0 && (
              <div>
                <h4 className="text-base font-semibold text-openai-green mb-3">Technical Constraints</h4>
                <ul className="space-y-2">
                  {context.technical_constraints.map((constraint, index) => (
                    <li key={index} className="text-base text-gray-300 flex items-start gap-3">
                      <span className="text-openai-green mt-1 text-lg">•</span>
                      <span>{constraint}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            
            {context.success_metrics && context.success_metrics.length > 0 && (
              <div>
                <h4 className="text-base font-semibold text-openai-green mb-3">Success Metrics</h4>
                <ul className="space-y-2">
                  {context.success_metrics.map((metric, index) => (
                    <li key={index} className="text-base text-gray-300 flex items-start gap-3">
                      <span className="text-openai-green mt-1 text-lg">•</span>
                      <span>{metric}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

