import React, { useState, useEffect, useRef, useCallback } from 'react'

// ─── Types ────────────────────────────────────────────────────────────

interface ComponentScore {
  score: number
  detail: string
  direction: string
}

interface ReversalSignal {
  confluence: number
  direction: 'BULLISH' | 'BEARISH' | 'NEUTRAL'
  components: {
    gex_proximity: ComponentScore
    flow_divergence: ComponentScore
    price_extension: ComponentScore
    trap_signal: ComponentScore
    gamma_regime: ComponentScore
  }
  key_level: number | null
  stop_level: number | null
  target_level: number | null
  current_price: number | null
  underlying: string
  timestamp: string
}

interface GreeksData {
  chain: Array<{
    strike: number
    option_type: string
    theta: number | null
    delta: number | null
  }>
  spot: number
}

interface ScalpingPanelProps {
  underlying: 'SPX' | 'QQQ'
}

// ─── Constants ────────────────────────────────────────────────────────

const COMPONENT_LABELS: Record<string, string> = {
  gex_proximity: 'GEX',
  flow_divergence: 'FLOW',
  price_extension: 'PRC',
  trap_signal: 'TRP',
  gamma_regime: 'GAM',
}

const API_BASE = `${window.location.protocol}//${window.location.host}`

// ─── Session phase helper ─────────────────────────────────────────────
function getSessionPhase(): { label: string; colorKey: 'early' | 'mid' | 'power' } {
  const now = new Date()
  const utcHour = now.getUTCHours()
  // ET = UTC - 5 (standard), UTC - 4 (DST). Use -5 as conservative estimate.
  const etHour = (utcHour - 5 + 24) % 24

  if (etHour < 11) {
    return { label: 'EARLY RTH', colorKey: 'early' }
  } else if (etHour < 14) {
    return { label: 'MID RTH', colorKey: 'mid' }
  } else {
    return { label: 'POWER HOUR', colorKey: 'power' }
  }
}

// ─── Countdown helper ─────────────────────────────────────────────────
function getCountdown(): string {
  const now = new Date()
  const utcHour = now.getUTCHours()
  const utcMin = now.getUTCMinutes()
  const etHour = (utcHour - 5 + 24) % 24

  if (etHour >= 16) return '0m'

  const totalMins = (16 - etHour) * 60 - utcMin
  const h = Math.floor(totalMins / 60)
  const m = totalMins % 60
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

// ─── R:R calculator ───────────────────────────────────────────────────
function calcRR(entry: number, stop: number, target: number): number | null {
  if (!entry || !stop || !target) return null
  const risk = Math.abs(entry - stop)
  const reward = Math.abs(target - entry)
  if (risk === 0) return null
  return reward / risk
}

// ─── Component dot classifier ──────────────────────────────────────────
type DotState = 'confirming' | 'weak' | 'contrarian' | 'neutral'

function classifyDot(comp: ComponentScore, overallDir: string): DotState {
  if (comp.score < 50) return 'weak'
  if (comp.direction === 'NEUTRAL') return 'neutral'
  if (comp.direction === overallDir) return 'confirming'
  return 'contrarian'
}

export const ScalpingPanel: React.FC<ScalpingPanelProps> = ({ underlying }) => {
  return null // placeholder — full render implemented in Task 4
}

export default ScalpingPanel
