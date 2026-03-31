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
      const price = lastTick.price;

      // Calculate bucket size based on interval
      const intervalSeconds: Record<string, number> = {
        '1m': 60,
        '5m': 300,
        '15m': 900,
      };
      const bucketSize = intervalSeconds[interval] || 60;
      const bucketTs = now - (now % bucketSize);

      let currentCandle = currentCandleRef.current;
      const isNewBucket = bucketTs > currentCandle.time;

      // ALWAYS validate tick price against last close (previous candle's close)
      // This prevents bad first-tick of new bucket from creating a giant candle
      const lastClose = currentCandle.close;
      if (price < lastClose * 0.9 || price > lastClose * 1.1) {
        // Discard outlier tick (likely bad data from API/daemon)
        return;
      }

      if (isNewBucket) {
        currentCandle = { time: bucketTs, open: price, high: price, low: price, close: price };
      } else {
        currentCandle = {
          ...currentCandle,
          high: Math.max(currentCandle.high, price),
          low: Math.min(currentCandle.low, price),
          close: price,
        };
      }

      // Discard candle if high-low range exceeds 1% of close (anomalous candle guard)
      if (currentCandle.close > 0) {
        const rangePct = (currentCandle.high - currentCandle.low) / currentCandle.close;
        if (rangePct > 0.01) {
          // Skip this tick — would create an anomalously large candle
          return;
        }
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

  // Translate a raw strike to future price for overlay positioning
  // Uses gexData (preferred) or falls back to keyLevels ratio formula
  const strikeToFuturePrice = useCallback((strike: number): number => {
    // Preferred: use gexData which has exact futurePrice computed by backend
    const strikeData = gexData.find(g => Math.abs(g.strike - strike) < 1);
    if (strikeData?.futurePrice) return strikeData.futurePrice;

    // Fallback: use keyLevels ratio to translate strike → future price
    // Works for both additive (SPX: offset = CW - ZGL) and multiplicative (QQQ: mult = CW/ZGL)
    if (keyLevels?.zgl?.price && keyLevels?.call_wall?.price) {
      const zglPrice = keyLevels.zgl.price;
      const cwPrice = keyLevels.call_wall.price;
      const mult = cwPrice / zglPrice;  // ≈ 1 for SPX additive, ≈ 41.8 for QQQ multiplicative
      const zglStrike = zglPrice / mult; // strike that maps to ZGL in future price space
      return strike * mult + (zglPrice - zglStrike);  // simplifies to strike*mult for QQQ (offset≈0)
    }

    return strike;  // fallback to raw strike
  }, [gexData, keyLevels]);

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

      // Build fingerprint from key level prices + concentration strikes (translated to future prices)
      const kp = keyLevels
        ? [keyLevels.zgl, keyLevels.call_wall, keyLevels.put_wall, keyLevels.top_call, keyLevels.top_put]
            .filter(Boolean)
            .map(l => l!.price)
        : [];
      const cp = (flowConcentration || []).map(l => strikeToFuturePrice(l.strike));
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

      // ── Flow Concentration ZONES ──────────────────────────────────────
      // Cluster nearby lines into zones to avoid visual overlap
      if (flowConcentration && flowConcentration.length > 0) {
        const ZONE_PIXELS = 10; // Merge lines within 10px into a zone

        // Convert to Y coordinates
        const withY = flowConcentration
          .map(level => ({
            level,
            futurePrice: strikeToFuturePrice(level.strike),
            y: seriesRef.current!.priceToCoordinate(strikeToFuturePrice(level.strike)),
          }))
          .filter((l): l is typeof l & { y: number } => l.y !== null && l.y >= 0 && l.y <= height);

        if (withY.length === 0) return;

        // Sort by Y (ascending = higher prices at top visually)
        withY.sort((a, b) => b.y - a.y);

        // Cluster into zones
        interface Zone {
          levels: typeof withY;
          minY: number;
          maxY: number;
          dominant: 'call' | 'put';
          totalCallPremium: number;
          totalPutPremium: number;
          strikeRange: string;
        }

        const zones: Zone[] = [];
        let currentZone: Zone | null = null;

        for (const item of withY) {
          const isCall = item.level.dominant === 'call';
          const premium = isCall ? item.level.call_premium : item.level.put_premium;

          if (!currentZone) {
            currentZone = {
              levels: [item],
              minY: item.y,
              maxY: item.y,
              dominant: item.level.dominant,
              totalCallPremium: item.level.call_premium,
              totalPutPremium: item.level.put_premium,
              strikeRange: `${item.level.strike.toFixed(0)}`,
            };
          } else if (Math.abs(item.y - currentZone.maxY) <= ZONE_PIXELS) {
            // Same zone
            currentZone.levels.push(item);
            currentZone.maxY = Math.max(currentZone.maxY, item.y);
            currentZone.totalCallPremium += item.level.call_premium;
            currentZone.totalPutPremium += item.level.put_premium;
            currentZone.strikeRange = `${currentZone.levels[0].level.strike.toFixed(0)}-${item.level.strike.toFixed(0)}`;
          } else {
            // New zone
            zones.push(currentZone);
            currentZone = {
              levels: [item],
              minY: item.y,
              maxY: item.y,
              dominant: item.level.dominant,
              totalCallPremium: item.level.call_premium,
              totalPutPremium: item.level.put_premium,
              strikeRange: `${item.level.strike.toFixed(0)}`,
            };
          }
        }
        if (currentZone) zones.push(currentZone);

        // Draw zones
        const maxPremium = Math.max(...zones.map(z =>
          z.dominant === 'call' ? z.totalCallPremium : z.totalPutPremium
        ));

        for (const zone of zones) {
          const isCall = zone.dominant === 'call';
          const premium = isCall ? zone.totalCallPremium : zone.totalPutPremium;
          const color = isCall ? '#F97316' : '#3B82F6';
          const zoneTop = Math.min(zone.minY, zone.maxY);
          const zoneBottom = Math.max(zone.minY, zone.maxY);
          const zoneHeight = Math.max(zoneBottom - zoneTop, 4); // Min height

          const r = parseInt(color.slice(1, 3), 16);
          const g = parseInt(color.slice(3, 5), 16);
          const b = parseInt(color.slice(5, 7), 16);

          // Draw zone band
          const alpha = 0.25 + (premium / maxPremium) * 0.15;
          ctx.fillStyle = `rgba(${r},${g},${b},${alpha})`;
          ctx.fillRect(0, zoneTop, width, zoneHeight);

          // Draw zone borders (solid)
          ctx.strokeStyle = `rgba(${r},${g},${b},0.6)`;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(0, zoneTop);
          ctx.lineTo(width, zoneTop);
          ctx.moveTo(0, zoneBottom);
          ctx.lineTo(width, zoneBottom);
          ctx.stroke();

          // Draw center line
          const centerY = zoneTop + zoneHeight / 2;
          ctx.beginPath();
          ctx.strokeStyle = `rgba(${r},${g},${b},0.8)`;
          ctx.lineWidth = 1;
          ctx.setLineDash([3, 3]);
          ctx.moveTo(0, centerY);
          ctx.lineTo(width, centerY);
          ctx.stroke();
          ctx.setLineDash([]);

          // Label
          const totalPremium = zone.totalCallPremium + zone.totalPutPremium;
          const premiumLabel = totalPremium >= 1e6
            ? `$${(totalPremium / 1e6).toFixed(1)}M`
            : `$${(totalPremium / 1e3).toFixed(0)}K`;
          const prefix = isCall ? 'CALL' : 'PUT';
          const labelText = `${prefix} ${zone.strikeRange} ${premiumLabel} (${zone.levels.length})`;
          ctx.font = '10px monospace';
          const tm = ctx.measureText(labelText);
          const pad = 3;
          const lx = 4;
          const ly = centerY + 4;
          ctx.fillStyle = 'rgba(10,14,23,0.85)';
          ctx.fillRect(lx - pad, ly - 11, tm.width + pad * 2, 14);
          ctx.fillStyle = `rgba(${r},${g},${b},1)`;
          ctx.fillText(labelText, lx, ly);
        }
      }

      // ── Skew Zones ──────────────────────────────────────────────────────────────
      // DISABLED: Overlaps with flow concentration lines (same strikes, same colors)
      // Blue/call skew zones duplicate orange/call flow concentration
      // Red/put skew zones duplicate blue/put flow concentration
      // Keeping flow concentration as the primary overlay is cleaner
      const drawSkewZones = () => {
        // Skew zones disabled to avoid visual overlap with flow concentration
        // If needed, can be re-enabled with a toggle
      };

      drawSkewZones();

      // ── OI Buildup Levels ───────────────────────────────────────────
      if (oiLevels && oiLevels.length > 0 && seriesRef.current) {
        const maxDelta = Math.max(...oiLevels.map(l => Math.abs(l.oiDelta)));
        if (maxDelta > 0) {
          for (const level of oiLevels) {
            const futurePrice = strikeToFuturePrice(level.strike);
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
