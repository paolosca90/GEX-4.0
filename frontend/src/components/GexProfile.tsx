import React, { useEffect, useState, useRef, useMemo } from 'react';

interface GexLevel {
    strike: number;
    gex: number;
    futurePrice: number;
}

interface GexProfileProps {
    apiBase: string;
    underlying: string;
    priceRange?: { min: number; max: number } | null;
}

export const GexProfile: React.FC<GexProfileProps> = ({ apiBase, underlying, priceRange }) => {
    const [gexData, setGexData] = useState<GexLevel[]>([]);
    const [message, setMessage] = useState('Loading...');
    const containerRef = useRef<HTMLDivElement>(null);

    // Fetch GEX data
    useEffect(() => {
        const fetchGex = async () => {
            try {
                const resp = await fetch(`${apiBase}/api/gex/latest?underlying=${underlying}`);
                const data = await resp.json();
                if (data.gex && data.gex.length > 0) {
                    setGexData(data.gex);
                    setMessage('');
                } else {
                    setMessage('No data');
                }
            } catch {
                setMessage('Error loading');
            }
        };

        fetchGex();
        const interval = setInterval(fetchGex, 60000);
        return () => clearInterval(interval);
    }, [apiBase, underlying]);

    // Filter and sort GEX data
    const filteredGex = useMemo(() => {
        if (!gexData.length) return [];

        // Filter by price range if provided
        let filtered = gexData;
        if (priceRange) {
            const padding = (priceRange.max - priceRange.min) * 0.1;
            filtered = gexData.filter(level =>
                level.futurePrice >= priceRange.min - padding &&
                level.futurePrice <= priceRange.max + padding
            );
        }

        // Filter significant GEX only (> 1% of max)
        const maxAbsGex = Math.max(...gexData.map(g => Math.abs(g.gex)));
        const threshold = maxAbsGex * 0.01;

        return filtered
            .filter(level => Math.abs(level.gex) > threshold)
            .sort((a, b) => a.futurePrice - b.futurePrice);
    }, [gexData, priceRange]);

    // Calculate max for bar scaling
    const maxGex = useMemo(() => {
        if (!filteredGex.length) return 1;
        return Math.max(...filteredGex.map(g => Math.abs(g.gex)));
    }, [filteredGex]);

    if (message) {
        return (
            <div className="gex-profile-container">
                <div className="gex-header">GEX {underlying}</div>
                <div className="gex-empty">{message}</div>
            </div>
        );
    }

    if (!filteredGex.length) {
        return (
            <div className="gex-profile-container">
                <div className="gex-header">GEX {underlying}</div>
                <div className="gex-empty">No visible levels</div>
            </div>
        );
    }

    // Use price range for positioning, or fall back to GEX data range
    const minPrice = priceRange?.min ?? Math.min(...filteredGex.map(g => g.futurePrice));
    const maxPrice = priceRange?.max ?? Math.max(...filteredGex.map(g => g.futurePrice));
    const priceSpan = maxPrice - minPrice;

    // Calculate Gamma Flip (Zero GEX Level) using the "Gamma Valley" method
    const gammaFlipPrice = useMemo(() => {
        if (!gexData.length) return null;
        const sorted = [...gexData].sort((a, b) => a.futurePrice - b.futurePrice);
        
        let cumulative = 0;
        let minCumulative = Infinity;
        let flipPrice = sorted[Math.floor(sorted.length / 2)].futurePrice;
        
        for (const level of sorted) {
            cumulative += level.gex;
            if (cumulative < minCumulative) {
                minCumulative = cumulative;
                flipPrice = level.futurePrice;
            }
        }
        return flipPrice;
    }, [gexData]);

    return (
        <div className="gex-profile-container" ref={containerRef}>
            <div className="gex-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>GEX {underlying}</span>
                {gammaFlipPrice !== null && (
                     <span style={{ fontSize: '0.8em', color: '#ffb300' }}>Zero GEX: {Math.round(gammaFlipPrice)}</span>
                )}
            </div>
            <div className="gex-bars">
                {filteredGex.map((level, idx) => {
                    const widthPct = Math.min(95, (Math.abs(level.gex) / maxGex) * 100);
                    const isCall = level.gex > 0;

                    // Calculate vertical position (0% = top, 100% = bottom)
                    const topPct = priceSpan > 0
                        ? ((maxPrice - level.futurePrice) / priceSpan) * 100
                        : 50;

                    return (
                        <div
                            key={`${level.futurePrice}-${idx}`}
                            className="gex-row"
                            style={{ top: `${Math.max(2, Math.min(98, topPct))}%` }}
                        >
                            <span className="gex-price">{level.futurePrice.toFixed(0)}</span>
                            <div className="gex-bar-wrapper">
                                <div
                                    className={`gex-bar ${isCall ? 'call' : 'put'}`}
                                    style={{ width: `${widthPct}%` }}
                                >
                                    <span className="gex-val">
                                        {(level.gex / 1e6).toFixed(1)}M
                                    </span>
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
};
