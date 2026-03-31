import React, { useState, useEffect } from 'react'
import './UniverseConfirmation.css'
import fetchDebug from '../lib/fetchDebug'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function UniverseConfirmation({ runId, onConfirmed, onCancel }) {
  const [keywords, setKeywords] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [editValues, setEditValues] = useState({})
  const [showAddForm, setShowAddForm] = useState(false)
  const [newKeyword, setNewKeyword] = useState({
    keyword: '',
    intent: 'informational',
    priority: 'medium'
  })

  // Load existing keywords
  useEffect(() => {
    fetchKeywords()
  }, [runId])

  const fetchKeywords = async () => {
    try {
      setLoading(true)
      const { res, parsed: data } = await fetchDebug(`${API}/api/runs/${runId}/gate-1`)
      if (!res.ok) throw new Error('Failed to load keywords')
      setKeywords(data.keywords || [])
      setError('')
    } catch (err) {
      setError(err.message)
      setKeywords([])
    } finally {
      setLoading(false)
    }
  }

  const startEdit = (keyword) => {
    setEditingId(keyword.id)
    setEditValues(keyword)
  }

  const saveEdit = (id) => {
    setKeywords(keywords.map(k => k.id === id ? editValues : k))
    setEditingId(null)
    setEditValues({})
    setSuccess('Keyword updated')
    setTimeout(() => setSuccess(''), 3000)
  }

  const deleteKeyword = (id) => {
    if (confirm('Delete this keyword?')) {
      setKeywords(keywords.filter(k => k.id !== id))
      setSuccess('Keyword removed')
      setTimeout(() => setSuccess(''), 3000)
    }
  }

  const addKeyword = () => {
    if (!newKeyword.keyword.trim()) {
      setError('Keyword is required')
      return
    }
    const id = `new-${Date.now()}`
    setKeywords([...keywords, { id, ...newKeyword }])
    setNewKeyword({ keyword: '', intent: 'informational', priority: 'medium' })
    setShowAddForm(false)
    setSuccess('Keyword added')
    setTimeout(() => setSuccess(''), 3000)
  }

  const handleConfirm = async () => {
    if (keywords.length === 0) {
      setError('Must have at least one keyword')
      return
    }

    try {
      setSubmitting(true)
      const payload = {
        keywords: keywords,
        confirmed_by: 'customer',
        notes: ''
      }

      const { res, parsed } = await fetchDebug(`${API}/api/runs/${runId}/gate-1`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })

      if (!res.ok) {
        throw new Error(parsed?.detail || 'Confirmation failed')
      }

      setSuccess('Keywords confirmed!')
      setTimeout(() => onConfirmed(keywords), 500)
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
          <h2>Loading Keywords...</h2>
        </div>
        <div style={{ padding: '20px', textAlign: 'center' }}>Loading...</div>
      </div>
    )
  }

  return (
    <div className="confirmation-modal">
      <div className="modal-header">
        <h2>🔍 Confirm Universe Keywords</h2>
        <p>Review and confirm the initial keyword universe generated from your seed keywords</p>
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
            {keywords.length} keywords selected
          </span>
          {!showAddForm && (
            <button
              onClick={() => setShowAddForm(true)}
              style={{
                padding: '8px 16px',
                background: '#007bff',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '14px'
              }}
            >
              + Add Keyword
            </button>
          )}
        </div>

        {showAddForm && (
          <div style={{
            padding: '12px',
            background: '#f9f9f9',
            border: '1px solid #ddd',
            borderRadius: '4px',
            marginBottom: '12px'
          }}>
            <div style={{ marginBottom: '8px' }}>
              <label style={{ display: 'block', marginBottom: '4px', fontSize: '13px', fontWeight: 'bold' }}>
                Keyword
              </label>
              <input
                type="text"
                value={newKeyword.keyword}
                onChange={(e) => setNewKeyword({ ...newKeyword, keyword: e.target.value })}
                placeholder="e.g., keyword research tools"
                style={{
                  width: '100%',
                  padding: '8px',
                  border: '1px solid #ddd',
                  borderRadius: '4px',
                  boxSizing: 'border-box',
                  fontSize: '13px'
                }}
              />
            </div>

            <div style={{ marginBottom: '8px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
              <div>
                <label style={{ display: 'block', marginBottom: '4px', fontSize: '13px', fontWeight: 'bold' }}>
                  Intent
                </label>
                <select
                  value={newKeyword.intent}
                  onChange={(e) => setNewKeyword({ ...newKeyword, intent: e.target.value })}
                  style={{
                    width: '100%',
                    padding: '8px',
                    border: '1px solid #ddd',
                    borderRadius: '4px',
                    fontSize: '13px'
                  }}
                >
                  <option>informational</option>
                  <option>commercial</option>
                  <option>transactional</option>
                  <option>navigational</option>
                </select>
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: '4px', fontSize: '13px', fontWeight: 'bold' }}>
                  Priority
                </label>
                <select
                  value={newKeyword.priority}
                  onChange={(e) => setNewKeyword({ ...newKeyword, priority: e.target.value })}
                  style={{
                    width: '100%',
                    padding: '8px',
                    border: '1px solid #ddd',
                    borderRadius: '4px',
                    fontSize: '13px'
                  }}
                >
                  <option>low</option>
                  <option>medium</option>
                  <option>high</option>
                </select>
              </div>
            </div>

            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                onClick={addKeyword}
                style={{
                  flex: 1,
                  padding: '8px',
                  background: '#28a745',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontSize: '13px'
                }}
              >
                Add
              </button>
              <button
                onClick={() => setShowAddForm(false)}
                style={{
                  flex: 1,
                  padding: '8px',
                  background: '#ccc',
                  color: '#333',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontSize: '13px'
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        <div style={{
          maxHeight: '300px',
          overflowY: 'auto',
          border: '1px solid #ddd',
          borderRadius: '4px'
        }}>
          <table style={{
            width: '100%',
            borderCollapse: 'collapse',
            fontSize: '13px'
          }}>
            <thead>
              <tr style={{ background: '#f5f5f5', borderBottom: '1px solid #ddd' }}>
                <th style={{ padding: '8px', textAlign: 'left' }}>Keyword</th>
                <th style={{ padding: '8px', textAlign: 'left' }}>Intent</th>
                <th style={{ padding: '8px', textAlign: 'left' }}>Priority</th>
                <th style={{ padding: '8px', textAlign: 'center', width: '100px' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {keywords.map((kw) => (
                <tr key={kw.id} style={{ borderBottom: '1px solid #eee' }}>
                  {editingId === kw.id ? (
                    <>
                      <td style={{ padding: '8px' }}>
                        <input
                          type="text"
                          value={editValues.keyword}
                          onChange={(e) => setEditValues({ ...editValues, keyword: e.target.value })}
                          style={{
                            width: '100%',
                            padding: '4px',
                            border: '1px solid #ddd',
                            borderRadius: '3px',
                            boxSizing: 'border-box'
                          }}
                        />
                      </td>
                      <td style={{ padding: '8px' }}>
                        <select
                          value={editValues.intent}
                          onChange={(e) => setEditValues({ ...editValues, intent: e.target.value })}
                          style={{
                            width: '100%',
                            padding: '4px',
                            border: '1px solid #ddd',
                            borderRadius: '3px'
                          }}
                        >
                          <option>informational</option>
                          <option>commercial</option>
                          <option>transactional</option>
                          <option>navigational</option>
                        </select>
                      </td>
                      <td style={{ padding: '8px' }}>
                        <select
                          value={editValues.priority}
                          onChange={(e) => setEditValues({ ...editValues, priority: e.target.value })}
                          style={{
                            width: '100%',
                            padding: '4px',
                            border: '1px solid #ddd',
                            borderRadius: '3px'
                          }}
                        >
                          <option>low</option>
                          <option>medium</option>
                          <option>high</option>
                        </select>
                      </td>
                      <td style={{ padding: '8px', textAlign: 'center' }}>
                        <button
                          onClick={() => saveEdit(kw.id)}
                          style={{
                            padding: '4px 8px',
                            background: '#28a745',
                            color: 'white',
                            border: 'none',
                            borderRadius: '3px',
                            cursor: 'pointer',
                            fontSize: '12px',
                            marginRight: '4px'
                          }}
                        >
                          ✓
                        </button>
                        <button
                          onClick={() => setEditingId(null)}
                          style={{
                            padding: '4px 8px',
                            background: '#ccc',
                            color: '#333',
                            border: 'none',
                            borderRadius: '3px',
                            cursor: 'pointer',
                            fontSize: '12px'
                          }}
                        >
                          ✕
                        </button>
                      </td>
                    </>
                  ) : (
                    <>
                      <td style={{ padding: '8px' }}>{kw.keyword}</td>
                      <td style={{ padding: '8px' }}>
                        <span style={{
                          display: 'inline-block',
                          padding: '2px 6px',
                          background: '#f0f0f0',
                          borderRadius: '3px',
                          fontSize: '12px'
                        }}>
                          {kw.intent}
                        </span>
                      </td>
                      <td style={{ padding: '8px' }}>
                        <span style={{
                          display: 'inline-block',
                          padding: '2px 6px',
                          background: kw.priority === 'high' ? '#ffebee' : kw.priority === 'medium' ? '#fff3e0' : '#f1f8e9',
                          color: kw.priority === 'high' ? '#c62828' : kw.priority === 'medium' ? '#e65100' : '#558b2f',
                          borderRadius: '3px',
                          fontSize: '12px'
                        }}>
                          {kw.priority}
                        </span>
                      </td>
                      <td style={{ padding: '8px', textAlign: 'center' }}>
                        <button
                          onClick={() => startEdit(kw)}
                          style={{
                            padding: '4px 8px',
                            background: '#007bff',
                            color: 'white',
                            border: 'none',
                            borderRadius: '3px',
                            cursor: 'pointer',
                            fontSize: '12px',
                            marginRight: '4px'
                          }}
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => deleteKeyword(kw.id)}
                          style={{
                            padding: '4px 8px',
                            background: '#dc3545',
                            color: 'white',
                            border: 'none',
                            borderRadius: '3px',
                            cursor: 'pointer',
                            fontSize: '12px'
                          }}
                        >
                          ✕
                        </button>
                      </td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
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
          disabled={submitting || keywords.length === 0}
          style={{
            padding: '10px 20px',
            background: keywords.length === 0 ? '#ccc' : '#28a745',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: keywords.length === 0 ? 'not-allowed' : 'pointer',
            fontSize: '14px',
            fontWeight: 'bold',
            opacity: submitting ? 0.7 : 1
          }}
        >
          {submitting ? 'Confirming...' : 'Confirm Keywords'}
        </button>
      </div>
    </div>
  )
}
