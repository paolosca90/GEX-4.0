import React, { useState, useEffect, useRef, useCallback } from 'react';

interface StrikeData {
  strike: number;
  iv: number;
  call_iv: number;
  put_iv: number;
  skew: number;
  delta: number;
  gamma: number;
}

interface ExpirySurface {
  expiration: string;
  days_to_expiry: number;
  strikes: StrikeData[];
}

interface VolSurfaceProps {
  underlying: string;
}

const API_BASE = `${window.location.protocol}//${window.location.host}`;

const COLOR_SCALE: [number, string][] = [
  [0.10, '#1e40af'],  // <10% IV → deep blue
  [0.20, '#60a5fa'],  // 10-20% → light blue
  [0.30, '#22c55e'],  // 20-30% → green
  [0.40, '#eab308'],  // 30-40% → yellow
  [0.50, '#f97316'],  // 40-50% → orange
  [1.00, '#ef4444'],  // 50%+  → red
];

function interpolateColor(iv: number): string {
  const stops: [number, [number, number, number]][] = [
    [0.10, [30, 64, 175]],
    [0.20, [96, 165, 250]],
    [0.30, [34, 197, 94]],
    [0.40, [234, 179, 8]],
    [0.50, [249, 115, 22]],
    [1.00, [239, 68, 68]],
  ];
  for (let i = 0; i < stops.length - 1; i++) {
    const [t0, [r0, g0, b0]] = stops[i];
    const [t1, [r1, g1, b1]] = stops[i + 1];
    if (iv >= t0 && iv < t1) {
      const ratio = (iv - t0) / (t1 - t0);
      const r = Math.round(r0 + (r1 - r0) * ratio);
      const g = Math.round(g0 + (g1 - g0) * ratio);
      const b = Math.round(b0 + (b1 - b0) * ratio);
      return `rgb(${r},${g},${b})`;
    }
  }
  return 'rgb(239,68,68)';
}

