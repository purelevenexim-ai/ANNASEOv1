import React, { useState, useEffect } from 'react'
import './BlogSuggestionsConfirmation.css'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function BlogSuggestionsConfirmation({ runId, onConfirmed, onCancel }) {
  const [articles, setArticles] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [selectedArticles, setSelectedArticles] = useState(new Set())
  const [expandedArticle, setExpandedArticle] = useState(null)

  useEffect(() => {
    fetchArticles()
  }, [runId])

  const fetchArticles = async () => {
    try {
      setLoading(true)
      const response = await fetch(`${API}/api/runs/${runId}/gate-4`)
      if (!response.ok) throw new Error('Failed to load blog suggestions')
      const data = await response.json()
      setArticles(data.articles || [])
      setSelectedArticles(new Set(data.articles.map((_, i) => i)))
      setError('')
    } catch (err) {
      setError(err.message)
      setArticles([])
    } finally {
      setLoading(false)
    }
  }

  const toggleArticle = (idx) => {
    const newSelected = new Set(selectedArticles)
    if (newSelected.has(idx)) {
      newSelected.delete(idx)
    } else {
      newSelected.add(idx)
    }
    setSelectedArticles(newSelected)
  }

  const toggleAll = () => {
    if (selectedArticles.size === articles.length) {
      setSelectedArticles(new Set())
    } else {
      setSelectedArticles(new Set(articles.map((_, i) => i)))
    }
  }

  const handleConfirm = async () => {
    if (selectedArticles.size === 0) {
      setError('Must select at least one article')
      return
    }

    try {
      setSubmitting(true)
      const confirmed = Array.from(selectedArticles).map(idx => articles[idx])
      const payload = {
        articles: confirmed,
        confirmed_by: 'customer',
        notes: ''
      }

      const response = await fetch(`${API}/api/runs/${runId}/gate-4`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })

      if (!response.ok) {
        const err = await response.json()
        throw new Error(err.detail || 'Confirmation failed')
      }

      setSuccess('Blog strategy confirmed!')
      setTimeout(() => onConfirmed(confirmed), 500)
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
          <h2>Loading Blog Suggestions...</h2>
        </div>
        <div style={{ padding: '20px', textAlign: 'center' }}>Loading...</div>
      </div>
    )
  }

  return (
    <div className="confirmation-modal">
      <div className="modal-header">
        <h2>📰 Confirm Blog Strategy</h2>
        <p>Review and approve the suggested article angles and titles. Select which articles to create.</p>
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

      <div className="modal-content">
        <div style={{ marginBottom: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '14px', color: '#666' }}>
            {selectedArticles.size} of {articles.length} selected
          </span>
          <button
            onClick={toggleAll}
            style={{
              padding: '6px 12px',
              background: '#17a2b8',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '13px'
            }}
          >
            {selectedArticles.size === articles.length ? 'Deselect All' : 'Select All'}
          </button>
        </div>

        <div style={{
          maxHeight: '350px',
          overflowY: 'auto',
          border: '1px solid #ddd',
          borderRadius: '4px'
        }}>
          {articles.map((article, idx) => (
            <div
              key={idx}
              style={{
                borderBottom: idx < articles.length - 1 ? '1px solid #eee' : 'none',
                background: selectedArticles.has(idx) ? '#f0f7ff' : 'white',
                padding: '12px',
                cursor: 'pointer',
                transition: 'background 0.2s'
              }}
              onClick={() => toggleArticle(idx)}
            >
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
                <input
                  type="checkbox"
                  checked={selectedArticles.has(idx)}
                  onChange={() => {}}
                  style={{
                    marginTop: '2px',
                    width: '16px',
                    height: '16px',
                    cursor: 'pointer'
                  }}
                  onClick={(e) => e.stopPropagation()}
                />
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 'bold', fontSize: '14px', marginBottom: '4px' }}>
                    {article.title}
                  </div>
                  <div style={{ fontSize: '13px', color: '#666', marginBottom: '8px' }}>
                    {article.angle}
                  </div>

                  {/* Expand for preview */}
                  {expandedArticle === idx && (
                    <div style={{
                      background: '#f9f9f9',
                      padding: '8px',
                      borderRadius: '4px',
                      fontSize: '13px',
                      color: '#555',
                      marginTop: '8px',
                      lineHeight: '1.5'
                    }}>
                      <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>Brief:</div>
                      <div>{article.brief}</div>
                      {article.target_keywords && (
                        <div style={{ marginTop: '8px' }}>
                          <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>Target Keywords:</div>
                          <div>{article.target_keywords.join(', ')}</div>
                        </div>
                      )}
                      {article.article_count && (
                        <div style={{ marginTop: '8px', fontSize: '12px', color: '#999' }}>
                          Estimated {article.article_count} existing articles
                        </div>
                      )}
                    </div>
                  )}

                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      setExpandedArticle(expandedArticle === idx ? null : idx)
                    }}
                    style={{
                      marginTop: '8px',
                      padding: '4px 8px',
                      background: expandedArticle === idx ? '#6c757d' : '#007bff',
                      color: 'white',
                      border: 'none',
                      borderRadius: '3px',
                      cursor: 'pointer',
                      fontSize: '12px'
                    }}
                  >
                    {expandedArticle === idx ? '▼ Hide Brief' : '▶ Show Brief'}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div style={{
          marginTop: '12px',
          padding: '8px',
          background: '#f9f9f9',
          borderRadius: '4px',
          fontSize: '12px',
          color: '#666'
        }}>
          💡 Tip: Click an article to see its full brief and target keywords
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
          disabled={submitting || selectedArticles.size === 0}
          style={{
            padding: '10px 20px',
            background: selectedArticles.size === 0 ? '#ccc' : '#28a745',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: selectedArticles.size === 0 ? 'not-allowed' : 'pointer',
            fontSize: '14px',
            fontWeight: 'bold',
            opacity: submitting ? 0.7 : 1
          }}
        >
          {submitting ? 'Confirming...' : `Confirm Strategy (${selectedArticles.size})`}
        </button>
      </div>
    </div>
  )
}
