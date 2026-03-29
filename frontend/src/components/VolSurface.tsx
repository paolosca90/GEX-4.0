import React, { useEffect, useRef, useState, useCallback } from 'react'

interface Snapshot {
  oi_delta: number
  oi_delta_retail: number
  oi_delta_block: number
}

interface OIRow {
  strike: number
  future_price: number
  side: 'call' | 'put'
  snapshots: (Snapshot | null)[]
}

interface OIHeatmapData {
  underlying: string
  offset: number
  multiplier: number
  future_price: number
  columns: string[]
  rows: OIRow[]
  updated_at: string
}

export const VolSurface: React.FC<{ underlying: string }> = ({ underlying }) => {
  const [data, setData] = useState<OIHeatmapData | null>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [tooltip, setTooltip] = useState<{ x: number; y: number; content: string } | null>(null)

  const fetchData = useCallback(async () => {
    try {
      const base = `${window.location.protocol}//${window.location.host}`
      const resp = await fetch(`${base}/api/oi/heatmap/${underlying}`)
      if (resp.ok) {
        const json = await resp.json()
        if (json.columns?.length > 0 || json.rows?.length > 0) {
          setData(json)
        }
      }
    } catch (err) {
      console.error('OI heatmap fetch error:', err)
    }
  }, [underlying])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 60000)
    return () => clearInterval(interval)
  }, [fetchData])

  // Canvas rendering
  useEffect(() => {
    if (!canvasRef.current || !data || data.rows.length === 0) return

    const canvas = canvasRef.current
    const container = containerRef.current
    if (!container) return

    canvas.width = container.clientWidth
    canvas.height = Math.max(200, data.rows.length * 28 + 40)

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const COLS = data.columns.length
    const ROWS = data.rows.length
    const HEADER_H = 28
    const ROW_H = 28
    const COL_W = Math.max(50, (canvas.width - 100) / COLS)
    const LABEL_W = 100

    ctx.clearRect(0, 0, canvas.width, canvas.height)

    // Background
    ctx.fillStyle = '#0a0e17'
    ctx.fillRect(0, 0, canvas.width, canvas.height)

    // Column headers (times)
    ctx.font = '11px JetBrains Mono, monospace'
    ctx.fillStyle = '#94a3b8'
    ctx.textAlign = 'center'
    data.columns.forEach((col, j) => {
      const x = LABEL_W + j * COL_W + COL_W / 2
      ctx.fillText(col, x, HEADER_H - 8)
    })

    // Find max absolute delta for scaling
    let maxAbs = 1
    for (const row of data.rows) {
      for (const snap of row.snapshots) {
        if (snap && Math.abs(snap.oi_delta) > maxAbs) {
          maxAbs = Math.abs(snap.oi_delta)
        }
      }
    }

    // Rows
    data.rows.forEach((row, i) => {
      const y = HEADER_H + i * ROW_H

      // Row label (strike / future_price)
      ctx.font = '10px JetBrains Mono, monospace'
      ctx.fillStyle = row.side === 'call' ? '#22C55E' : '#EF4444'
      ctx.textAlign = 'left'
      ctx.fillText(`${row.strike.toFixed(0)} / ${row.future_price.toFixed(0)}`, 4, y + ROW_H - 8)

      // Cells
      row.snapshots.forEach((snap, j) => {
        const x = LABEL_W + j * COL_W
        if (snap === null) {
          ctx.fillStyle = '#1e293b'
        } else {
          const abs = Math.abs(snap.oi_delta)
          const intensity = Math.min(1, abs / maxAbs)
          if (snap.oi_delta > 0) {
            const r = Math.round(0 + (34 - 0) * (1 - intensity))
            const g = Math.round(200 + (255 - 200) * intensity)
            const b = Math.round(83 + (202 - 83) * (1 - intensity))
            ctx.fillStyle = `rgba(${r},${g},${b},0.85)`
          } else if (snap.oi_delta < 0) {
            const r = Math.round(255 + (239 - 255) * (1 - intensity))
            const g = Math.round(23 + (68 - 23) * (1 - intensity))
            const b = Math.round(68 + (69 - 68) * (1 - intensity))
            ctx.fillStyle = `rgba(${r},${g},${b},0.85)`
          } else {
            ctx.fillStyle = '#1e293b'
          }
        }
        ctx.fillRect(x + 1, y + 1, COL_W - 2, ROW_H - 2)

        if (snap !== null && COL_W > 45) {
          ctx.font = '9px JetBrains Mono, monospace'
          ctx.fillStyle = '#ffffff'
          ctx.textAlign = 'center'
          const label = snap.oi_delta >= 0 ? `+${snap.oi_delta}` : `${snap.oi_delta}`
          ctx.fillText(label, x + COL_W / 2, y + ROW_H / 2 + 3)
        }
      })
    })

    const handleMouseMove = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect()
      const mx = e.clientX - rect.left
      const my = e.clientY - rect.top

      if (my < HEADER_H || mx < LABEL_W) {
        setTooltip(null)
        return
      }

      const col = Math.floor((mx - LABEL_W) / COL_W)
      const row = Math.floor((my - HEADER_H) / ROW_H)

      if (col >= 0 && col < COLS && row >= 0 && row < ROWS) {
        const r = data.rows[row]
        const s = r.snapshots[col]
        if (s) {
          setTooltip({
            x: e.clientX - rect.left,
            y: e.clientY - rect.top,
            content: `Strike: ${r.strike.toFixed(0)} | Future: ${r.future_price.toFixed(2)}\n` +
                     `OI Δ: ${s.oi_delta >= 0 ? '+' : ''}${s.oi_delta}\n` +
                     `Retail: ${s.oi_delta_retail >= 0 ? '+' : ''}${s.oi_delta_retail} | ` +
                     `Block: ${s.oi_delta_block >= 0 ? '+' : ''}${s.oi_delta_block}`
          })
          return
        }
      }
      setTooltip(null)
    }

    canvas.onmousemove = handleMouseMove
    canvas.onmouseleave = () => setTooltip(null)

  }, [data])

  return (
    <div className="sidebar-card" style={{ position: 'relative' }}>
      <div className="sidebar-card-header">
        <span className="sidebar-card-title">OI Delta Heatmap</span>
        {data && (
          <span style={{ fontSize: '0.55rem', color: 'var(--text-muted)' }}>
            {data.underlying} · FP: {data.future_price.toFixed(2)}
          </span>
        )}
      </div>

      {!data || data.rows.length === 0 ? (
        <div style={{ padding: '12px', fontSize: '0.6rem', color: 'var(--text-muted)', textAlign: 'center' }}>
          No OI data available
        </div>
      ) : (
        <div ref={containerRef} style={{ position: 'relative', width: '100%', overflowX: 'auto' }}>
          <canvas ref={canvasRef} style={{ display: 'block', minWidth: '100%' }} />
          {tooltip && (
            <div style={{
              position: 'absolute',
              left: tooltip.x + 10,
              top: tooltip.y - 10,
              background: 'rgba(10,14,23,0.95)',
              border: '1px solid #334155',
              borderRadius: '4px',
              padding: '6px 8px',
              fontSize: '0.58rem',
              fontFamily: 'JetBrains Mono, monospace',
              color: '#e2e8f0',
              whiteSpace: 'pre-line',
              pointerEvents: 'none',
              zIndex: 10,
            }}>
              {tooltip.content}
            </div>
          )}
        </div>
      )}

      {data && data.updated_at && (
        <div style={{ fontSize: '0.5rem', color: 'var(--text-muted)', textAlign: 'right', padding: '2px 4px' }}>
          {new Date(data.updated_at).toLocaleTimeString()}
        </div>
      )}
    </div>
  )
}
