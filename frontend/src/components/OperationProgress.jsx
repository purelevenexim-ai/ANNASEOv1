import React, { useState, useEffect } from 'react'

/**
 * ProgressBar Component
 * Shows animated progress bar with spinner for long-running operations
 *
 * Props:
 *   - label: Text to show (e.g., "Running strategy processing")
 *   - progress: 0-100 (optional, shows determinate progress)
 *   - isRunning: boolean (shows spinner and activity)
 *   - estimatedSeconds: Estimated seconds remaining (optional)
 */
export default function ProgressBar({
  label = "Processing…",
  progress = null,
  isRunning = true,
  estimatedSeconds = null
}) {
  const [dots, setDots] = useState('')

  // Animated spinner dots
  useEffect(() => {
    if (!isRunning) {
      setDots('')
      return
    }
    const interval = setInterval(() => {
      setDots(prev => {
        if (prev.length >= 3) return ''
        return prev + '.'
      })
    }, 400)
    return () => clearInterval(interval)
  }, [isRunning])

  // Estimate progress if not provided but running
  const displayProgress = progress !== null ? progress : (isRunning ? 30 : 100)

  return (
    <div style={{
      padding: '16px',
      background: '#f8fafc',
      borderRadius: '8px',
      marginBottom: '16px',
      border: '1px solid #e2e8f0'
    }}>
      {/* Label with spinner */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        marginBottom: '12px',
        fontSize: '13px',
        fontWeight: 500,
        color: '#1e293b'
      }}>
        {isRunning && (
          <div style={{
            display: 'inline-block',
            width: '16px',
            height: '16px',
            borderRadius: '50%',
            border: '2px solid #e2e8f0',
            borderTopColor: '#3b82f6',
            animation: 'spin 1s linear infinite'
          }} />
        )}
        {!isRunning && (
          <span style={{ fontSize: '16px' }}>✓</span>
        )}
        <span>{label}{dots}</span>
      </div>

      {/* Progress bar */}
      <div style={{
        height: '6px',
        background: '#e2e8f0',
        borderRadius: '3px',
        overflow: 'hidden',
        marginBottom: estimatedSeconds ? '8px' : '0'
      }}>
        <div style={{
          height: '100%',
          width: `${displayProgress}%`,
          background: isRunning ? '#3b82f6' : '#10b981',
          transition: 'width 0.3s ease',
          borderRadius: '3px'
        }} />
      </div>

      {/* Progress percentage and estimated time */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        fontSize: '11px',
        color: '#64748b',
        marginTop: '6px'
      }}>
        <span>{displayProgress}%</span>
        {estimatedSeconds && (
          <span>
            ~{estimatedSeconds > 60
              ? Math.floor(estimatedSeconds / 60) + 'm ' + (estimatedSeconds % 60) + 's'
              : estimatedSeconds + 's'
            } remaining
          </span>
        )}
      </div>

      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  )
}
