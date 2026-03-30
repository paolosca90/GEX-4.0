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
const SKEW_THRESHOLD = 0.03; // 3% - lowered from 15%

export const SkewGauge: React.FC<SkewGaugeProps> = ({ underlying }) => {
  const [skewValue, setSkewValue] = useState<number | null>(null);
  const [skewDirection, setSkewDirection] = useState<'put' | 'call' | 'neutral' | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchSkew = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await fetch(`${API_BASE}/api/volatility/surface?underlying=${underlying}`);
      const data = await resp.json();
      if (data.error || !data.surface?.length) {
        console.log(`[SkewGauge] No data for ${underlying}: error=${data.error}, surfaces=${data.surface?.length}`);
        setLoading(false);
        return;
      }

      const strikes = data.surface[0]?.strikes || [];
      const spot = data.spot_price || 0;

      if (!spot || !strikes.length) {
        console.log(`[SkewGauge] Missing spot or strikes: spot=${spot}, strikes=${strikes.length}`);
        setLoading(false);
        return;
      }

      // Use ±5% range to capture full skew curve including OTM wings
      const lower = spot * 0.95;
      const upper = spot * 1.05;
      const atmStrikes = strikes.filter((s: StrikeData) =>
        s.strike >= lower && s.strike <= upper &&
        s.call_iv != null && s.put_iv != null && s.gamma != null
      );

      if (!atmStrikes.length) {
        console.log(`[SkewGauge] No ATM strikes in ${lower.toFixed(0)}-${upper.toFixed(0)} for ${underlying}`);
        setLoading(false);
        return;
      }

      // Find the most negative skew (max downside risk) — not the average
      // Average cancels put skew (-11%) with call skew (+11%) → near zero = WRONG
      // Min skew correctly captures elevated put skew risk
      let minSkew = 0;
      for (const s of atmStrikes) {
        const skew = s.skew || 0;
        if (skew < minSkew) {
          minSkew = skew;
        }
      }

      console.log(`[SkewGauge] ${underlying}: minSkew=${(minSkew*100).toFixed(2)}%, ${atmStrikes.length} strikes`);
      setSkewValue(minSkew);

      // Negative skew = put skew (downside risk), positive skew = call skew (upside risk)
      if (minSkew < -SKEW_THRESHOLD) {
        setSkewDirection('put');
      } else if (minSkew > SKEW_THRESHOLD) {
        setSkewDirection('call');
      } else {
        setSkewDirection('neutral');
      }
      setLoading(false);
    } catch (e) {
      console.error(`[SkewGauge] Error fetching skew for ${underlying}:`, e);
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