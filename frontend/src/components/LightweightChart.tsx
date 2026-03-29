import React, { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import { createChart, ColorType, IChartApi, ISeriesApi, Time, CandlestickSeries, IRange } from 'lightweight-charts';
import { KeyLevels } from '../App';

interface TickData {
  type: string;
  symbol: string;
  price: number;
  volume: number;
  time: string;
}

interface CandleInput {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

interface GexLevel {
  strike: number;
  gex: number;
  futurePrice: number;
}

interface FlowConcentration {
  strike: number;
  call_premium: number;
  put_premium: number;
  net_premium: number;
  dominant: 'call' | 'put';
}

interface OILevel {
  strike: number;
  oiDelta: number;
  oiDeltaRetail: number;
  oiDeltaBlock: number;
  side: 'call' | 'put';
}

interface ChartProps {
  candles: CandleInput[];
  lastTick: TickData | null;
  gexData?: GexLevel[];
  keyLevels?: KeyLevels | null;
  flowConcentration?: FlowConcentration[];
  oiLevels?: OILevel[];
  interval?: '1m' | '5m' | '15m';
  underlying?: string;
}

export const LightweightChart: React.FC<ChartProps> = ({ candles, lastTick, gexData = [], keyLevels = null, flowConcentration = [], oiLevels = [], interval = '1m', underlying }) => {
  const API_BASE = `${window.location.protocol}//${window.location.host}`;
  const SKEW_THRESHOLD = 0.15;
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const [visibleTimeRange, setVisibleTimeRange] = useState<IRange<number> | null>(null);
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 });
  const [skewZones, setSkewZones] = useState<Array<{strike: number; skew: number; type: 'put' | 'call'}>>([]);

  // Create chart
  useEffect(() => {
    if (!containerRef.current) return;

    const nyTimeFormatter = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/New_York',
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
    });

    const nyDateFormatter = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/New_York',
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#94a3b8',
      },
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight || 500,
      grid: {
        vertLines: { color: 'rgba(30, 41, 59, 0.5)' },
        horzLines: { color: 'rgba(30, 41, 59, 0.5)' },
      },
      crosshair: { mode: 0 },
      rightPriceScale: {
        borderColor: '#1e293b',
        scaleMargins: { top: 0.05, bottom: 0.05 },
      },
      localization: {
        timeFormatter: (time: number) => {
          const date = new Date(time * 1000);
          return `${nyDateFormatter.format(date)} ${nyTimeFormatter.format(date)} (ET)`;
        },
      },
      timeScale: {
        borderColor: '#1e293b',
        timeVisible: true,
        secondsVisible: false,
        tickMarkFormatter: (time: number, tickMarkType: any, locale: string) => {
          return nyTimeFormatter.format(new Date(time * 1000));
        },
      },
    });

    chartRef.current = chart;

    const series = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#ef4444', // Vibrant Red
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
      autoscaleInfoProvider: (original: () => any) => {
        const res = original();
        if (res && res.priceRange !== null) {
          const range = res.priceRange.maxValue - res.priceRange.minValue;
          // Provide a 1% minimum visual auto scale range for flat markets
          if (range < res.priceRange.maxValue * 0.01) {
            const padding = res.priceRange.maxValue * 0.005;
            res.priceRange.minValue -= padding;
            res.priceRange.maxValue += padding;
          }
        }
        return res;
      }
    });
    seriesRef.current = series as any;

    // Subscribe to time scale changes (zoom/pan)
    chart.timeScale().subscribeVisibleTimeRangeChange((range) => {
      if (range) {
        setVisibleTimeRange({ from: range.from as number, to: range.to as number });
      }
    });

    // Resize handler
    const handleResize = () => {
      if (containerRef.current && chartRef.current) {
        const width = containerRef.current.clientWidth;
        const height = containerRef.current.clientHeight || 500;
        chartRef.current.applyOptions({ width, height });
        setContainerSize({ width, height });
      }
    };

    const resizeObserver = new ResizeObserver(() => {
      handleResize();
    });

    resizeObserver.observe(containerRef.current);

    setContainerSize({
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight || 500
    });

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  // Update candles
  const currentCandleRef = useRef<CandleInput | null>(null);

  useEffect(() => {
    if (seriesRef.current && candles.length > 0) {
      const formattedData = candles.map(c => ({
        time: c.time as Time,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }));
      seriesRef.current.setData(formattedData);
      chartRef.current?.timeScale().fitContent();
      currentCandleRef.current = candles[candles.length - 1];
    }
  }, [candles]);

  // Real-time tick update
  useEffect(() => {
    if (!seriesRef.current || !lastTick || !currentCandleRef.current) return;

    try {
      const tickTimeMs = new Date(lastTick.time).getTime();
      if (isNaN(tickTimeMs)) return;

      const now = Math.floor(tickTimeMs / 1000);

      // Calculate bucket size based on interval
      const intervalSeconds: Record<string, number> = {
        '1m': 60,
        '5m': 300,
        '15m': 900,
      };
      const bucketSize = intervalSeconds[interval] || 60;
      const bucketTs = now - (now % bucketSize);

      let currentCandle = currentCandleRef.current;

      if (bucketTs > currentCandle.time) {
        currentCandle = { time: bucketTs, open: lastTick.price, high: lastTick.price, low: lastTick.price, close: lastTick.price };
      } else {
        currentCandle = {
          ...currentCandle,
          high: Math.max(currentCandle.high, lastTick.price),
          low: Math.min(currentCandle.low, lastTick.price),
          close: lastTick.price,
        };
      }

      currentCandleRef.current = currentCandle;
      seriesRef.current.update({
        time: currentCandle.time as Time,
        open: currentCandle.open,
        high: currentCandle.high,
        low: currentCandle.low,
        close: currentCandle.close,
      });
    } catch (e) {
      console.error("Chart update error:", e);
    }
  }, [lastTick, interval]);

  // Calculate visible candles and price range

  const fetchSkewZones = useCallback(async (und: string) => {
    try {
      const resp = await fetch(`${API_BASE}/api/volatility/surface?underlying=${und}`);
      const data = await resp.json();
      if (!data.surface?.length) return;
      const strikes = data.surface[0]?.strikes || [];
      const spot = data.spot_price || 0;
      if (!spot) return;

      const zones: Array<{strike: number; skew: number; type: 'put' | 'call'}> = [];
      for (const s of strikes) {
        if (s.skew == null || s.call_iv == null || s.put_iv == null) continue;
        if (Math.abs(s.skew) > SKEW_THRESHOLD) {
          zones.push({ strike: s.strike, skew: s.skew, type: s.skew > 0 ? 'put' : 'call' });
        }
      }

      zones.sort((a, b) => {
        if (a.type === 'put' && b.type === 'put') return b.skew - a.skew;
        if (a.type === 'call' && b.type === 'call') return a.skew - b.skew;
        return 0;
      });

      const puts = zones.filter(z => z.type === 'put').slice(0, 3);
      const calls = zones.filter(z => z.type === 'call').slice(0, 3);
      setSkewZones([...puts, ...calls]);
    } catch (e) { }
  }, []);

  useEffect(() => {
    if (underlying) {
      let mounted = true;
      fetchSkewZones(underlying);
      const interval = setInterval(() => {
        if (mounted) fetchSkewZones(underlying);
      }, 120000);
      return () => {
        mounted = false;
        clearInterval(interval);
      };
    }
  }, [underlying, fetchSkewZones]);

  const { rangeMin, rangeMax } = useMemo(() => {
    let visibleCandles = candles;

    // Filter by visible time range if available
    if (visibleTimeRange) {
      visibleCandles = candles.filter(c =>
        c.time >= visibleTimeRange.from && c.time <= visibleTimeRange.to
      );
    }

    if (visibleCandles.length === 0) {
      visibleCandles = candles.slice(-100);
    }

    let minPrice = Infinity;
    let maxPrice = -Infinity;
    visibleCandles.forEach(c => {
      if (c.low < minPrice) minPrice = c.low;
      if (c.high > maxPrice) maxPrice = c.high;
    });

    if (minPrice === Infinity || maxPrice === -Infinity) {
      if (candles.length > 0) {
        minPrice = candles[0].low;
        maxPrice = candles[0].high;
      } else {
        minPrice = 100;
        maxPrice = 100;
      }
    }

    let priceRange = maxPrice - minPrice;
    if (priceRange <= 0) {
      priceRange = minPrice * 0.01; // Provide a 1% fallback range for completely flat markets
    }

    return {
      rangeMin: minPrice - priceRange * 0.05,
      rangeMax: maxPrice + priceRange * 0.05
    };
  }, [candles, visibleTimeRange]);

  const totalRange = rangeMax - rangeMin;

  // Chart area dimensions
  const marginTop = containerSize.height * 0.05;
  const marginBottom = containerSize.height * 0.05;
  const chartAreaHeight = containerSize.height - marginTop - marginBottom;

  // Convert price to Y coordinate
  const priceToY = useCallback((price: number): number | null => {
    if (totalRange === 0 || chartAreaHeight === 0) return null;
    const normalized = (price - rangeMin) / totalRange;
    return marginTop + chartAreaHeight * (1 - normalized);
  }, [rangeMin, totalRange, marginTop, chartAreaHeight]);

  // Calculate max GEX for scaling
  const maxGex = useMemo(() => {
    return gexData.length > 0 ? Math.max(...gexData.map(g => Math.abs(g.gex))) : 0;
  }, [gexData]);

  // Key Levels + Flow Concentration Canvas Drawing
  useEffect(() => {
    if (!canvasRef.current || !seriesRef.current) return;

    const canvas = canvasRef.current;
    canvas.width = containerSize.width;
    canvas.height = containerSize.height;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let lastYMap = '';

    const drawOverlay = () => {
      if (!seriesRef.current) return;

      const width = canvas.width;
      const height = canvas.height;

      // Build fingerprint from key level prices + concentration strikes
      const kp = keyLevels
        ? [keyLevels.zgl, keyLevels.call_wall, keyLevels.put_wall, keyLevels.top_call, keyLevels.top_put]
            .filter(Boolean)
            .map(l => l!.price)
        : [];
      const cp = (flowConcentration || []).map(l => l.strike);
      const currentYMap = [...kp, ...cp]
        .map(p => seriesRef.current!.priceToCoordinate(p))
        .join('_');
      if (currentYMap === lastYMap) return;
      lastYMap = currentYMap;

      ctx.clearRect(0, 0, width, height);

      // Base background
      ctx.fillStyle = '#0a0e17';
      ctx.fillRect(0, 0, width, height);

      if (!keyLevels) return;

      // ── Key GEX levels ──────────────────────────────────────────────────
      const gexLevels: Array<{
        level: { price: number; label: string; type: string } | null;
        color: string;
        opacity: number;
        lineWidth: number;
        dashed: boolean;
        labelPrefix: string;
      }> = [
        { level: keyLevels.zgl, color: '#FFB300', opacity: 1.0, lineWidth: 2, dashed: false, labelPrefix: '0GEX' },
        { level: keyLevels.call_wall, color: '#22C55E', opacity: 1.0, lineWidth: 1.5, dashed: false, labelPrefix: 'CW' },
        { level: keyLevels.put_wall, color: '#EF4444', opacity: 1.0, lineWidth: 1.5, dashed: false, labelPrefix: 'PW' },
        { level: keyLevels.top_call, color: '#22C55E', opacity: 0.5, lineWidth: 1, dashed: true, labelPrefix: 'C' },
        { level: keyLevels.top_put, color: '#EF4444', opacity: 0.5, lineWidth: 1, dashed: true, labelPrefix: 'P' },
      ];

      const drawLine = (price: number, color: string, opacity: number, lw: number, dashed: boolean, prefix: string) => {
        const y = seriesRef.current!.priceToCoordinate(price);
        if (y === null || y < 0 || y > height) return;
        const r = parseInt(color.slice(1, 3), 16);
        const g = parseInt(color.slice(3, 5), 16);
        const b = parseInt(color.slice(5, 7), 16);
        const rgba = `rgba(${r},${g},${b},${opacity})`;

        ctx.beginPath();
        ctx.strokeStyle = rgba;
        ctx.lineWidth = lw;
        ctx.setLineDash(dashed ? [8, 5] : []);
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
        ctx.setLineDash([]);

        const labelText = `${prefix}: ${price.toFixed(0)}`;
        ctx.font = '11px monospace';
        const tm = ctx.measureText(labelText);
        const pad = 4;
        const lx = width - tm.width - pad * 2 - 60;
        const ly = y - 3;
        ctx.fillStyle = 'rgba(10,14,23,0.85)';
        ctx.fillRect(lx - pad, ly - 11, tm.width + pad * 2, 15);
        ctx.fillStyle = rgba;
        ctx.fillText(labelText, lx, ly);
      };

      for (const { level, color, opacity, lineWidth, dashed, labelPrefix } of gexLevels) {
        if (level) drawLine(level.price, color, opacity, lineWidth, dashed, labelPrefix);
      }

      // ── Flow Concentration levels ──────────────────────────────────────
      if (flowConcentration && flowConcentration.length > 0) {
        // Find max premium for scaling line width
        const maxPremium = Math.max(...flowConcentration.map(l => Math.max(l.call_premium, l.put_premium)));
        const MIN_LW = 1;
        const MAX_LW = 3;

        for (const level of flowConcentration) {
          const y = seriesRef.current!.priceToCoordinate(level.strike);
          if (y === null || y < 0 || y > height) continue;

          const isCall = level.dominant === 'call';
          const premium = isCall ? level.call_premium : level.put_premium;
          const color = isCall ? '#F97316' : '#3B82F6'; // orange=call, blue=put
          const lineWidth = MIN_LW + (premium / maxPremium) * (MAX_LW - MIN_LW);
          const opacity = 0.7;
          const prefix = isCall ? 'CALL' : 'PUT';
          const r = parseInt(color.slice(1, 3), 16);
          const g = parseInt(color.slice(3, 5), 16);
          const b = parseInt(color.slice(5, 7), 16);
          const rgba = `rgba(${r},${g},${b},${opacity})`;

          // Thin dashed line
          ctx.beginPath();
          ctx.strokeStyle = rgba;
          ctx.lineWidth = lineWidth;
          ctx.setLineDash([4, 4]);
          ctx.moveTo(0, y);
          ctx.lineTo(width, y);
          ctx.stroke();
          ctx.setLineDash([]);

          // Label with premium
          const premiumLabel = premium >= 1e6
            ? `$${(premium / 1e6).toFixed(1)}M`
            : `$${(premium / 1e3).toFixed(0)}K`;
          const labelText = `${prefix} ${level.strike.toFixed(0)} ${premiumLabel}`;
          ctx.font = '10px monospace';
          const tm = ctx.measureText(labelText);
          const pad = 3;
          const lx = 4; // left edge for concentration labels
          const ly = y - 2;
          ctx.fillStyle = 'rgba(10,14,23,0.8)';
          ctx.fillRect(lx - pad, ly - 10, tm.width + pad * 2, 13);
          ctx.fillStyle = rgba;
          ctx.fillText(labelText, lx, ly);
        }
      }

      // ── Skew Zones ──────────────────────────────────────────────────────────────
      const drawSkewZones = () => {
        if (!seriesRef.current || !skewZones.length || !keyLevels) return;

        const SKEW_THRESHOLD = 0.15;

        for (const zone of skewZones) {
          const strike = zone.strike;
          // Translate strike to future price using existing gexData (already computed with correct additive/multiplicative logic)
          let futurePrice = strike;
          const strikeData = gexData.find(g => Math.abs(g.strike - strike) < 1);
          if (strikeData?.futurePrice) {
            futurePrice = strikeData.futurePrice;
          } else {
            // Fallback: estimate from zgl and call_wall
            if (keyLevels?.zgl?.price && keyLevels?.call_wall?.price) {
              const mult = keyLevels.call_wall.price / keyLevels.zgl.price;
              const zglStrike = keyLevels.zgl.price / mult;
              futurePrice = strike * mult + (keyLevels.zgl.price - zglStrike);
            }
          }

          const y = seriesRef.current.priceToCoordinate(futurePrice);
          if (y === null || y < 0 || y > height) return;

          const isPut = zone.type === 'put';
          const color = isPut ? '#ef4444' : '#3b82f6';
          const skewPct = (Math.abs(zone.skew) * 100).toFixed(0);
          const prefix = isPut ? 'PUT' : 'CALL';

          ctx.beginPath();
          ctx.strokeStyle = color;
          ctx.lineWidth = 1;
          ctx.setLineDash([6, 4]);
          ctx.globalAlpha = 0.7;
          ctx.moveTo(0, y);
          ctx.lineTo(width, y);
          ctx.stroke();
          ctx.setLineDash([]);
          ctx.globalAlpha = 1;

          const labelText = `${prefix} ${strike.toFixed(0)} ${skewPct}%`;
          ctx.font = '9px monospace';
          const tm = ctx.measureText(labelText);
          ctx.fillStyle = 'rgba(10,14,23,0.85)';
          ctx.fillRect(4, y - 10, tm.width + 6, 13);
          ctx.fillStyle = color;
          ctx.fillText(labelText, 6, y);
        }
      };

      drawSkewZones();

      // ── OI Buildup Levels ───────────────────────────────────────────
      if (oiLevels && oiLevels.length > 0 && seriesRef.current) {
        const maxDelta = Math.max(...oiLevels.map(l => Math.abs(l.oiDelta)));
        if (maxDelta > 0) {
          for (const level of oiLevels) {
            // Translate strike to future price using gexData
            let futurePrice = level.strike;
            const strikeData = gexData.find(g => Math.abs(g.strike - level.strike) < 1);
            if (strikeData?.futurePrice) {
              futurePrice = strikeData.futurePrice;
            } else if (keyLevels?.call_wall?.price && keyLevels?.zgl?.price) {
              const mult = keyLevels.call_wall.price / keyLevels.zgl.price;
              futurePrice = level.strike * mult + keyLevels.zgl.price - level.strike;
            }

            const y = seriesRef.current.priceToCoordinate(futurePrice);
            if (y === null || y < 0 || y > height) continue;

            const isCall = level.side === 'call';
            const color = isCall ? '#00C853' : '#FF1744';
            const opacity = 0.6;
            const isBlockOnly = Math.abs(level.oiDeltaBlock) > Math.abs(level.oiDeltaRetail);
            const dashed = isBlockOnly;
            const prefix = isCall ? 'C' : 'P';

            const r = parseInt(color.slice(1, 3), 16);
            const g = parseInt(color.slice(3, 5), 16);
            const b = parseInt(color.slice(5, 7), 16);
            const rgba = `rgba(${r},${g},${b},${opacity})`;

            ctx.beginPath();
            ctx.strokeStyle = rgba;
            ctx.lineWidth = 1.5;
            ctx.setLineDash(dashed ? [6, 4] : []);
            ctx.moveTo(0, y);
            ctx.lineTo(width, y);
            ctx.stroke();
            ctx.setLineDash([]);

            // Label
            const labelText = `${prefix} ${level.strike.toFixed(0)} ${level.oiDelta >= 0 ? '+' : ''}${level.oiDelta}`;
            ctx.font = '10px monospace';
            const tm = ctx.measureText(labelText);
            const lx = 4;
            const ly = y - 2;
            ctx.fillStyle = 'rgba(10,14,23,0.85)';
            ctx.fillRect(lx - 3, ly - 10, tm.width + 6, 13);
            ctx.fillStyle = rgba;
            ctx.fillText(labelText, lx, ly);
          }
        }
      }

      // Schedule next frame at the END so we only continue when we actually drew
      animationFrameId = requestAnimationFrame(drawOverlay);
    };

    drawOverlay();

    return () => {
      cancelAnimationFrame(animationFrameId);
    };
  }, [keyLevels, flowConcentration, containerSize, skewZones, oiLevels]);

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', minHeight: '400px', backgroundColor: '#0a0e17' }}>
      {/* Background Heatmap Canvas */}
      <canvas
        ref={canvasRef}
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          zIndex: 1
        }}
      />

      {/* Chart Container */}
      <div
        ref={containerRef}
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          zIndex: 2
        }}
      />

    </div>
  );
};
