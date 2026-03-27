import React, { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import { createChart, ColorType, IChartApi, ISeriesApi, Time, CandlestickSeries, IRange } from 'lightweight-charts';

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

interface ChartProps {
  candles: CandleInput[];
  lastTick: TickData | null;
  gexData?: GexLevel[];
  interval?: '1m' | '5m' | '15m';
}

export const LightweightChart: React.FC<ChartProps> = ({ candles, lastTick, gexData = [], interval = '1m' }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const [visibleTimeRange, setVisibleTimeRange] = useState<IRange<number> | null>(null);
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 });

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

  // Heatmap Canvas Drawing
  useEffect(() => {
    if (!canvasRef.current || !seriesRef.current || gexData.length === 0 || maxGex <= 0) return;

    const canvas = canvasRef.current;
    // Set actual canvas resolution to match size
    canvas.width = containerSize.width;
    canvas.height = containerSize.height;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let lastYMap = '';

    const sortedGex = [...gexData].sort((a, b) => a.futurePrice - b.futurePrice);

    const drawHeatmap = () => {
      animationFrameId = requestAnimationFrame(drawHeatmap);

      if (!seriesRef.current) return;

      const pBot = sortedGex[0]?.futurePrice;
      const pTop = sortedGex[sortedGex.length - 1]?.futurePrice;
      if (pBot === undefined || pTop === undefined) return;

      const yBot = seriesRef.current.priceToCoordinate(pBot);
      const yTop = seriesRef.current.priceToCoordinate(pTop);

      const currentYMap = `${yBot}_${yTop}`;
      if (currentYMap === lastYMap) return; // Scale/pan hasn't changed
      lastYMap = currentYMap;

      const width = canvas.width;
      const height = canvas.height;
      ctx.clearRect(0, 0, width, height);

      // Base background color dark for matrix
      ctx.fillStyle = '#0a0e17';
      ctx.fillRect(0, 0, width, height);

      // --- 1. Calculate Gamma Flip (Zero GEX Level) using "Gamma Valley" ---
      // We find the absolute minimum of the cumulative GEX sum, indicating the shift
      // from net negative to net positive Dealer Gamma exposure.
      let cumulative = 0;
      let minCumulative = Infinity;
      let gammaFlipPrice = sortedGex[Math.floor(sortedGex.length / 2)].futurePrice; // fallback to median
      
      for (const level of sortedGex) {
        cumulative += level.gex;
        if (cumulative < minCumulative) {
            minCumulative = cumulative;
            gammaFlipPrice = level.futurePrice;
        }
      }

      // --- 2. Get Current Market Price ---
      const currentPrice = currentCandleRef.current?.close ?? (pBot + pTop) / 2;
      const isPriceAboveFlip = currentPrice >= gammaFlipPrice;

      // --- 3. Draw Discrete GEX Lines ---
      for (let i = 0; i < sortedGex.length; i++) {
        const level = sortedGex[i];
        
        // Skip tiny levels (noise)
        if (Math.abs(level.gex) < maxGex * 0.02) continue;

        const y = seriesRef.current.priceToCoordinate(level.futurePrice);
        if (y === null || y < 0 || y > height) continue;

        // Exponential Opacity Filtering:
        // Calculate non-linear intensity so huge levels glow, and tiny noise fades out.
        const normalizedGex = Math.abs(level.gex) / maxGex;
        const alpha = Math.min(1.0, Math.pow(normalizedGex, 0.6)); 

        const isCall = level.gex > 0;
        let rgbaColor;

        // --- 4. Contextual Line Style Strategy ---
        // Positive Gamma Environment (Price > Flip) -> Solid Lines
        // Negative Gamma Environment (Price < Flip) -> Dashed Lines
        
        if (isCall) {
            rgbaColor = `rgba(239, 68, 68, ${alpha})`; // Call / Resistance
        } else {
            rgbaColor = `rgba(16, 185, 129, ${alpha})`; // Put / Support
        }

        const lineHeight = 4;

        ctx.beginPath();
        ctx.strokeStyle = rgbaColor;
        ctx.lineWidth = lineHeight;
        
        if (isPriceAboveFlip) {
            ctx.setLineDash([]); // Solid
        } else {
            ctx.setLineDash([10, 6]); // Dashed
        }

        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
      }

      // --- 4. Draw Gamma Flip (Zero GEX) Marker Line ---
      // User requested a distinct yellow line to explicitly show the Flip point
      if (gammaFlipPrice) {
          ctx.setLineDash([]); // Reset dash for the marker line
          const flipY = seriesRef.current.priceToCoordinate(gammaFlipPrice);
          if (flipY !== null && flipY >= 0 && flipY <= height) {
              const flipLineHeight = 2; // Thinner but solid
              ctx.fillStyle = 'rgba(245, 158, 11, 0.9)'; // Bright Gold/Yellow
              ctx.fillRect(0, flipY - (flipLineHeight / 2), width, flipLineHeight);

              // Optional: Add a tiny label on the left edge
              ctx.fillStyle = 'rgba(245, 158, 11, 0.9)';
              ctx.font = '10px monospace';
              ctx.fillText('ZERO GEX', 5, flipY - 3);
          }
      }
    };

    drawHeatmap();

    return () => {
      cancelAnimationFrame(animationFrameId);
    };
  }, [gexData, maxGex, containerSize]);

  // Filter GEX to visible price range
  const visibleGex = useMemo(() => {
    return gexData.filter(level => {
      if (Math.abs(level.gex) < maxGex * 0.01) return false;
      if (level.futurePrice < rangeMin || level.futurePrice > rangeMax) return false;
      return true;
    });
  }, [gexData, maxGex, rangeMin, rangeMax]);

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
