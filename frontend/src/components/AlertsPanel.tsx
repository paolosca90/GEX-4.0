import React, { useState, useEffect } from 'react'

interface Alert {
  id: number
  time: string
  underlying: string
  alert_type: string
  severity: string
  direction: string
  trigger_price: number | null
  level_price: number | null
  message: string
}

const SEVERITY_ICON: Record<string, string> = {
  HIGH: '\u{1F534}',
  MEDIUM: '\u{1F7E1}',
  LOW: '\u{1F7E2}',
}

const SEVERITY_COLOR: Record<string, string> = {
  HIGH: 'var(--danger)',
  MEDIUM: 'var(--warning)',
  LOW: 'var(--success)',
}

const TYPE_LABELS: Record<string, string> = {
  zgl_proximity: 'ZGL Proximity',
  wall_test: 'Wall Test',
  flow_spike: 'Flow Spike',
  gamma_flip: 'Gamma Flip',
  momentum_reversal: 'Momentum Rev',
  dix_extreme: 'DIX Extreme',
}

export const AlertsPanel: React.FC = () => {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [badgeCount, setBadgeCount] = useState(0)

  useEffect(() => {
    const fetchAlerts = async () => {
      try {
        const base = `${window.location.protocol}//${window.location.host}`
        const resp = await fetch(`${base}/api/alerts?limit=50`)
        if (resp.ok) {
          const data = await resp.json()
          setAlerts(data.alerts || [])
          setBadgeCount((data.alerts || []).filter((a: Alert) => a.severity === 'HIGH').length)
        }
      } catch (err) {
        console.error('Alerts fetch error:', err)
      }
    }
    fetchAlerts()
    const interval = setInterval(fetchAlerts, 30000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    const handleAlert = (e: CustomEvent) => {
      const alert = e.detail?.data
      if (!alert) return
      setAlerts(prev => [alert, ...prev].slice(0, 50))
      if (alert.severity === 'HIGH') {
        setBadgeCount(prev => prev + 1)
      }
    }
    window.addEventListener('alert', handleAlert as EventListener)
    return () => window.removeEventListener('alert', handleAlert as EventListener)
  }, [])

  const formatTime = (isoStr: string): string => {
    try {
      const d = new Date(isoStr)
      return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })
    } catch {
      return ''
    }
  }

  return (
    <div className="sidebar-card">
      <div className="sidebar-card-header">
        <span className="sidebar-card-title">Alerts</span>
        {badgeCount > 0 && (
          <span className="alert-badge">{badgeCount} new</span>
        )}
      </div>
      <div className="alert-list">
        {alerts.length === 0 ? (
          <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', padding: '8px 0' }}>
            No alerts yet
          </div>
        ) : (
          alerts.slice(0, 10).map((alert) => (
            <div key={alert.id || alert.time} className="alert-item">
              <span className="alert-icon">{SEVERITY_ICON[alert.severity] || '\u26AA'}</span>
              <div className="alert-content">
                <div className="alert-type" style={{ color: SEVERITY_COLOR[alert.severity] }}>
                  {TYPE_LABELS[alert.alert_type] || alert.alert_type}
                </div>
                <div className="alert-message">{alert.message}</div>
              </div>
              <span className="alert-time">{formatTime(alert.time)}</span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}