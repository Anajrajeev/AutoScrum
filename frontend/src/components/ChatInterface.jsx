import { useState, useRef, useEffect } from 'react'
import { Send, Bot, User } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

// Simple markdown renderer for basic formatting
const formatMessage = (text) => {
  if (!text) return ''
  
  // Split by newlines to preserve line breaks
  const lines = text.split('\n')
  
  return lines.map((line, lineIndex) => {
    // Handle bold text **text**
    let formattedLine = line
    const boldRegex = /\*\*(.+?)\*\*/g
    const parts = []
    let lastIndex = 0
    let match
    
    while ((match = boldRegex.exec(line)) !== null) {
      // Add text before the match
      if (match.index > lastIndex) {
        parts.push({ type: 'text', content: line.substring(lastIndex, match.index) })
      }
      // Add bold text
      parts.push({ type: 'bold', content: match[1] })
      lastIndex = match.index + match[0].length
    }
    
    // Add remaining text
    if (lastIndex < line.length) {
      parts.push({ type: 'text', content: line.substring(lastIndex) })
    }
    
    // If no bold formatting found, return as text
    if (parts.length === 0) {
      parts.push({ type: 'text', content: line })
    }
    
    return (
      <div key={lineIndex} className={lineIndex > 0 ? 'mt-2' : ''}>
        {parts.map((part, partIndex) => {
          if (part.type === 'bold') {
            return <strong key={partIndex} className="text-white font-semibold">{part.content}</strong>
          }
          return <span key={partIndex} className="text-gray-200">{part.content}</span>
        })}
      </div>
    )
  })
}

export const ChatInterface = ({ messages, onSendMessage, isLoading, title = "Clarification Chat" }) => {
  const [input, setInput] = useState('')
  const messagesEndRef = useRef(null)
  const messagesContainerRef = useRef(null)
  const isUserScrollingRef = useRef(false)
  const lastMessageCountRef = useRef(0)
  
  const scrollToBottom = (smooth = true) => {
    if (messagesEndRef.current && !isUserScrollingRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto' })
    }
  }
  
  // Track user scrolling
  useEffect(() => {
    const container = messagesContainerRef.current
    if (!container) return
    
    const handleScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = container
      const isNearBottom = scrollHeight - scrollTop - clientHeight < 100
      isUserScrollingRef.current = !isNearBottom
    }
    
    container.addEventListener('scroll', handleScroll)
    return () => container.removeEventListener('scroll', handleScroll)
  }, [])
  
  useEffect(() => {
    // Only auto-scroll when new messages are added (not on initial load)
    const newMessageCount = messages.length
    const previousCount = lastMessageCountRef.current
    
    if (newMessageCount > previousCount && previousCount > 0) {
      // New message added - scroll to bottom
      setTimeout(() => scrollToBottom(true), 100)
    }
    
    lastMessageCountRef.current = newMessageCount
  }, [messages])
  
  const handleSubmit = (e) => {
    e.preventDefault()
    if (input.trim() && !isLoading) {
      onSendMessage(input.trim())
      setInput('')
    }
  }
  
  return (
    <div className="glass-card p-8 flex flex-col h-full min-h-[600px]">
      {/* Header */}
      <div className="mb-6">
        <h3 className="text-2xl font-semibold text-white">{title}</h3>
        <p className="text-base text-gray-300 mt-2">
          Dynamic Agent
        </p>
      </div>
      
      {/* Messages */}
      <div ref={messagesContainerRef} className="flex-1 overflow-y-auto custom-scrollbar space-y-5 mb-6">
        <AnimatePresence>
          {messages.map((message, index) => (
            <motion.div
              key={index}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.3 }}
              className={`flex items-start gap-4 ${
                message.role === 'user' ? 'flex-row-reverse' : 'flex-row'
              }`}
            >
              {/* Avatar */}
              <div className={`flex-shrink-0 w-12 h-12 rounded-full flex items-center justify-center ${
                message.role === 'user' 
                  ? 'bg-gradient-to-br from-openai-blue to-openai-green' 
                  : 'bg-white/10'
              }`}>
                {message.role === 'user' ? (
                  <User className="w-6 h-6 text-white" />
                ) : (
                  <Bot className="w-6 h-6 text-openai-green" />
                )}
              </div>
              
              {/* Message Bubble */}
              <div className={`flex flex-col ${message.role === 'user' ? 'items-end' : 'items-start'}`}>
                <span className="text-sm text-gray-400 mb-2 font-medium">
                  {message.role === 'user' ? 'User' : 'Dynamic Agent'}
                </span>
                <div className={`${
                  message.role === 'user' ? 'chat-bubble-user' : 'chat-bubble-agent'
                } text-base whitespace-pre-wrap`}>
                  {message.role === 'assistant' ? formatMessage(message.content) : message.content}
                </div>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
        
        {isLoading && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex items-start gap-4"
          >
            <div className="w-12 h-12 rounded-full bg-white/10 flex items-center justify-center">
              <Bot className="w-6 h-6 text-openai-green" />
            </div>
            <div className="chat-bubble-agent">
              <div className="flex space-x-2">
                <div className="w-3 h-3 bg-openai-green rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                <div className="w-3 h-3 bg-openai-green rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                <div className="w-3 h-3 bg-openai-green rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
              </div>
            </div>
          </motion.div>
        )}
        
        <div ref={messagesEndRef} />
      </div>
      
      {/* Input */}
      <form onSubmit={handleSubmit} className="flex gap-3">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type your response..."
          disabled={isLoading}
          className="input-glass flex-1 text-base px-4 py-3"
        />
        <button
          type="submit"
          disabled={isLoading || !input.trim()}
          className="btn-primary flex items-center gap-2 px-5 py-3 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Send className="w-5 h-5" />
        </button>
      </form>
    </div>
  )
}

