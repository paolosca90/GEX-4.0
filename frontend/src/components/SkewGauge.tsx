import React, { useState, useEffect, useCallback } from 'react';

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

interface SkewGaugeProps {
  underlying: string;
}

const API_BASE = `${window.location.protocol}//${window.location.host}`;
const SKEW_THRESHOLD = 0.15; // 15%

export const SkewGauge: React.FC<SkewGaugeProps> = ({ underlying }) => {
  const [skewValue, setSkewValue] = useState<number | null>(null);
  const [skewDirection, setSkewDirection] = useState<'put' | 'call' | 'neutral' | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchSkew = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE}/api/volatility/surface?underlying=${underlying}`);
      const data = await resp.json();
      if (data.error || !data.surface?.length) {
        setLoading(false);
        return;
      }

      const strikes = data.surface[0]?.strikes || [];
      const spot = data.spot_price || 0;

      if (!spot || !strikes.length) {
        setLoading(false);
        return;
      }

      const lower = spot * 0.98;
      const upper = spot * 1.02;
      const otmStrikes = strikes.filter((s: StrikeData) =>
        s.strike >= lower && s.strike <= upper &&
        s.call_iv != null && s.put_iv != null && s.gamma != null
      );

      if (!otmStrikes.length) {
        setLoading(false);
        return;
      }

      let totalGamma = 0;
      let weightedSkew = 0;
      for (const s of otmStrikes) {
        const gamma = Math.abs(s.gamma || 0);
        totalGamma += gamma;
        weightedSkew += s.skew * gamma;
      }

      const avgSkew = totalGamma > 0 ? weightedSkew / totalGamma : 0;
      setSkewValue(avgSkew);

      if (avgSkew > SKEW_THRESHOLD) {
        setSkewDirection('put');
      } else if (avgSkew < -SKEW_THRESHOLD) {
        setSkewDirection('call');
      } else {
        setSkewDirection('neutral');
      }

      setLoading(false);
    } catch (e) {
      setLoading(false);
    }
  }, [underlying]);

  useEffect(() => {
    fetchSkew();
    const interval = setInterval(fetchSkew, 120000);
    return () => clearInterval(interval);
  }, [fetchSkew]);

  if (loading) {
    return (
      <div className="skew-gauge" style={{
        padding: '0.5rem',
        background: 'rgba(15,23,42,0.8)',
        borderRadius: 6,
        marginTop: '0.25rem',
      }}>
        <div style={{ fontSize: '0.65rem', color: '#64748b', marginBottom: 4 }}>SKEW GAUGE</div>
        <div style={{ color: '#94a3b8', fontSize: '0.7rem' }}>Loading...</div>
      </div>
    );
  }

  const skewColor = skewDirection === 'put' ? '#ef4444' : skewDirection === 'call' ? '#3b82f6' : '#64748b';
  const skewSign = skewValue !== null ? (skewValue >= 0 ? '+' : '') : '';
  const badge = skewDirection === 'put' ? '▲ HIGH RISK' : skewDirection === 'call' ? '▼ HIGH RISK' : '— NEUTRAL';

  return (
    <div className="skew-gauge" style={{
      padding: '0.5rem',
      background: 'rgba(15,23,42,0.8)',
      borderRadius: 6,
      marginTop: '0.25rem',
      border: `1px solid ${skewDirection !== 'neutral' ? skewColor : '#334155'}`,
    }}>
      <div style={{ fontSize: '0.65rem', color: '#64748b', marginBottom: 4 }}>SKEW GAUGE</div>
      {skewValue !== null ? (
        <>
          <div style={{ fontSize: '1.4rem', fontWeight: 700, color: skewColor, fontFamily: 'monospace' }}>
            {skewSign}{(skewValue * 100).toFixed(1)}%
          </div>
          <div style={{ fontSize: '0.7rem', fontWeight: 600, color: skewColor, marginTop: 2 }}>
            {badge}
          </div>
          <div style={{ fontSize: '0.6rem', color: '#475569', marginTop: 4 }}>
            Skew threshold: {(SKEW_THRESHOLD * 100).toFixed(0)}%
          </div>
        </>
      ) : (
        <div style={{ color: '#64748b', fontSize: '0.7rem' }}>No data</div>
      )}
    </div>
  );
};