import React, { useState, useEffect, useRef } from 'react'

interface FlowTick {
  type: string
  symbol: string
  time: string
  call_premium: number
  put_premium: number
  call_volume: number
  put_volume: number
  net_drift: number
}

interface SmartMoneyBoxProps {
  underlying: string  // SPX o QQQ direttamente
}

// Store ticks in memory for 5m aggregation
const tickHistory: Record<string, FlowTick[]> = {
  SPX: [],
  QQQ: []
}

export const SmartMoneyBox: React.FC<SmartMoneyBoxProps> = ({ underlying }) => {
  // 1 minute metrics
  const [netFlow1m, setNetFlow1m] = useState(0)
  const [netDrift1m, setNetDrift1m] = useState(0)

  // 5 minutes EMA metrics
  const [netDrift5m, setNetDrift5m] = useState(0)
  const [drift5mPeak, setDrift5mPeak] = useState(1) // Track peak for normalizing the gauge

  // Signal state
  const [signal, setSignal] = useState('⚪ NEUTRAL')
  const [signalColor, setSignalColor] = useState('#666')
  const [isLive, setIsLive] = useState(false)
  const lastUpdateRef = useRef<number>(0)

  // Percentages for dual bars
  const [callPremPercent, setCallPremPercent] = useState(50)
  const [putPremPercent, setPutPremPercent] = useState(50)
  const [callVolPercent, setCallVolPercent] = useState(50)
  const [putVolPercent, setPutVolPercent] = useState(50)

  // Process a flow tick
  const processTick = (tick: FlowTick) => {
    const now = Date.now()
    const tickTime = new Date(tick.time).getTime()

    // Add to history
    if (!tickHistory[underlying]) {
      tickHistory[underlying] = []
    }
    tickHistory[underlying].push(tick)

    // Keep only last 5 minutes of ticks
    const fiveMinutesAgo = now - 5 * 60 * 1000
    tickHistory[underlying] = tickHistory[underlying].filter(t =>
      new Date(t.time).getTime() > fiveMinutesAgo
    )

    // === 1 MINUTE METRICS ===
    // Net Flow = Call Volume - Put Volume
    // Net Drift = Call Premium - Put Premium (already passed as tick.net_drift from backend 5m, but let's calculate exact 1m drift)

    // Calculate 1m sums from history to ensure accuracy
    const oneMinuteAgo = now - 60 * 1000
    const ticks1m = tickHistory[underlying].filter(t => new Date(t.time).getTime() > oneMinuteAgo)

    // If tick provides instantaneous 1m sums, we use those for Flow and Drift (Premium)
    const flowVolume = (tick.call_volume || 0) - (tick.put_volume || 0)
    const driftPremium = (tick.call_premium || 0) - (tick.put_premium || 0)

    setNetFlow1m(flowVolume)
    setNetDrift1m(driftPremium)

    // === 5 MINUTE EMA METRICS ===
    const drift5m = tick.net_drift || 0
    setNetDrift5m(drift5m)
    // Update rolling peak for gauge normalization
    setDrift5mPeak(prev => Math.max(prev, Math.abs(drift5m), 1))

    // Calculate Percentages for the Dual Bars (Premium vs Volume)
    const callPrem = Math.abs(tick.call_premium || 0)
    const putPrem = Math.abs(tick.put_premium || 0)
    const totalPrem = callPrem + putPrem

    const callVol = Math.abs(tick.call_volume || 0)
    const putVol = Math.abs(tick.put_volume || 0)
    const totalVol = callVol + putVol

    const cpPct = totalPrem > 0 ? (callPrem / totalPrem) * 100 : 50
    const ppPct = totalPrem > 0 ? (putPrem / totalPrem) * 100 : 50
    setCallPremPercent(cpPct)
    setPutPremPercent(ppPct)

    const cvPct = totalVol > 0 ? (callVol / totalVol) * 100 : 50
    const pvPct = totalVol > 0 ? (putVol / totalVol) * 100 : 50
    setCallVolPercent(cvPct)
    setPutVolPercent(pvPct)

    lastUpdateRef.current = now
    setIsLive(true)

    // === Determine Signal (Strictly driven by EMA Drift) ===
    const isDriftBullish = drift5m > 0
    const isDriftBearish = drift5m < 0

    // To prevent noise when drift is basically flat (e.g. less than $10k net)
    const driftIsSignificant = Math.abs(drift5m) > 10000

    if (!driftIsSignificant) {
        setSignal('⚪ NEUTRAL DRIFT')
        setSignalColor('var(--text-muted)')
    } else if (isDriftBullish) {
        if (cpPct > 50 && cvPct > 50) {
            setSignal('🟢 STRONG CALL TREND')
            setSignalColor('var(--success)')
        } else if (ppPct > 55 || pvPct > 55) {
            // SPX drifting up, but heavy Put buying detected -> Bear Trap
            setSignal('🚨 BEAR TRAP (SQZ UP)')
            setSignalColor('var(--success)')
        } else {
            setSignal('🟢 CALL DRIFT')
            setSignalColor('var(--success)')
        }
    } else if (isDriftBearish) {
        if (ppPct > 50 && pvPct > 50) {
            setSignal('🔴 STRONG PUT TREND')
            setSignalColor('var(--danger)')
        } else if (cpPct > 55 || cvPct > 55) {
            // SPX drifting down, but heavy Call buying detected -> Bull Trap
            setSignal('🚨 BULL TRAP (DUMP)')
            setSignalColor('var(--danger)')
        } else {
            setSignal('🔴 PUT DRIFT')
            setSignalColor('var(--danger)')
        }
    }
  }

  // Listen for market_tick events from WebSocket
  useEffect(() => {
    const handleMarketTick = (e: CustomEvent<FlowTick>) => {
      const tick = e.detail
      if (tick.type === 'flow_tick' && tick.symbol === underlying) {
        processTick(tick)
      }
    }

    window.addEventListener('market_tick', handleMarketTick as EventListener)

    // Check for frozen state (no update for 60s)
    const frozenCheck = setInterval(() => {
      if (Date.now() - lastUpdateRef.current > 60000) {
        setIsLive(false)
      }
    }, 5000)

    return () => {
      window.removeEventListener('market_tick', handleMarketTick as EventListener)
      clearInterval(frozenCheck)
    }
  }, [underlying])

  // Initial fetch of historical data
  useEffect(() => {
    const fetchFlow = async () => {
      try {
        // Fetch last 5 minutes of data
        const resp = await fetch(`${window.location.protocol}//${window.location.host}/api/flow/${underlying}?limit=5`)
        const data = await resp.json()

        if (data.flow && data.flow.length > 0) {
          // Initialize history with fetched data
          tickHistory[underlying] = data.flow.map((f: any) => ({
            type: 'flow_tick',
            symbol: underlying,
            time: f.time,
            call_premium: f.call_premium,
            put_premium: f.put_premium,
            call_volume: f.call_volume,
            put_volume: f.put_volume,
            net_drift: f.net_drift,
          }))

          // Process the latest tick
          const latest = data.flow[0]
          processTick({
            type: 'flow_tick',
            symbol: underlying,
            time: latest.time,
            call_premium: latest.call_premium,
            put_premium: latest.put_premium,
            call_volume: latest.call_volume,
            put_volume: latest.put_volume,
            net_drift: latest.net_drift,
          })
        }
      } catch (err) {
        console.error('Failed to fetch flow data:', err)
      }
    }
    fetchFlow()
  }, [underlying])

  const formatPremium = (val: number): string => {
    const absVal = Math.abs(val)
    if (absVal >= 1e6) {
      return `$${(val / 1e6).toFixed(2)}M`
    } else if (absVal >= 1e3) {
      return `$${(val / 1e3).toFixed(0)}K`
    }
    return `$${val.toFixed(0)}`
  }

  const formatVolume = (val: number): string => {
    const absVal = Math.abs(val)
    if (absVal >= 1e3) {
      return `${(val / 1e3).toFixed(1)}K`
    }
    return `${val.toFixed(0)}`
  }

  const underlyingLabel = underlying === 'SPX' ? 'S&P 500' : 'Nasdaq 100'

  return (
    <div className="smart-money-box">
      <div className="smart-money-header">
        <span className="smart-money-title">Flow Dynamics</span>
        <span className="smart-money-underlying">{underlyingLabel}</span>
        <div className={`smart-money-status ${isLive ? 'live' : 'frozen'}`}>
          {isLive ? '🟢 LIVE' : '🟠 FROZEN'}
        </div>
      </div>

      <div className="smart-money-signal" style={{ color: signalColor, fontSize: '0.75rem' }}>
        {signal}
      </div>

      <div className="smart-money-metrics" style={{ borderBottom: '1px solid var(--border)', paddingBottom: '8px', marginBottom: '8px', display: 'flex', justifyContent: 'center' }}>
        <div className="metric" style={{ alignItems: 'center' }}>
          <span className="metric-label" title="EMA Net Drift (5m): Time-decayed institutional conviction. Recent trades weigh more.">SMART MONEY CONVICTION (EMA 5m)</span>
          <span className={`metric-value ${netDrift5m >= 0 ? 'positive' : 'negative'}`} style={{ fontWeight: 700, fontSize: '1.1rem', marginTop: '2px' }}>
            {netDrift5m > 0 ? '+' : ''}{formatPremium(netDrift5m)}
          </span>
        </div>
      </div>

      {/* EMA Net Drift 5m Conviction Gauge */}
      {(() => {
        const normalized = Math.min(1, Math.abs(netDrift5m) / drift5mPeak)
        const barWidth = normalized * 50 // max 50% each side
        const isBull = netDrift5m >= 0
        return (
          <div style={{ marginBottom: '12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.5rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '4px' }}>
              <span>BEARISH</span>
              <span>BULLISH</span>
            </div>
            <div style={{ height: '14px', display: 'flex', borderRadius: '4px', overflow: 'hidden', background: 'var(--bg-primary)', border: '1px solid var(--border)', position: 'relative' }}>
              {/* Center line */}
              <div style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, width: '1px', background: 'var(--border)', zIndex: 1 }} />
              {/* Bearish fill (grows left from center) */}
              {!isBull && (
                <div style={{
                  position: 'absolute', right: '50%', top: 0, bottom: 0,
                  width: `${barWidth}%`,
                  background: 'linear-gradient(to left, var(--danger), #7a001a)',
                  transition: 'width 0.5s ease',
                  boxShadow: '0 0 8px rgba(239,68,68,0.4)'
                }} />
              )}
              {/* Bullish fill (grows right from center) */}
              {isBull && (
                <div style={{
                  position: 'absolute', left: '50%', top: 0, bottom: 0,
                  width: `${barWidth}%`,
                  background: 'linear-gradient(to right, var(--success), #007a1e)',
                  transition: 'width 0.5s ease',
                  boxShadow: '0 0 8px rgba(16,185,129,0.4)'
                }} />
              )}
            </div>
          </div>
        )
      })()}

      <div className="meters-container" style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>

        {/* VOLUME FLOW BAR (Retail/Swarm) */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.55rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '2px' }}>
            <span>PUT VOLUME %</span>
            <span>CALL VOLUME %</span>
          </div>
          <div className="volume-bar" style={{ height: '10px', display: 'flex', borderRadius: '4px', overflow: 'hidden', background: 'var(--bg-primary)' }}>
            <div style={{ width: `${putVolPercent}%`, background: 'var(--danger)', display: 'flex', alignItems: 'center', paddingLeft: '4px', transition: 'width 0.3s ease' }}>
              <span style={{ fontSize: '0.45rem', fontWeight: 600, color: '#ffffff', textShadow: '0 0 2px #000' }}>{putVolPercent.toFixed(0)}%</span>
            </div>
            <div style={{ width: `${callVolPercent}%`, background: 'var(--success)', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', paddingRight: '4px', transition: 'width 0.3s ease' }}>
              <span style={{ fontSize: '0.45rem', fontWeight: 600, color: '#000000' }}>{callVolPercent.toFixed(0)}%</span>
            </div>
          </div>
        </div>

      </div>
    </div>
  )
}
