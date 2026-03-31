import React, { useState, useEffect } from 'react'
import './ContentStrategy.css'
import fetchDebug from '../lib/fetchDebug'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function ContentStrategy({ projectId, runId, onConfirmed, onCancel }) {
  const [cadence, setCadence] = useState('2') // articles per week
  const [strategy, setStrategy] = useState(null)
  const [budget, setBudget] = useState('standard') // budget tier
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const cadenceOptions = [
    { value: '1', label: '1 article/week', totalWeeks: 24, totalArticles: 24 },
    { value: '2', label: '2 articles/week', totalWeeks: 12, totalArticles: 24 },
    { value: '3', label: '3 articles/week', totalWeeks: 8, totalArticles: 24 },
    { value: '4', label: '4 articles/week', totalWeeks: 6, totalArticles: 24 },
    { value: 'custom', label: 'Custom', totalWeeks: null, totalArticles: null }
  ]

  const budgetTiers = [
    {
      value: 'basic',
      label: 'Basic',
      description: 'Cost-effective content',
      pricePerArticle: 150,
      features: ['1,500 word articles', 'Basic SEO optimization', 'AI-generated']
    },
    {
      value: 'standard',
      label: 'Standard',
      description: 'Balanced quality & cost',
      pricePerArticle: 300,
      features: ['2,500 word articles', 'Advanced SEO', 'Expert review', 'Fact-checked']
    },
    {
      value: 'premium',
      label: 'Premium',
      description: 'High-quality content',
      pricePerArticle: 600,
      features: ['4,000 word articles', 'Premium SEO', 'Human writer', 'Industry expert review']
    }
  ]

  const selected = cadenceOptions.find(o => o.value === cadence)
  const selectedBudget = budgetTiers.find(b => b.value === budget)
  const totalCost = selected?.totalArticles ? selected.totalArticles * selectedBudget.pricePerArticle : 0

  const handleConfirm = async () => {
    if (!selected?.totalArticles) {
      setError('Please select or set number of articles')
      return
    }

    try {
      setSubmitting(true)
      const payload = {
        cadence: cadence,
        budget_tier: budget,
        total_articles: selected.totalArticles,
        articles_per_week: parseInt(cadence),
        total_weeks: selected.totalWeeks,
        estimated_cost: totalCost,
        confirmed_by: 'customer'
      }

      const endpoint = runId
        ? `${API}/api/runs/${runId}/content-strategy`
        : `${API}/api/projects/${projectId}/content-strategy`

      const { res, parsed } = await fetchDebug(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })

      if (!res.ok) {
        throw new Error(parsed?.detail || 'Strategy confirmation failed')
      }

      setSuccess('Content strategy confirmed!')
      setTimeout(() => onConfirmed(payload), 500)
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="confirmation-modal">
      <div className="modal-header">
        <h2>📊 Content Strategy & Pricing</h2>
        <p>Choose your content cadence and quality tier. We'll show you the cost and timeline.</p>
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
        {/* Publishing Cadence */}
        <div style={{ marginBottom: '24px' }}>
          <h3 style={{ fontSize: '16px', fontWeight: 'bold', marginBottom: '12px' }}>
            📅 Publishing Cadence
          </h3>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
            gap: '8px'
          }}>
            {cadenceOptions.map(option => (
              <button
                key={option.value}
                onClick={() => setCadence(option.value)}
                style={{
                  padding: '12px',
                  border: cadence === option.value ? '2px solid #007bff' : '1px solid #ddd',
                  background: cadence === option.value ? '#f0f7ff' : 'white',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontSize: '14px',
                  fontWeight: cadence === option.value ? 'bold' : 'normal',
                  color: cadence === option.value ? '#007bff' : '#555'
                }}
              >
                <div>{option.label}</div>
                {option.totalWeeks && (
                  <div style={{ fontSize: '11px', color: '#999', marginTop: '4px' }}>
                    {option.totalWeeks} weeks
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Budget Tier Selection */}
        <div style={{ marginBottom: '24px' }}>
          <h3 style={{ fontSize: '16px', fontWeight: 'bold', marginBottom: '12px' }}>
            💰 Content Quality Tier
          </h3>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: '12px'
          }}>
            {budgetTiers.map(tier => (
              <button
                key={tier.value}
                onClick={() => setBudget(tier.value)}
                style={{
                  padding: '16px',
                  border: budget === tier.value ? '2px solid #28a745' : '1px solid #ddd',
                  background: budget === tier.value ? '#f1f8f4' : 'white',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'all 0.2s'
                }}
              >
                <div style={{ fontWeight: 'bold', fontSize: '14px', marginBottom: '4px' }}>
                  {tier.label}
                </div>
                <div style={{ fontSize: '12px', color: '#666', marginBottom: '8px' }}>
                  {tier.description}
                </div>
                <div style={{
                  fontSize: '13px',
                  fontWeight: 'bold',
                  color: '#28a745',
                  marginBottom: '8px'
                }}>
                  ${tier.pricePerArticle}/article
                </div>
                <div style={{ fontSize: '11px', color: '#999' }}>
                  {tier.features.map((f, i) => (
                    <div key={i}>✓ {f}</div>
                  ))}
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Cost Summary */}
        {selected && selectedBudget && (
          <div style={{
            background: '#f0f7ff',
            border: '2px solid #007bff',
            borderRadius: '4px',
            padding: '16px',
            marginBottom: '16px'
          }}>
            <h3 style={{ fontSize: '15px', fontWeight: 'bold', marginBottom: '12px' }}>
              📈 Project Summary
            </h3>
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(2, 1fr)',
              gap: '12px',
              marginBottom: '12px'
            }}>
              <div>
                <div style={{ fontSize: '12px', color: '#666' }}>Total Articles</div>
                <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#007bff' }}>
                  {selected.totalArticles}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '12px', color: '#666' }}>Timeline</div>
                <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#007bff' }}>
                  {selected.totalWeeks} weeks
                </div>
              </div>
              <div>
                <div style={{ fontSize: '12px', color: '#666' }}>Cost per Article</div>
                <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#28a745' }}>
                  ${selectedBudget.pricePerArticle}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '12px', color: '#666' }}>Total Budget</div>
                <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#28a745' }}>
                  ${totalCost.toLocaleString()}
                </div>
              </div>
            </div>
            <div style={{
              background: 'white',
              padding: '12px',
              borderRadius: '4px',
              fontSize: '13px',
              color: '#555',
              lineHeight: '1.5'
            }}>
              <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>💡 What's Included:</div>
              <ul style={{ margin: 0, paddingLeft: '16px' }}>
                <li>Content generation for all {selected.totalArticles} articles</li>
                <li>{selectedBudget.label} quality tier: {selectedBudget.features[0]}</li>
                <li>Publication on your schedule over {selected.totalWeeks} weeks</li>
                <li>Internal linking optimization</li>
                <li>SEO technical implementation</li>
              </ul>
            </div>
          </div>
        )}

        <div style={{
          background: '#fff9e6',
          border: '1px solid #ffc107',
          borderRadius: '4px',
          padding: '12px',
          fontSize: '12px',
          color: '#856404',
          marginBottom: '16px'
        }}>
          ⚠️ <strong>Note:</strong> This is an estimate. Final pricing may vary based on complexity and revisions needed.
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
          {submitting ? 'Saving...' : `✓ Confirm & Proceed ($${totalCost.toLocaleString()})`}
        </button>
      </div>
    </div>
  )
}
