/**
 * BlueprintCard — Display a single Strategy V2 content blueprint.
 * 
 * Shows:
 *  - Angle type badge (color-coded)
 *  - QA score bars (SEO, AEO, Conversion, Depth)
 *  - Title + Hook preview
 *  - Section list
 *  - Expandable detail (story + CTA + gaps/fixes)
 *  - "Generate Content" CTA
 */
import React, { useState } from 'react'

const API = import.meta.env.VITE_API_URL || ''

const ANGLE_COLORS = {
  contrarian:         { bg: '#fee2e2', text: '#dc2626', label: 'Contrarian' },
  mistake:            { bg: '#fff7ed', text: '#ea580c', label: 'Mistake Avoidance' },
  comparison:         { bg: '#eff6ff', text: '#2563eb', label: 'Comparison' },
  decision_framework: { bg: '#f0fdf4', text: '#16a34a', label: 'Decision Framework' },
  hidden_truth:       { bg: '#faf5ff', text: '#9333ea', label: 'Hidden Truth' },
  informational:      { bg: '#f1f5f9', text: '#475569', label: 'Informational' },
}

function ScoreBar({ label, value, color }) {
  const pct = Math.min(100, Math.max(0, value || 0))
  const barColor = pct >= 80 ? '#16a34a' : pct >= 60 ? '#d97706' : '#dc2626'
  return (
    <div style={{ marginBottom: 4 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#64748b', marginBottom: 2 }}>
        <span>{label}</span>
        <span style={{ fontWeight: 600, color: barColor }}>{pct}</span>
      </div>
      <div style={{ height: 6, background: '#e2e8f0', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: barColor, borderRadius: 3, transition: 'width 0.4s ease' }} />
      </div>
    </div>
  )
}

function OverallBadge({ score }) {
  const color = score >= 80 ? '#16a34a' : score >= 65 ? '#d97706' : '#dc2626'
  const bg = score >= 80 ? '#f0fdf4' : score >= 65 ? '#fff7ed' : '#fee2e2'
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      background: bg, color, border: `1.5px solid ${color}20`,
      borderRadius: 20, padding: '2px 10px', fontSize: 13, fontWeight: 700,
    }}>
      {score}
    </div>
  )
}