export const VolSurface: React.FC<VolSurfaceProps> = ({ underlying }) => {
  const [surface, setSurface] = useState<ExpirySurface[]>([]);
  const [spotPrice, setSpotPrice] = useState<number>(0);
  const [updatedAt, setUpdatedAt] = useState<string>('');
  const [error, setError] = useState<string>('');
  const [hoveredCell, setHoveredCell] = useState<{expiry: string, strike: StrikeData, x: number, y: number} | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const fetchSurface = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE}/api/volatility/surface?underlying=${underlying}`);
      const data = await resp.json();
      if (data.error) {
        setError(data.error);
        return;
      }
      setSurface(data.surface || []);
      setSpotPrice(data.spot_price || 0);
      setUpdatedAt(data.updated_at || '');
      setError('');
    } catch (e) {
      setError('Failed to fetch');
    }
  }, [underlying]);

  useEffect(() => {
    fetchSurface();
    const interval = setInterval(fetchSurface, 120000); // 2 min
    return () => clearInterval(interval);
  }, [fetchSurface]);

  // Draw heatmap on canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container || surface.length === 0) return;

    const strikes = surface[0]?.strikes || [];
    if (strikes.length === 0) return;

    const numExpirations = surface.length;
    const numStrikes = Math.min(strikes.length, 25);

    const CELL_WIDTH = Math.floor(container.clientWidth / numExpirations);
    const CELL_HEIGHT = 22;
    const HEADER_HEIGHT = 24;
    const canvasHeight = HEADER_HEIGHT + numStrikes * CELL_HEIGHT;

    canvas.width = container.clientWidth;
    canvas.height = canvasHeight;
    canvas.style.height = `${canvasHeight}px`;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Draw column headers
    ctx.font = 'bold 11px monospace';
    ctx.fillStyle = '#94a3b8';
    surface.forEach((exp, col) => {
      const label = exp.days_to_expiry === 0 ? '0DTE' : `${exp.days_to_expiry}DTE`;
      ctx.fillText(label, col * CELL_WIDTH + 4, HEADER_HEIGHT - 6);
    });

    // Bucket strikes: select evenly spaced strikes
    const bucketSize = Math.max(1, Math.floor(strikes.length / numStrikes));
    const bucketedStrikes = strikes.filter((_, i) => i % bucketSize === 0).slice(0, numStrikes);

    // Draw cells
    bucketedStrikes.forEach((strikeData, row) => {
      const isATM = Math.abs(strikeData.strike - spotPrice) < (spotPrice * 0.005);

      surface.forEach((exp, col) => {
        const expStrike = exp.strikes.find(s => s.strike === strikeData.strike);
        if (!expStrike) return;

        const x = col * CELL_WIDTH;
        const y = HEADER_HEIGHT + row * CELL_HEIGHT;

        ctx.fillStyle = interpolateColor(expStrike.iv);
        ctx.fillRect(x + 1, y + 1, CELL_WIDTH - 2, CELL_HEIGHT - 2);

        if (isATM) {
          ctx.strokeStyle = '#fbbf24';
          ctx.lineWidth = 2;
          ctx.strokeRect(x + 1, y + 1, CELL_WIDTH - 2, CELL_HEIGHT - 2);
        }

        if (col === 0) {
          ctx.fillStyle = '#e2e8f0';
          ctx.font = '9px monospace';
          ctx.fillText(`${strikeData.strike.toFixed(0)}`, 2, y + CELL_HEIGHT - 4);
        }

        if (Math.abs(expStrike.skew) > 0.15) {
          ctx.fillStyle = expStrike.skew > 0 ? '#ef4444' : '#3b82f6';
          ctx.font = '8px monospace';
          ctx.fillText(expStrike.skew > 0 ? '▲' : '▼', x + CELL_WIDTH - 12, y + CELL_HEIGHT - 4);
        }
      });
    });

  }, [surface, spotPrice]);

  if (error) {
    return (
      <div className="vol-surface-panel" style={{ padding: '0.5rem', color: '#ef4444', fontSize: '0.75rem' }}>
        Vol Surface: {error}
      </div>
    );
  }

  if (surface.length === 0) {
    return (
      <div className="vol-surface-panel" style={{ padding: '0.5rem', color: '#94a3b8', fontSize: '0.75rem' }}>
        Loading Vol Surface...
      </div>
    );
  }

  return (
    <div className="vol-surface-panel" style={{ padding: '0.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.25rem' }}>
        <span style={{ fontSize: '0.7rem', fontWeight: 600, color: '#e2e8f0' }}>VOL SURFACE</span>
        <span style={{ fontSize: '0.65rem', color: '#64748b' }}>
          {updatedAt ? `Updated ${new Date(updatedAt).toLocaleTimeString()}` : ''}
        </span>
      </div>
      <div ref={containerRef} style={{ position: 'relative', width: '100%', overflow: 'hidden' }}>
        <canvas
          ref={canvasRef}
          style={{ display: 'block', width: '100%' }}
          onMouseMove={(e) => {
            const canvas = canvasRef.current;
            if (!canvas) return;
            const rect = canvas.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            const col = Math.floor(x / (canvas.width / surface.length));
            const HEADER_HEIGHT = 24;
            const CELL_HEIGHT = 22;
            const row = Math.floor((y - HEADER_HEIGHT) / CELL_HEIGHT);
            const strikes = surface[0]?.strikes || [];
            const bucketSize = Math.max(1, Math.floor(strikes.length / Math.min(strikes.length, 25)));
            const bucketedStrikes = strikes.filter((_, i) => i % bucketSize === 0).slice(0, 25);
            if (col >= 0 && col < surface.length && row >= 0 && row < bucketedStrikes.length) {
              const exp = surface[col];
              const strike = bucketedStrikes[row];
              const expStrike = exp?.strikes?.find(s => s.strike === strike?.strike);
              if (expStrike) {
                setHoveredCell({ expiry: exp.expiration, strike: expStrike, x: e.clientX, y: e.clientY });
              }
            }
          }}
          onMouseLeave={() => setHoveredCell(null)}
        />
        {hoveredCell && (
          <div
            style={{
              position: 'fixed',
              left: hoveredCell.x + 12,
              top: hoveredCell.y - 60,
              background: 'rgba(15,23,42,0.95)',
              border: '1px solid #334155',
              borderRadius: 4,
              padding: '6px 10px',
              fontSize: '0.7rem',
              color: '#e2e8f0',
              pointerEvents: 'none',
              zIndex: 1000,
              minWidth: 140,
            }}
          >
            <div style={{ fontWeight: 600, marginBottom: 3 }}>{hoveredCell.expiry}</div>
            <div>Strike: <b>{hoveredCell.strike.strike.toFixed(0)}</b></div>
            <div>IV: <b>{(hoveredCell.strike.iv * 100).toFixed(1)}%</b></div>
            <div>C IV: {(hoveredCell.strike.call_iv * 100).toFixed(1)}% | P IV: {(hoveredCell.strike.put_iv * 100).toFixed(1)}%</div>
            <div>Skew: <b style={{ color: hoveredCell.strike.skew > 0 ? '#ef4444' : '#3b82f6' }}>{(hoveredCell.strike.skew * 100).toFixed(1)}%</b></div>
            <div>Delta: {hoveredCell.strike.delta?.toFixed(3)} | Gamma: {hoveredCell.strike.gamma?.toFixed(4)}</div>
          </div>
        )}
      </div>
      <div style={{ display: 'flex', gap: 4, marginTop: 4, flexWrap: 'wrap' }}>
        <span style={{ fontSize: '0.6rem', color: '#64748b' }}>IV:</span>
        {COLOR_SCALE.map(([t, c]) => (
          <span key={t} style={{ display: 'flex', alignItems: 'center', gap: 2, fontSize: '0.6rem', color: '#64748b' }}>
            <span style={{ width: 8, height: 8, background: c, borderRadius: 1, display: 'inline-block' }} />
            {(t * 100).toFixed(0)}%
          </span>
        ))}
        <span style={{ fontSize: '0.6rem', color: '#64748b', marginLeft: 4 }}>| Skew ▲=Put {'>'}=Call</span>
      </div>
    </div>
  );
};
