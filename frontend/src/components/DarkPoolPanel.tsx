import React, { useState, useEffect } from 'react'

interface DixData {
  date: string
  underlying: string
  short_volume: number
  total_volume: number
  short_ratio: number
  dix: number
  dark_volume_estimate: number
}

export const DarkPoolPanel: React.FC<{ underlying: string }> = ({ underlying }) => {
  const [dixData, setDixData] = useState<DixData | null>(null)
  const [history, setHistory] = useState<DixData[]>([])

  useEffect(() => {
    const fetchData = async () => {
      try {
        const base = `${window.location.protocol}//${window.location.host}`
        const [dixResp, histResp] = await Promise.all([
          fetch(`${base}/api/darkpool/dix/${underlying}`),
          fetch(`${base}/api/darkpool/history/${underlying}?days=7`),
        ])
        if (dixResp.ok) {
          const data = await dixResp.json()
          setDixData(data)
        }
        if (histResp.ok) {
          const data = await histResp.json()
          setHistory(data.history || [])
        }
      } catch (err) {
        console.error('Dark pool fetch error:', err)
      }
    }
    fetchData()
    const interval = setInterval(fetchData, 300000)
    return () => clearInterval(interval)
  }, [underlying])

  const dix = dixData?.dix
  const shortRatio = dixData?.short_ratio
  const totalVol = dixData?.total_volume

  const dixLevel: 'low' | 'mid' | 'high' = dix != null
    ? (dix < 0.15 ? 'low' : dix > 0.45 ? 'high' : 'mid')
    : 'mid'

  const formatVol = (v: number | undefined): string => {
    if (!v) return '\u2014'
    if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`
    if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`
    if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`
    return v.toString()
  }

  return (
    <div className="sidebar-card">
      <div className="sidebar-card-header">
        <span className="sidebar-card-title">Dark Pool</span>
        <span style={{ fontSize: '0.6rem', color: 'var(--text-muted)' }}>
          {dixData?.date || '\u2014'}
        </span>
      </div>

      <div style={{ marginBottom: '8px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.6rem', color: 'var(--text-muted)' }}>
          <span>DIX (Dark Index)</span>
          <span style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontWeight: 700,
            color: dixLevel === 'high' ? 'var(--success)' : dixLevel === 'low' ? 'var(--danger)' : 'var(--warning)',
          }}>
            {dix != null ? dix.toFixed(4) : '\u2014'}
          </span>
        </div>
        <div className="dix-gauge">
          <div
            className={`dix-gauge-fill ${dixLevel}`}
            style={{ width: `${dix != null ? dix * 100 : 0}%` }}
          />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.45rem', color: 'var(--text-muted)' }}>
          <span>0 (bearish)</span>
          <span>1 (bullish)</span>
        </div>
      </div>

      <div className="dix-metric">
        <span className="dix-label">Short Ratio</span>
        <span className="dix-value">
          {shortRatio != null ? `${(shortRatio * 100).toFixed(1)}%` : '\u2014'}
        </span>
      </div>
      <div className="dix-metric">
        <span className="dix-label">Total Volume</span>
        <span className="dix-value">{formatVol(totalVol)}</span>
      </div>
      <div className="dix-metric">
        <span className="dix-label">Dark Vol Est.</span>
        <span className="dix-value">{formatVol(dixData?.dark_volume_estimate)}</span>
      </div>

      {history.length > 1 && (
        <div style={{ marginTop: '8px' }}>
          <div style={{ fontSize: '0.55rem', color: 'var(--text-muted)', marginBottom: '4px' }}>
            7-Day DIX
          </div>
          <svg viewBox="0 0 100 30" style={{ width: '100%', height: 30 }}>
            {(() => {
              const points = [...history].reverse()
              const dixVals = points.map(p => p.dix).filter((d): d is number => d != null)
              if (dixVals.length < 2) return null
              const min = Math.min(...dixVals)
              const max = Math.max(...dixVals)
              const range = max - min || 0.01
              const pathD = points.map((p, i) => {
                const x = (i / (points.length - 1)) * 100
                const y = 28 - ((p.dix - min) / range) * 26
                return `${i === 0 ? 'M' : 'L'} ${x} ${y}`
              }).join(' ')
              return <path d={pathD} fill="none" stroke="var(--primary)" strokeWidth="1.5" />
            })()}
          </svg>
        </div>
      )}
    </div>
  )
}