import React, { useState, useEffect } from 'react'

interface GreeksSummary {
  total_gamma: number | null
  net_delta: number | null
  avg_theta: number | null
  call_iv_mean: number | null
  put_iv_mean: number | null
  skew: number | null
  iv_rank: number | null
}

interface GreeksData {
  underlying: string
  spot: number | null
  timestamp: string
  summary: GreeksSummary
}

interface GreeksSummaryData {
  regime: string
  total_gex: number
  avg_theta_decay: number | null
  iv_context: {
    atm_iv: number | null
    skew_25delta: number | null
    term_structure: string
  }
}

export const GreeksPanel: React.FC<{ underlying: string }> = ({ underlying }) => {
  const [greeks, setGreeks] = useState<GreeksData | null>(null)
  const [summary, setSummary] = useState<GreeksSummaryData | null>(null)

  useEffect(() => {
    const fetchGreeks = async () => {
      try {
        const base = `${window.location.protocol}//${window.location.host}`
        const [chainResp, summaryResp] = await Promise.all([
          fetch(`${base}/api/greeks/${underlying}`),
          fetch(`${base}/api/greeks/summary/${underlying}`),
        ])
        if (chainResp.ok) setGreeks(await chainResp.json())
        if (summaryResp.ok) setSummary(await summaryResp.json())
      } catch (err) {
        console.error('Greeks fetch error:', err)
      }
    }
    fetchGreeks()
    const interval = setInterval(fetchGreeks, 60000)
    return () => clearInterval(interval)
  }, [underlying])

  const regime = summary?.regime || 'unknown'
  const isLong = regime === 'long_gamma'
  const ivPct = greeks?.summary?.call_iv_mean
    ? Math.round(greeks.summary.call_iv_mean * 10000) / 100
    : null

  return (
    <div className="sidebar-card">
      <div className="sidebar-card-header">
        <span className="sidebar-card-title">Greeks & IV</span>
        <span className={`regime-badge ${isLong ? 'long' : 'short'}`}>
          {regime === 'unknown' ? 'N/A' : isLong ? 'LONG GAMMA' : 'SHORT GAMMA'}
        </span>
      </div>

      {ivPct !== null && (
        <div style={{ marginBottom: '8px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.6rem', color: 'var(--text-muted)' }}>
            <span>ATM IV</span>
            <span style={{ color: 'var(--text-primary)', fontFamily: "'JetBrains Mono', monospace" }}>
              {ivPct.toFixed(1)}%
            </span>
          </div>
          <div className="iv-bar">
            <div className="iv-bar-fill" style={{ width: `${Math.min(100, ivPct * 2)}%` }} />
          </div>
        </div>
      )}

      <div className="greeks-table">
        <div className="greeks-row">
          <span className="greeks-label">Net Delta</span>
          <span className={`greeks-value ${(greeks?.summary?.net_delta || 0) >= 0 ? 'positive' : 'negative'}`}>
            {greeks?.summary?.net_delta?.toFixed(4) || '—'}
          </span>
        </div>
        <div className="greeks-row">
          <span className="greeks-label">Total Gamma</span>
          <span className="greeks-value">
            {greeks?.summary?.total_gamma?.toFixed(6) || '—'}
          </span>
        </div>
        <div className="greeks-row">
          <span className="greeks-label">Avg Theta</span>
          <span className={`greeks-value ${(greeks?.summary?.avg_theta || 0) <= 0 ? 'negative' : 'positive'}`}>
            {greeks?.summary?.avg_theta?.toFixed(4) || '—'}
          </span>
        </div>
        <div className="greeks-row">
          <span className="greeks-label">Skew</span>
          <span className={`greeks-value ${(greeks?.summary?.skew || 0) >= 0 ? 'positive' : 'negative'}`}>
            {greeks?.summary?.skew != null ? `${(greeks.summary.skew * 100).toFixed(2)}%` : '—'}
          </span>
        </div>
        <div className="greeks-row">
          <span className="greeks-label">Term Structure</span>
          <span className="greeks-value">
            {summary?.iv_context?.term_structure || '—'}
          </span>
        </div>
      </div>
    </div>
  )
}