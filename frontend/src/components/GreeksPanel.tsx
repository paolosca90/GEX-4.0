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

interface OIBuildupEntry {
  strike: number
  oi_delta: number
  oi_delta_retail: number
  oi_delta_block: number
  side: 'call' | 'put'
}

interface OIBuildupData {
  calls: OIBuildupEntry[]
  puts: OIBuildupEntry[]
  updated_at: string
}

export const GreeksPanel: React.FC<{ underlying: string }> = ({ underlying }) => {
  const [greeks, setGreeks] = useState<GreeksData | null>(null)
  const [summary, setSummary] = useState<GreeksSummaryData | null>(null)
  const [oiBuildup, setOiBuildup] = useState<OIBuildupData | null>(null)

  useEffect(() => {
    const fetchGreeks = async () => {
      try {
        const base = `${window.location.protocol}//${window.location.host}`
        const [chainResp, summaryResp, oiResp] = await Promise.all([
          fetch(`${base}/api/greeks/${underlying}`),
          fetch(`${base}/api/greeks/summary/${underlying}`),
          fetch(`${base}/api/oi/buildup/${underlying}`),
        ])
        if (chainResp.ok) setGreeks(await chainResp.json())
        if (summaryResp.ok) setSummary(await summaryResp.json())
        if (oiResp.ok) setOiBuildup(await oiResp.json())
      } catch (err) {
        console.error('Greeks fetch error:', err)
      }
    }
    fetchGreeks()
    const interval = setInterval(fetchGreeks, 30000)
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
      {oiBuildup && (oiBuildup.calls.length > 0 || oiBuildup.puts.length > 0) && (
        <div style={{ marginTop: '12px', borderTop: '1px solid rgba(148,163,184,0.1)', paddingTop: '8px' }}>
          <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', marginBottom: '6px', fontWeight: 600 }}>
            OI BUILDUP
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px', fontSize: '0.58rem' }}>
            {/* Calls */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', color: '#22C55E', marginBottom: '2px' }}>
                <span>CALLS</span><span>ΔOI</span>
              </div>
              {oiBuildup.calls.map((c) => {
                const total = Math.abs(c.oi_delta_retail + c.oi_delta_block);
                const blockPct = total > 0 ? Math.abs(c.oi_delta_block) / total : 0;
                return (
                  <div key={c.strike} style={{ display: 'flex', justifyContent: 'space-between', color: '#22C55E', fontFamily: "'JetBrains Mono', monospace" }}>
                    <span>{c.strike.toFixed(0)}</span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <span>{c.oi_delta >= 0 ? '+' : ''}{c.oi_delta}</span>
                      {blockPct > 0.5 && <span style={{ fontSize: '0.5rem', opacity: 0.7 }}>BLK</span>}
                    </div>
                  </div>
                );
              })}
            </div>
            {/* Puts */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', color: '#EF4444', marginBottom: '2px' }}>
                <span>PUTS</span><span>ΔOI</span>
              </div>
              {oiBuildup.puts.map((p) => {
                const total = Math.abs(p.oi_delta_retail + p.oi_delta_block);
                const blockPct = total > 0 ? Math.abs(p.oi_delta_block) / total : 0;
                return (
                  <div key={p.strike} style={{ display: 'flex', justifyContent: 'space-between', color: '#EF4444', fontFamily: "'JetBrains Mono', monospace" }}>
                    <span>{p.strike.toFixed(0)}</span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <span>{p.oi_delta >= 0 ? '+' : ''}{p.oi_delta}</span>
                      {blockPct > 0.5 && <span style={{ fontSize: '0.5rem', opacity: 0.7 }}>BLK</span>}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}