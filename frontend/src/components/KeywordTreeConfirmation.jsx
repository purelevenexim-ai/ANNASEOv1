import React, { useState, useEffect } from 'react'
import './KeywordTreeConfirmation.css'
import fetchDebug from '../lib/fetchDebug'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function KeywordTreeConfirmation({ runId, onConfirmed, onCancel }) {
  const [clusters, setClusters] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [expandedClusters, setExpandedClusters] = useState({})
  const [draggedKeyword, setDraggedKeyword] = useState(null)

  useEffect(() => {
    fetchTree()
  }, [runId])

  const fetchTree = async () => {
    try {
      setLoading(true)
      const { res, parsed: data } = await fetchDebug(`${API}/api/runs/${runId}/gate-3`)
      if (!res.ok) throw new Error('Failed to load keyword tree')
      setClusters(data.clusters || [])
      setError('')
      // Expand all clusters by default
      const expanded = {}
      data.clusters.forEach((_, idx) => {
        expanded[idx] = true
      })
      setExpandedClusters(expanded)
    } catch (err) {
      setError(err.message)
      setClusters([])
    } finally {
      setLoading(false)
    }
  }

  const toggleCluster = (idx) => {
    setExpandedClusters(prev => ({
      ...prev,
      [idx]: !prev[idx]
    }))
  }

  const deleteCluster = (idx) => {
    if (confirm('Delete this cluster and all keywords in it?')) {
      setClusters(clusters.filter((_, i) => i !== idx))
      setSuccess('Cluster deleted')
      setTimeout(() => setSuccess(''), 3000)
    }
  }

  const deleteKeywordFromCluster = (clusterIdx, keywordIdx) => {
    const newClusters = [...clusters]
    newClusters[clusterIdx].keywords.splice(keywordIdx, 1)
    if (newClusters[clusterIdx].keywords.length === 0) {
      newClusters.splice(clusterIdx, 1)
      setSuccess('Keyword removed and empty cluster deleted')
    } else {
      setSuccess('Keyword removed')
    }
    setClusters(newClusters)
    setTimeout(() => setSuccess(''), 3000)
  }

  const moveKeyword = (fromClusterIdx, keywordIdx, toClusterIdx) => {
    if (fromClusterIdx === toClusterIdx) return

    const newClusters = [...clusters]
    const keyword = newClusters[fromClusterIdx].keywords[keywordIdx]
    
    // Remove from source
    newClusters[fromClusterIdx].keywords.splice(keywordIdx, 1)
    if (newClusters[fromClusterIdx].keywords.length === 0) {
      newClusters.splice(fromClusterIdx, 1)
    }
    
    // Add to destination
    newClusters[toClusterIdx].keywords.push(keyword)
    
    setClusters(newClusters)
    setSuccess('Keyword moved')
    setTimeout(() => setSuccess(''), 3000)
  }

  const handleConfirm = async () => {
    const totalKeywords = clusters.reduce((sum, c) => sum + c.keywords.length, 0)
    if (totalKeywords === 0) {
      setError('Must have at least one cluster with keywords')
      return
    }

    try {
      setSubmitting(true)
      const payload = {
        clusters: clusters,
        confirmed_by: 'customer',
        notes: ''
      }

      const { res, parsed } = await fetchDebug(`${API}/api/runs/${runId}/gate-3`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })

      if (!res.ok) {
        throw new Error(parsed?.detail || 'Confirmation failed')
      }

      setSuccess('Keyword tree confirmed!')
      setTimeout(() => onConfirmed(clusters), 500)
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
          <h2>Loading Keyword Tree...</h2>
        </div>
        <div style={{ padding: '20px', textAlign: 'center' }}>Loading...</div>
      </div>
    )
  }

  const totalKeywords = clusters.reduce((sum, c) => sum + c.keywords.length, 0)

  return (
    <div className="confirmation-modal">
      <div className="modal-header">
        <h2>🌳 Confirm Keyword Tree</h2>
        <p>Review and organize the keyword structure. Drag keywords between clusters to reorganize.</p>
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
        <div style={{ marginBottom: '16px', fontSize: '14px', color: '#666' }}>
          {clusters.length} clusters • {totalKeywords} keywords
        </div>

        <div style={{
          maxHeight: '350px',
          overflowY: 'auto',
          border: '1px solid #ddd',
          borderRadius: '4px',
          background: '#fafafa'
        }}>
          {clusters.map((cluster, clusterIdx) => (
            <div key={clusterIdx} style={{
              borderBottom: clusterIdx < clusters.length - 1 ? '1px solid #eee' : 'none',
              background: 'white',
              margin: '8px',
              borderRadius: '4px',
              overflow: 'hidden'
            }}>
              {/* Cluster Header */}
              <div style={{
                padding: '12px',
                background: '#f9f9f9',
                borderBottom: expandedClusters[clusterIdx] ? '1px solid #ddd' : 'none',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                cursor: 'pointer'
              }} onClick={() => toggleCluster(clusterIdx)}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 'bold', fontSize: '14px' }}>
                    {expandedClusters[clusterIdx] ? '▼' : '▶'} {cluster.cluster_name}
                  </div>
                  <div style={{ fontSize: '12px', color: '#666', marginTop: '2px' }}>
                    {cluster.keywords.length} keywords
                  </div>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    deleteCluster(clusterIdx)
                  }}
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
                  Delete
                </button>
              </div>

              {/* Keywords List */}
              {expandedClusters[clusterIdx] && (
                <div style={{ padding: '8px' }}>
                  {cluster.keywords.map((keyword, keywordIdx) => (
                    <div
                      key={keywordIdx}
                      draggable
                      onDragStart={() => setDraggedKeyword({ clusterIdx, keywordIdx, keyword })}
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={() => {
                        if (draggedKeyword && draggedKeyword.clusterIdx !== clusterIdx) {
                          moveKeyword(draggedKeyword.clusterIdx, draggedKeyword.keywordIdx, clusterIdx)
                        }
                        setDraggedKeyword(null)
                      }}
                      style={{
                        padding: '8px 12px',
                        background: '#f0f7ff',
                        border: '1px solid #cce5ff',
                        borderRadius: '4px',
                        marginBottom: '6px',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        cursor: 'move',
                        opacity: draggedKeyword?.keyword === keyword ? 0.5 : 1,
                        transition: 'opacity 0.2s'
                      }}
                    >
                      <div>
                        <div style={{ fontSize: '13px', fontWeight: '500' }}>{keyword}</div>
                        <div style={{ fontSize: '11px', color: '#666', marginTop: '2px' }}>
                          Drag to move to another cluster
                        </div>
                      </div>
                      <button
                        onClick={() => deleteKeywordFromCluster(clusterIdx, keywordIdx)}
                        style={{
                          padding: '4px 8px',
                          background: '#dc3545',
                          color: 'white',
                          border: 'none',
                          borderRadius: '3px',
                          cursor: 'pointer',
                          fontSize: '12px',
                          marginLeft: '8px'
                        }}
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
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
          disabled={submitting || clusters.length === 0}
          style={{
            padding: '10px 20px',
            background: clusters.length === 0 ? '#ccc' : '#28a745',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: clusters.length === 0 ? 'not-allowed' : 'pointer',
            fontSize: '14px',
            fontWeight: 'bold',
            opacity: submitting ? 0.7 : 1
          }}
        >
          {submitting ? 'Confirming...' : 'Confirm Tree'}
        </button>
      </div>
    </div>
  )
}
