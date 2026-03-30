import React, { useState, useEffect } from 'react'
import './FinalStrategyConfirmation.css'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function FinalStrategyConfirmation({ runId, onConfirmed, onCancel }) {
  const [strategy, setStrategy] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [expandedSections, setExpandedSections] = useState({
    overview: true,
    topArticle: true,
    contentCalendar: true,
    timeline: true
  })

  useEffect(() => {
    fetchStrategy()
  }, [runId])

  const fetchStrategy = async () => {
    try {
      setLoading(true)
      const response = await fetch(`${API}/api/runs/${runId}/gate-5`)
      if (!response.ok) throw new Error('Failed to load final strategy')
      const data = await response.json()
      setStrategy(data.strategy || {})
      setError('')
    } catch (err) {
      setError(err.message)
      setStrategy(null)
    } finally {
      setLoading(false)
    }
  }

  const toggleSection = (section) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }))
  }

  const handleConfirm = async () => {
    try {
      setSubmitting(true)
      const payload = {
        strategy: strategy,
        confirmed_by: 'customer',
        ready_for_generation: true,
        notes: ''
      }

      const response = await fetch(`${API}/api/runs/${runId}/gate-5`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })

      if (!response.ok) {
        const err = await response.json()
        throw new Error(err.detail || 'Confirmation failed')
      }

      setSuccess('Strategy confirmed! Ready for content generation.')
      setTimeout(() => onConfirmed(strategy), 500)
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="confirmation-modal">
        <div className="modal-header">
          <h2>Loading Final Strategy...</h2>
        </div>
        <div style={{ padding: '20px', textAlign: 'center' }}>Loading...</div>
      </div>
    )
  }

  if (!strategy) {
    return (
      <div className="confirmation-modal">
        <div className="modal-header">
          <h2>Final Strategy</h2>
        </div>
        <div style={{ padding: '20px', textAlign: 'center', color: '#c33' }}>
          ❌ {error || 'No strategy available'}
        </div>
      </div>
    )
  }

  return (
    <div className="confirmation-modal">
      <div className="modal-header">
        <h2>🎯 Final SEO Strategy</h2>
        <p>Review your complete SEO strategy and ranking plan. Once approved, content generation will begin.</p>
      </div>

      {error && (
        <div style={{
          margin: '16px',
          padding: '12px',
          background: '#fee',
          color: '#c33',
          borderRadius: '4px',
          fontSize: '14px'
        }}>
          ❌ {error}
        </div>
      )}

      {success && (
        <div style={{
          margin: '16px',
          padding: '12px',
          background: '#efe',
          color: '#3c3',
          borderRadius: '4px',
          fontSize: '14px'
        }}>
          ✓ {success}
        </div>
      )}

      <div className="modal-content" style={{ maxHeight: '400px', overflowY: 'auto' }}>
        {/* Overview Section */}
        <div style={{ marginBottom: '12px', border: '1px solid #ddd', borderRadius: '4px', overflow: 'hidden' }}>
          <div
            onClick={() => toggleSection('overview')}
            style={{
              padding: '12px',
              background: '#f5f5f5',
              cursor: 'pointer',
              fontWeight: 'bold',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}
          >
            <span>📊 Strategy Overview</span>
            <span>{expandedSections.overview ? '▼' : '▶'}</span>
          </div>
          {expandedSections.overview && (
            <div style={{ padding: '12px', background: 'white', fontSize: '13px' }}>
              <div style={{ marginBottom: '8px' }}>
                <div style={{ fontWeight: 'bold', marginBottom: '2px' }}>Target Ranking Position:</div>
                <div style={{ fontSize: '18px', color: '#007bff', fontWeight: 'bold' }}>
                  #{strategy.target_rank || '#1'}
                </div>
              </div>
              <div style={{ marginBottom: '8px' }}>
                <div style={{ fontWeight: 'bold', marginBottom: '2px' }}>Primary Keyword:</div>
                <div style={{ color: '#555' }}>{strategy.primary_keyword || 'N/A'}</div>
              </div>
              <div style={{ marginBottom: '8px' }}>
                <div style={{ fontWeight: 'bold', marginBottom: '2px' }}>Total Keywords Targeting:</div>
                <div style={{ color: '#555' }}>{strategy.total_keywords || '0'} keywords</div>
              </div>
              <div style={{ marginBottom: '8px' }}>
                <div style={{ fontWeight: 'bold', marginBottom: '2px' }}>Estimated Timeline:</div>
                <div style={{ color: '#555' }}>{strategy.timeline || '6-12 months'}</div>
              </div>
              <div style={{
                marginTop: '12px',
                padding: '8px',
                background: '#f0f7ff',
                borderRadius: '4px',
                borderLeft: '3px solid #007bff'
              }}>
                <div style={{ fontSize: '12px', color: '#555', lineHeight: '1.5' }}>
                  {strategy.overview || 'Comprehensive SEO strategy based on your domain analysis and keyword research.'}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Top Ranking Article */}
        <div style={{ marginBottom: '12px', border: '1px solid #ddd', borderRadius: '4px', overflow: 'hidden' }}>
          <div
            onClick={() => toggleSection('topArticle')}
            style={{
              padding: '12px',
              background: '#f5f5f5',
              cursor: 'pointer',
              fontWeight: 'bold',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}
          >
            <span>📝 #1 Ranking Article</span>
            <span>{expandedSections.topArticle ? '▼' : '▶'}</span>
          </div>
          {expandedSections.topArticle && (
            <div style={{ padding: '12px', background: 'white', fontSize: '13px' }}>
              <div style={{ marginBottom: '8px' }}>
                <div style={{ fontWeight: 'bold', marginBottom: '2px' }}>Title:</div>
                <div style={{ color: '#555', lineHeight: '1.4' }}>{strategy.top_article_title || 'N/A'}</div>
              </div>
              <div style={{ marginBottom: '8px' }}>
                <div style={{ fontWeight: 'bold', marginBottom: '2px' }}>Angle:</div>
                <div style={{ color: '#555' }}>{strategy.top_article_angle || 'N/A'}</div>
              </div>
              <div style={{
                marginTop: '12px',
                padding: '8px',
                background: '#fff9e6',
                borderRadius: '4px',
                borderLeft: '3px solid #ffc107',
                fontSize: '12px',
                color: '#555',
                lineHeight: '1.5'
              }}>
                {strategy.top_article_brief || 'This will be your cornerstone content targeting the primary keyword with the highest conversion potential.'}
              </div>
            </div>
          )}
        </div>

        {/* Content Calendar */}
        <div style={{ marginBottom: '12px', border: '1px solid #ddd', borderRadius: '4px', overflow: 'hidden' }}>
          <div
            onClick={() => toggleSection('contentCalendar')}
            style={{
              padding: '12px',
              background: '#f5f5f5',
              cursor: 'pointer',
              fontWeight: 'bold',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}
          >
            <span>📅 Content Calendar</span>
            <span>{expandedSections.contentCalendar ? '▼' : '▶'}</span>
          </div>
          {expandedSections.contentCalendar && (
            <div style={{ padding: '12px', background: 'white', fontSize: '13px' }}>
              <div style={{ marginBottom: '8px' }}>
                <div style={{ fontWeight: 'bold', marginBottom: '2px' }}>Publishing Cadence:</div>
                <div style={{ color: '#555' }}>{strategy.publishing_cadence || '2 articles per week'}</div>
              </div>
              <div style={{ marginBottom: '8px' }}>
                <div style={{ fontWeight: 'bold', marginBottom: '2px' }}>Total Articles Planned:</div>
                <div style={{ color: '#555' }}>{strategy.total_articles || '0'} articles</div>
              </div>
              <div style={{
                marginTop: '12px',
                padding: '8px',
                background: '#f0f7ff',
                borderRadius: '4px',
                borderLeft: '3px solid #17a2b8'
              }}>
                <div style={{ fontSize: '12px', color: '#555', lineHeight: '1.5' }}>
                  Content will be published on a consistent schedule to maintain momentum and boost rankings across all targeted keywords.
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Timeline */}
        <div style={{ marginBottom: '12px', border: '1px solid #ddd', borderRadius: '4px', overflow: 'hidden' }}>
          <div
            onClick={() => toggleSection('timeline')}
            style={{
              padding: '12px',
              background: '#f5f5f5',
              cursor: 'pointer',
              fontWeight: 'bold',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}
          >
            <span>⏱️ Expected Timeline</span>
            <span>{expandedSections.timeline ? '▼' : '▶'}</span>
          </div>
          {expandedSections.timeline && (
            <div style={{ padding: '12px', background: 'white', fontSize: '13px' }}>
              <div style={{ marginBottom: '12px' }}>
                <div style={{ fontWeight: 'bold', marginBottom: '2px', color: '#28a745' }}>Phase 1: Foundation (Weeks 1-4)</div>
                <div style={{ color: '#666', fontSize: '12px' }}>Publish cornerstone content and pillar pages targeting high-value keywords</div>
              </div>
              <div style={{ marginBottom: '12px' }}>
                <div style={{ fontWeight: 'bold', marginBottom: '2px', color: '#007bff' }}>Phase 2: Expansion (Weeks 5-12)</div>
                <div style={{ color: '#666', fontSize: '12px' }}>Build supporting content and internal linking structure</div>
              </div>
              <div style={{ marginBottom: '12px' }}>
                <div style={{ fontWeight: 'bold', marginBottom: '2px', color: '#17a2b8' }}>Phase 3: Authority (Weeks 13+)</div>
                <div style={{ color: '#666', fontSize: '12px' }}>Establish domain authority and monitor rankings for adjustments</div>
              </div>
            </div>
          )}
        </div>

        <div style={{
          marginTop: '16px',
          padding: '12px',
          background: '#f9f9f9',
          borderRadius: '4px',
          fontSize: '12px',
          color: '#666',
          borderLeft: '3px solid #6c757d'
        }}>
          <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>⚡ Next Steps:</div>
          <ul style={{ margin: '4px 0', paddingLeft: '16px' }}>
            <li>Confirm this strategy to authorize content generation</li>
            <li>Content will be generated according to the calendar schedule</li>
            <li>Track rankings and ROI in your analytics dashboard</li>
          </ul>
        </div>
      </div>

      <div className="modal-footer">
        <button
          onClick={onCancel}
          style={{
            padding: '10px 20px',
            background: '#ccc',
            color: '#333',
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer',
            fontSize: '14px',
            fontWeight: 'bold'
          }}
        >
          Cancel
        </button>
        <button
          onClick={handleConfirm}
          disabled={submitting}
          style={{
            padding: '10px 20px',
            background: '#28a745',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer',
            fontSize: '14px',
            fontWeight: 'bold',
            opacity: submitting ? 0.7 : 1
          }}
        >
          {submitting ? 'Confirming...' : '✓ Approve & Generate Content'}
        </button>
      </div>
    </div>
  )
}
