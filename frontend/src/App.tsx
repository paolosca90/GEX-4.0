import React, { useState, useEffect, useRef } from 'react'
import { LightweightChart } from './components/LightweightChart'
import { SmartMoneyBox } from './components/SmartMoneyBox'
import './App.css'
import { GreeksPanel } from './components/GreeksPanel'
import { AlertsPanel } from './components/AlertsPanel'
import { DarkPoolPanel } from './components/DarkPoolPanel'
import { ReversalGauge } from './components/ReversalGauge'
import { VolSurface } from './components/VolSurface'
import logo from './assets/gex.png'

const API_BASE = `${window.location.protocol}//${window.location.host}`
const WS_BASE = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`

type CandleData = {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume?: number
}

type TickData = {
  type: string
  symbol: string
  price: number
  volume: number
  time: string
}

// Chart panel component for each symbol
interface ChartPanelProps {
  symbol: string
  underlying: string
  label: string
  isExpanded: boolean
  onExpandToggle: () => void
}

type GexLevel = {
  strike: number
  gex: number
  futurePrice: number
}

export interface KeyLevel {
  price: number
  gex?: number
  label: string
  type: 'zero_gamma' | 'call' | 'put'
}

export interface KeyLevels {
  zgl: KeyLevel | null
  call_wall: KeyLevel | null
  put_wall: KeyLevel | null
  top_call: KeyLevel | null
  top_put: KeyLevel | null
}

export interface FlowConcentration {
  strike: number
  call_premium: number
  put_premium: number
  net_premium: number
  dominant: 'call' | 'put'
}

const ChartPanel: React.FC<ChartPanelProps> = ({ symbol, underlying, label, isExpanded, onExpandToggle }) => {
  const [candles, setCandles] = useState<CandleData[]>([])
  const [lastTick, setLastTick] = useState<TickData | null>(null)
  const [lastPrice, setLastPrice] = useState<number | null>(null)
  const [gexData, setGexData] = useState<GexLevel[]>([])
  const [keyLevels, setKeyLevels] = useState<KeyLevels | null>(null)
  const [flowConcentration, setFlowConcentration] = useState<FlowConcentration[]>([])

  // Timeframe state
  const [intervalOption, setIntervalOption] = useState<'1m' | '5m' | '15m'>('1m')

  // Draggable overlay state
  const [pos, setPos] = useState({ x: 10, y: 10 })
  const [dragging, setDragging] = useState(false)
  const [rel, setRel] = useState({ x: 0, y: 0 })

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    // Only drag on left click or touch
    if (e.button !== 0 && e.nativeEvent.type !== 'touchstart') return
    const target = e.target as HTMLElement
    // Prevent dragging if clicking on an interactive element inside
    if (['BUTTON', 'A', 'INPUT'].includes(target.tagName)) return

    // Capture pointer to allow dragging outside bounds
    e.currentTarget.setPointerCapture(e.pointerId)

    setDragging(true)
    setRel({
      x: e.pageX - pos.x,
      y: e.pageY - pos.y
    })
    e.stopPropagation()
  }

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragging) return
    setPos({
      x: e.pageX - rel.x,
      y: e.pageY - rel.y
    })
    e.stopPropagation()
  }

  const onPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    setDragging(false)
    e.currentTarget.releasePointerCapture(e.pointerId)
    e.stopPropagation()
  }

  const zeroGamma = React.useMemo(() => {
    if (keyLevels?.zgl) return keyLevels.zgl.price.toFixed(0)
    return null
  }, [keyLevels])

  useEffect(() => {
    const fetchCandles = async () => {
      try {
        const resp = await fetch(`${API_BASE}/api/candles/${symbol}?interval=${intervalOption}&limit=500`)
        const data = await resp.json()
        if (data.candles && data.candles.length > 0) {
          setCandles(data.candles)
          setLastPrice(data.candles[data.candles.length - 1].close)
        }
      } catch (err) {
        console.error('Failed to fetch candles:', err)
      }
    }
    fetchCandles()
  }, [symbol, intervalOption])

  // Fetch GEX data
  useEffect(() => {
    const fetchGex = async () => {
      try {
        const resp = await fetch(`${API_BASE}/api/gex/latest?underlying=${underlying}`)
        const data = await resp.json()
        if (data.gex && data.gex.length > 0) {
          setGexData(data.gex)
        }
        if (data.key_levels) {
          setKeyLevels(data.key_levels)
        }
      } catch (err) {
        console.error('Failed to fetch GEX:', err)
      }
    }
    fetchGex()
    const interval = setInterval(fetchGex, 60000)
    return () => clearInterval(interval)
  }, [underlying])

  // Fetch flow concentration (aggregated by strike from our Tradier flow data)
  useEffect(() => {
    const fetchConcentration = async () => {
      try {
        const resp = await fetch(`${API_BASE}/api/flow/concentration/${underlying}?bars=5&lookback_minutes=1440`)
        const data = await resp.json()
        if (data.concentration && data.concentration.length > 0) {
          setFlowConcentration(data.concentration)
        }
      } catch (err) {
        console.error('Failed to fetch flow concentration:', err)
      }
    }
    fetchConcentration()
    const interval = setInterval(fetchConcentration, 120000) // refresh every 2 min
    return () => clearInterval(interval)
  }, [underlying])

  useEffect(() => {
    const handleMarketTick = (e: CustomEvent<TickData>) => {
      const msg = e.detail
      if (msg.type === 'tick' && msg.symbol === symbol) {
        setLastTick(msg)
        setLastPrice(msg.price)
      }
    }
    window.addEventListener('market_tick', handleMarketTick as EventListener)
    return () => {
      window.removeEventListener('market_tick', handleMarketTick as EventListener)
    }
  }, [symbol])

  return (
    <div className="chart-panel">
      <div className="panel-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.8rem' }}>
          <h2>{label}</h2>
          <div className="timeframe-selector">
            {(['1m', '5m', '15m'] as const).map(tf => (
              <button
                key={tf}
                className={`timeframe-btn ${intervalOption === tf ? 'active' : ''}`}
                onClick={() => setIntervalOption(tf)}
              >
                {tf}
              </button>
            ))}
            <button
              className="timeframe-btn"
              onClick={onExpandToggle}
              title={isExpanded ? "Collapse" : "Expand"}
            >
              {isExpanded ? '\u26F6' : '\u26F6'}
            </button>
          </div>
          {zeroGamma && <span className="zero-gamma-label" title="Zero Gamma Level">0GEX: {zeroGamma}</span>}
        </div>
        {lastPrice && <span className="panel-price">{lastPrice.toFixed(2)}</span>}
      </div>
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <div className="chart-container" style={{ flex: 1 }}>
          <div className="chart-main">
            <LightweightChart candles={candles} lastTick={lastTick} gexData={gexData} keyLevels={keyLevels} flowConcentration={flowConcentration} />
            <div
              className="smart-money-overlay"
              style={{ left: pos.x, top: pos.y }}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerCancel={onPointerUp}
            >
              <SmartMoneyBox underlying={underlying} />
            </div>
          </div>
        </div>
        <div className="sidebar-panel" style={{ padding: '0.5rem', overflowY: 'auto' }}>
          <ReversalGauge underlying={underlying} />
          <VolSurface underlying={underlying} />
          <GreeksPanel underlying={underlying} />
          <AlertsPanel />
          <DarkPoolPanel underlying={underlying} />
        </div>
      </div>
    </div>
  )
}

function App() {
  const [connected, setConnected] = useState(false)
  const [expandedChart, setExpandedChart] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    const connect = () => {
      const ws = new WebSocket(`${WS_BASE}/ws/market_data`)
      ws.onopen = () => {
        console.log('WebSocket connected')
        setConnected(true)
      }
      ws.onmessage = (event) => {
        try {
          const msg: TickData = JSON.parse(event.data)
          if (msg.type === 'tick' || msg.type === 'flow_tick' || msg.type === 'reversal_signal') {
            window.dispatchEvent(new CustomEvent('market_tick', { detail: msg }))
          }
          if (msg.type === 'alert') {
            window.dispatchEvent(new CustomEvent('alert', { detail: msg }))
          }
        } catch (e) { }
      }
      ws.onclose = () => {
        setConnected(false)
        setTimeout(connect, 3000)
      }
      ws.onerror = () => ws.close()
      wsRef.current = ws
    }
    connect()
    return () => { wsRef.current?.close() }
  }, [])

  return (
    <div className="dashboard-container">
      <header className="dashboard-header">
        <div className="header-left">
          <img src={logo} alt="QuantumGEX Logo" className="header-logo" />
        </div>
        <div className="header-right">
          <div className={`status-indicator ${connected ? 'connected' : 'disconnected'}`}>
            {connected ? 'LIVE' : 'Offline'}
          </div>
        </div>
      </header>
      <main className="dashboard-content">
        {expandedChart !== 'NAS100-F' && (
          <ChartPanel
            symbol="US500-F"
            underlying="SPX"
            label="ES / S&P 500"
            isExpanded={expandedChart === 'US500-F'}
            onExpandToggle={() => setExpandedChart(expandedChart === 'US500-F' ? null : 'US500-F')}
          />
        )}
        {expandedChart !== 'US500-F' && (
          <ChartPanel
            symbol="NAS100-F"
            underlying="QQQ"
            label="NQ / Nasdaq 100"
            isExpanded={expandedChart === 'NAS100-F'}
            onExpandToggle={() => setExpandedChart(expandedChart === 'NAS100-F' ? null : 'NAS100-F')}
          />
        )}
      </main>
    </div>
  )
}

export default App
