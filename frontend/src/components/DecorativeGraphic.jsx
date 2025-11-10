import { motion } from 'framer-motion'

export const DecorativeGraphic = () => {
  return (
    <div className="relative w-full h-64 overflow-hidden rounded-2xl bg-gradient-to-br from-openai-blue/20 to-openai-green/20">
      {/* Animated Background */}
      <div className="absolute inset-0 bg-gradient-to-br from-openai-blue/10 via-transparent to-openai-green/10 animate-gradient" />
      
      {/* Floating Circles */}
      <motion.div
        animate={{
          y: [0, -20, 0],
          scale: [1, 1.1, 1],
        }}
        transition={{
          duration: 4,
          repeat: Infinity,
          ease: "easeInOut"
        }}
        className="absolute top-1/4 left-1/4 w-32 h-32 bg-openai-blue/30 rounded-full blur-3xl"
      />
      
      <motion.div
        animate={{
          y: [0, 20, 0],
          scale: [1, 0.9, 1],
        }}
        transition={{
          duration: 5,
          repeat: Infinity,
          ease: "easeInOut"
        }}
        className="absolute bottom-1/4 right-1/4 w-40 h-40 bg-openai-green/30 rounded-full blur-3xl"
      />
      
      {/* Center Shape */}
      <div className="absolute inset-0 flex items-center justify-center">
        <motion.div
          animate={{
            rotate: 360,
          }}
          transition={{
            duration: 20,
            repeat: Infinity,
            ease: "linear"
          }}
          className="w-48 h-48 rounded-3xl bg-gradient-to-br from-white/5 to-white/10 backdrop-blur-sm border border-white/10"
        />
      </div>
      
      {/* Grid Pattern */}
      <div className="absolute inset-0 opacity-10" style={{
        backgroundImage: `
          linear-gradient(to right, rgba(255,255,255,0.1) 1px, transparent 1px),
          linear-gradient(to bottom, rgba(255,255,255,0.1) 1px, transparent 1px)
        `,
        backgroundSize: '40px 40px'
      }} />
    </div>
  )
}