export default function BlueprintCard({ blueprint, projectId, onContentStarted, setPage }) {
  const [expanded, setExpanded] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [genError, setGenError] = useState('')
  const [genDone, setGenDone] = useState(false)
  const [articleId, setArticleId] = useState(blueprint.content_article_id || '')

  const angleStyle = ANGLE_COLORS[blueprint.angle_type] || ANGLE_COLORS.informational
  const qa = blueprint.qa_score || {}
  const overallScore = qa.overall ?? blueprint.qa_overall_score ?? 0
  const seoScore     = qa.seo ?? blueprint.qa_seo_score ?? 0
  const aeoScore     = qa.aeo ?? blueprint.qa_aeo_score ?? 0
  const convScore    = qa.conversion ?? blueprint.qa_conversion_score ?? 0
  const depthScore   = qa.depth ?? blueprint.qa_depth_score ?? 0

  const hookText = typeof blueprint.hook === 'string'
    ? blueprint.hook
    : blueprint.hook?.text || ''

  const sections = blueprint.sections || []
  const story = typeof blueprint.story === 'string'
    ? blueprint.story
    : blueprint.story?.scenario || ''

  const ctaText = typeof blueprint.cta === 'string'
    ? blueprint.cta
    : blueprint.cta?.text || ''

  const gaps = blueprint.qa_gaps || qa.gaps || []
  const fixes = blueprint.qa_fixes || qa.fixes || []

  const handleGenerateContent = async () => {
    setGenerating(true)
    setGenError('')
    try {
      const token = localStorage.getItem('annaseo_token') || ''
      const resp = await fetch(`${API}/api/strategy-v2/${projectId}/blueprints/${blueprint.id}/to-content`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ word_count: 2200, page_type: 'article', ai_routing_preset: 'A' }),
      })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      setGenDone(true)
      if (data.article_id) setArticleId(data.article_id)
      if (onContentStarted) onContentStarted(data)
    } catch (e) {
      setGenError(e.message)
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div style={{
      background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12,
      padding: '18px 20px', boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
      display: 'flex', flexDirection: 'column', gap: 12,
    }}>
      {/* Header row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <span style={{
            display: 'inline-block', fontSize: 11, fontWeight: 600, padding: '2px 8px',
            borderRadius: 12, background: angleStyle.bg, color: angleStyle.text,
            marginBottom: 6, letterSpacing: 0.3,
          }}>
            {angleStyle.label}
          </span>
          <div style={{ fontWeight: 700, fontSize: 15, lineHeight: 1.4, color: '#0f172a' }}>
            {blueprint.title}
          </div>
        </div>
        <OverallBadge score={overallScore} />
      </div>

      {/* Hook preview */}
      {hookText && (
        <div style={{
          fontStyle: 'italic', fontSize: 13, color: '#475569', lineHeight: 1.5,
          borderLeft: '3px solid #e2e8f0', paddingLeft: 10,
        }}>
          "{hookText.length > 120 ? hookText.slice(0, 120) + '…' : hookText}"
        </div>
      )}

      {/* Score bars */}
      <div style={{ background: '#f8fafc', borderRadius: 8, padding: '10px 12px' }}>
        <ScoreBar label="SEO Strategy" value={seoScore} />
        <ScoreBar label="AEO / Snippet" value={aeoScore} />
        <ScoreBar label="Conversion" value={convScore} />
        <ScoreBar label="Depth & Angle" value={depthScore} />
      </div>

      {/* Section list */}
      {sections.length > 0 && (
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#94a3b8', marginBottom: 5, letterSpacing: 0.5 }}>
            SECTIONS ({sections.length})
          </div>
          <ol style={{ margin: 0, paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 3 }}>
            {sections.map((s, i) => (
              <li key={i} style={{ fontSize: 13, color: '#374151' }}>
                {s.heading || s}
                {s.purpose && <span style={{ fontSize: 11, color: '#94a3b8', marginLeft: 6 }}>— {s.purpose}</span>}
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* Expand toggle */}
      <button
        onClick={() => setExpanded(e => !e)}
        style={{
          background: 'none', border: 'none', cursor: 'pointer',
          fontSize: 12, color: '#6366f1', fontWeight: 600, textAlign: 'left', padding: 0,
        }}
      >
        {expanded ? '▲ Hide details' : '▼ Show story, CTA & quality notes'}
      </button>

      {expanded && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {story && (
            <div>
              <div style={{ fontSize: 12, fontWeight: 600, color: '#94a3b8', marginBottom: 4, letterSpacing: 0.5 }}>STORY SCENARIO</div>
              <div style={{ fontSize: 13, color: '#475569', lineHeight: 1.5, fontStyle: 'italic' }}>{story}</div>
            </div>
          )}
          {ctaText && (
            <div>
              <div style={{ fontSize: 12, fontWeight: 600, color: '#94a3b8', marginBottom: 4, letterSpacing: 0.5 }}>CTA</div>
              <div style={{ fontSize: 13, color: '#475569' }}>{ctaText}</div>
            </div>
          )}
          {gaps.length > 0 && (
            <div style={{ background: '#fff7ed', borderRadius: 8, padding: '8px 12px' }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: '#c2410c', marginBottom: 4 }}>Quality Gaps</div>
              {gaps.map((g, i) => <div key={i} style={{ fontSize: 12, color: '#92400e' }}>• {g}</div>)}
            </div>
          )}
          {fixes.length > 0 && (
            <div style={{ background: '#f0fdf4', borderRadius: 8, padding: '8px 12px' }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: '#15803d', marginBottom: 4 }}>Suggested Fixes</div>
              {fixes.map((f, i) => <div key={i} style={{ fontSize: 12, color: '#166534' }}>✓ {f}</div>)}
            </div>
          )}
        </div>
      )}

      {/* Generate Content CTA */}
      <div style={{ marginTop: 4, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        {genDone ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 13, color: '#16a34a', fontWeight: 600 }}>✓ Content generation started</span>
            {setPage && (
              <button
                onClick={() => setPage('content')}
                style={{
                  background: '#6366f1', color: '#fff', border: 'none',
                  borderRadius: 6, padding: '5px 12px', fontSize: 12,
                  fontWeight: 600, cursor: 'pointer',
                }}
              >
                View in Content →
              </button>
            )}
          </div>
        ) : (
          <button
            onClick={handleGenerateContent}
            disabled={generating}
            style={{
              background: generating ? '#e2e8f0' : '#6366f1', color: generating ? '#94a3b8' : '#fff',
              border: 'none', borderRadius: 8, padding: '8px 18px',
              fontSize: 13, fontWeight: 600, cursor: generating ? 'not-allowed' : 'pointer',
              transition: 'background 0.2s',
            }}
          >
            {generating ? 'Starting…' : 'Generate Content →'}
          </button>
        )}
        {genError && <div style={{ fontSize: 12, color: '#dc2626', marginTop: 4 }}>{genError}</div>}
      </div>
    </div>
  )
}
