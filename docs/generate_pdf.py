#!/usr/bin/env python3
"""Convert GEX 4.0 Guide to PDF using ReportLab"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor, black, white
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import KeepTogether
import re

# Colors
DARK_BG = HexColor('#0a0e17')
HEADER_BG = HexColor('#1e293b')
ACCENT_BLUE = HexColor('#3b82f6')
ACCENT_GREEN = HexColor('#10b981')
ACCENT_RED = HexColor('#ef4444')
ACCENT_YELLOW = HexColor('#FFB300')
ACCENT_ORANGE = HexColor('#F97316')
TEXT_GRAY = HexColor('#94a3b8')
TABLE_HEADER = HexColor('#1e293b')
TABLE_ALT = HexColor('#0f172a')

def markdown_to_pdf(md_path, pdf_path):
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        rightMargin=1.5*cm,
        leftMargin=1.5*cm,
        topMargin=1.5*cm,
        bottomMargin=1.5*cm,
        title="GEX 4.0 — Guida Completa del Sistema di Trading",
        author="GEX Dashboard"
    )

    styles = getSampleStyleSheet()

    # Custom styles
    styles.add(ParagraphStyle(
        name='Title_Custom',
        parent=styles['Title'],
        fontSize=28,
        textColor=ACCENT_YELLOW,
        spaceAfter=6,
        leading=34,
        fontName='Helvetica-Bold'
    ))

    styles.add(ParagraphStyle(
        name='Subtitle',
        parent=styles['Normal'],
        fontSize=13,
        textColor=TEXT_GRAY,
        spaceAfter=20,
        leading=18,
        fontName='Helvetica'
    ))

    styles.add(ParagraphStyle(
        name='H1_Custom',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=ACCENT_YELLOW,
        spaceBefore=20,
        spaceAfter=10,
        leading=22,
        fontName='Helvetica-Bold',
        borderPad=(0, 0, 4, 0),
    ))

    styles.add(ParagraphStyle(
        name='H2_Custom',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=ACCENT_BLUE,
        spaceBefore=14,
        spaceAfter=6,
        leading=18,
        fontName='Helvetica-Bold'
    ))

    styles.add(ParagraphStyle(
        name='H3_Custom',
        parent=styles['Heading3'],
        fontSize=12,
        textColor=ACCENT_GREEN,
        spaceBefore=10,
        spaceAfter=4,
        leading=16,
        fontName='Helvetica-Bold'
    ))

    styles.add(ParagraphStyle(
        name='Body_Custom',
        parent=styles['Normal'],
        fontSize=10,
        textColor=white,
        spaceAfter=6,
        leading=14,
        fontName='Helvetica',
        alignment=TA_JUSTIFY
    ))

    styles.add(ParagraphStyle(
        name='Bullet_Custom',
        parent=styles['Normal'],
        fontSize=10,
        textColor=white,
        spaceAfter=4,
        leading=14,
        fontName='Helvetica',
        leftIndent=16,
        bulletIndent=6
    ))

    styles.add(ParagraphStyle(
        name='Code_Custom',
        parent=styles['Normal'],
        fontSize=9,
        textColor=ACCENT_GREEN,
        spaceAfter=6,
        leading=12,
        fontName='Courier',
        backColor=HexColor('#0d1117'),
        borderPad=(4, 4, 4, 4),
    ))

    styles.add(ParagraphStyle(
        name='Table_Cell',
        parent=styles['Normal'],
        fontSize=9,
        textColor=white,
        leading=12,
        fontName='Helvetica'
    ))

    styles.add(ParagraphStyle(
        name='Table_Header',
        parent=styles['Normal'],
        fontSize=9,
        textColor=ACCENT_YELLOW,
        leading=12,
        fontName='Helvetica-Bold'
    ))

    styles.add(ParagraphStyle(
        name='Footer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=TEXT_GRAY,
        alignment=TA_CENTER
    ))

    story = []

    def add_paragraph(text, style='Body_Custom'):
        # Convert markdown bold **text** to reportlab bold
        text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'`(.+?)`', r'<font color="#10b981">\1</font>', text)
        story.append(Paragraph(text, styles[style]))
        story.append(Spacer(1, 4))

    def add_bullet(text):
        text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'`(.+?)`', r'<font color="#10b981">\1</font>', text)
        story.append(Paragraph(f'• {text}', styles['Bullet_Custom']))

    def add_h1(text):
        story.append(Spacer(1, 10))
        story.append(HRFlowable(width="100%", thickness=1, color=ACCENT_YELLOW, spaceAfter=6))
        story.append(Paragraph(text, styles['H1_Custom']))

    def add_h2(text):
        story.append(Spacer(1, 8))
        story.append(Paragraph(text, styles['H2_Custom']))

    def add_h3(text):
        story.append(Paragraph(text, styles['H3_Custom']))

    def add_table(headers, rows, col_widths=None):
        data = [[Paragraph(h, styles['Table_Header']) for h in headers]]
        for row in rows:
            data.append([Paragraph(str(cell), styles['Table_Cell']) for cell in row])

        if col_widths is None:
            col_widths = [doc.width / len(headers)] * len(headers)

        t = Table(data, colWidths=col_widths)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEADER),
            ('TEXTCOLOR', (0, 0), (-1, 0), ACCENT_YELLOW),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#334155')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [TABLE_ALT, HexColor('#0a0e17')]),
        ]))
        story.append(Spacer(1, 8))
        story.append(t)
        story.append(Spacer(1, 8))

    # ─────────────────────────────────────────────
    # TITLE PAGE
    # ─────────────────────────────────────────────
    story.append(Spacer(1, 3*cm))
    story.append(Paragraph("GEX 4.0", styles['Title_Custom']))
    story.append(Paragraph("Guida Completa del Sistema di Trading", styles['Subtitle']))
    story.append(Spacer(1, 0.5*cm))

    add_table(
        ["", ""],
        [
            ["Versione", "4.0 — Aprile 2026"],
            ["Dashboard", "http://137.220.63.222"],
            ["API Backend", "http://137.220.63.222:8000"],
            ["WebSocket", "ws://137.220.63.222:8000/ws/market_data"],
        ],
        col_widths=[4*cm, 11*cm]
    )

    story.append(PageBreak())

    # ─────────────────────────────────────────────
    # SECTION 1: PANORAMICA
    # ─────────────────────────────────────────────
    add_h1("1. Panoramica del Sistema")
    add_paragraph("GEX 4.0 è un sistema di monitoraggio real-time della Gamma Exposure (GEX) per futures su S&P 500 (ES) e Nasdaq 100 (NQ). Il sistema integra candlestick charts in tempo reale con livelli GEX sovrapposti, GEX Profile, Smart Money Power Meter, Momentum Score e Zone Alerts.")
    story.append(Spacer(1, 6))

    add_h2("1.1 Componenti Principali")

    add_h3("Candlestick Charts con GEX Overlay")
    add_paragraph("Grafici futures in tempo reale (1m/5m/15m) con livelli GEX sovrapposti: Zero Gamma Level (ZGL), Call Wall, Put Wall, e zone di concentrazione del flusso opzioni.")

    add_h3("GEX Profile")
    add_paragraph("Distribuzione completa dell'esposizione gamma per ogni strike. Mostra dove si concentra la 'pressione' dei market maker — barre verdi (call gamma) a destra, barre rosse (put gamma) a sinistra.")

    add_h3("Smart Money Power Meter")
    add_paragraph("Flusso opzioni netto (call vs put) in tempo reale con EMA drift e conteggio block trades (>$50K). Rivela il sentiment istituzionale.")

    add_h3("Momentum Score")
    add_paragraph("Punteggio composito 0-100 per la direzione del mercato. Cinque componenti pesati: Flow Velocity (35%), Price Action (25%), GEX Positioning (20%), Volume Ratio (10%), Theta Effect (10%).")

    add_h3("Zone Alerts")
    add_paragraph("Segnali di ipercomprato/ipervenduto basati sulla prossimità ai livelli GEX. Trigger automatico quando il prezzo si avvicina a ZGL, CW o PW.")

    # ─────────────────────────────────────────────
    # SECTION 2: ARCHITETTURA
    # ─────────────────────────────────────────────
    add_h1("2. Architettura Tecnica")

    add_h2("2.1 Stack Tecnologico")
    add_table(
        ["Componente", "Tecnologia"],
        [
            ["Frontend", "React + Vite + TypeScript + LightweightCharts"],
            ["Backend", "FastAPI (Python) + Uvicorn + WebSocket"],
            ["Database", "PostgreSQL + TimescaleDB"],
            ["Data Futures", "cTrader OpenAPI"],
            ["Data Opzioni", "Tradier API + Tradier WebSocket"],
            ["Server", "Vultr 137.220.63.222 — Ubuntu + nginx"],
        ]
    )

    add_h2("2.2 Flusso Dati")
    add_paragraph("cTrader OpenAPI invia tick futures in tempo reale al ctrader_openapi_daemon.py, che li memorizza nella hypertable futures_ticks. Il backend FastAPI broadcast i tick via WebSocket al frontend. Tradier API alimenta il gex_calculator.py per il profilo GEX giornaliero (16:30 EST). Il Tradier WebSocket passa per options_flow_daemon.py verso options_flow_ticks.")

    add_h2("2.3 Database — Tabelle")
    add_table(
        ["Tabella", "Tipo", "Contenuto"],
        [
            ["futures_ticks", "hypertable", "Tick price/volume US500-F, NAS100-F"],
            ["options_flow", "hypertable", "Singole operazioni opzioni (Tradier WS)"],
            ["options_flow_ticks", "hypertable", "Flow aggregato 2s con EMA drift"],
            ["options_flow_1m", "hypertable", "Flow aggregato 1 minuto"],
            ["gex_profile", "normale", "GEX per strike (calcolato 16:30 EST)"],
            ["gex_level_interactions", "hypertable", "Storico bounce/rimbalzo livelli GEX"],
        ]
    )

    add_h2("2.4 API Endpoints")
    add_table(
        ["Metodo", "Endpoint", "Descrizione"],
        [
            ["WS", "/ws/market_data", "Broadcast real-time ticks + flow"],
            ["GET", "/api/candles/{symbol}", "OHLCV 1m/5m/15m"],
            ["GET", "/api/gex/latest", "GEX profile + key levels"],
            ["GET", "/api/flow/{symbol}", "Flow opzioni per underlying"],
            ["GET", "/api/momentum/{underlying}", "Momentum Score composito"],
            ["GET", "/api/momentum/zone-alert/{underlying}", "Segnale zona ipercomprato/ipervenduto"],
        ]
    )

    story.append(PageBreak())

    # ─────────────────────────────────────────────
    # SECTION 3: TEORIA GEX
    # ─────────────────────────────────────────────
    add_h1("3. La Teoria della GEX")

    add_h2("3.1 Cos'è la Gamma Exposure")
    add_paragraph("La Gamma Exposure (GEX) misura quanto rapidamente i market maker devono comprare/vendere il sottostante per coprire le loro posizioni in opzioni al variare del prezzo.")
    story.append(Spacer(1, 4))
    add_paragraph("Formula: <b>GEX per strike = Gamma(strike) × Open Interest(strike) × 100 × Spot Price</b>", 'Body_Custom')
    story.append(Spacer(1, 4))
    add_bullet("<b>GEX positivo</b> (call): i market maker devono comprare futures quando il prezzo sale")
    add_bullet("<b>GEX negativo</b> (put): i market maker devono vendere futures quando il prezzo scende")
    add_bullet("<b>Zero Gamma Level (ZGL)</b>: il prezzo dove la somma cumulativa della GEX è minima")

    add_h2("3.2 Perché la GEX Causa Reverals")
    add_paragraph("Quando il prezzo si avvicina a uno Zero Gamma Level (ZGL):")
    story.append(Spacer(1, 4))
    add_bullet("I market maker hanno posizioni gamma elevate vicino a quel livello")
    add_bullet("Devono fare hedging attivo per mantenere delta-neutral")
    add_bullet("L'azione di hedging crea pressione direzionale che respinge il prezzo lontano dallo ZGL")
    add_bullet("Più il prezzo è vicino allo ZGL, più la pressione è forte")
    story.append(Spacer(1, 6))

    add_paragraph("<b>Regola empirica:</b>", 'Body_Custom')
    add_bullet("Prezzo <b>sopra ZGL</b> → bias ribassista (MM vendono per copertura)")
    add_bullet("Prezzo <b>sotto ZGL</b> → bias rialzista (MM comprano per copertura)")

    add_h2("3.3 Call Wall e Put Wall — Effetto sul Prezzo")
    add_table(
        ["Livello", "Significato", "Effetto sul Prezzo"],
        [
            ["Call Wall", "Strike con massimo GEX positivo", "Resistenze dinamiche — prezzo fatica a salire oltre"],
            ["Put Wall", "Strike con massimo GEX negativo", "Supporti dinamici — prezzo rimbalza su questo livello"],
            ["Zero Gamma (ZGL)", "Livello dove GEX cumulativa = 0", "Punto di equilibrio — trigger per reversal"],
        ]
    )

    story.append(PageBreak())

    # ─────────────────────────────────────────────
    # SECTION 4: DASHBOARD
    # ─────────────────────────────────────────────
    add_h1("4. Come Leggere il Dashboard")

    add_h2("4.1 Layout Principale")
    add_paragraph("Il dashboard è diviso in tre colonne principali: Chart (sinistra) con candlestick + GEX overlay, GEX Profile (centro) con barre gamma per strike, e Smart Money Power Meter (destra) con flusso opzioni netto.")
    story.append(Spacer(1, 6))
    add_paragraph("Sotto il chart principale: Scalping Panel, SkewGauge, GreeksPanel e DarkPoolPanel per analisi approfondita.")

    add_h2("4.2 Livelli Chiave — Colori e Significato")
    add_table(
        ["Colore", "Livello", "Significato"],
        [
            ["Giallo", "0GEX (ZGL)", "Zero Gamma — reversal point"],
            ["Verde", "CW (Call Wall)", "Massima pressione acquisto opzioni"],
            ["Rosso", "PW (Put Wall)", "Massima pressione vendita opzioni"],
            ["Verde tratteggiato", "Top Call", "Altre resistenze call"],
            ["Rosso tratteggiato", "Top Put", "Altri supporti put"],
            ["Arancione", "CALL ZONE", "Cluster flow call concentrato"],
            ["Blu", "PUT ZONE", "Cluster flow put concentrato"],
            ["Verde chiaro", "OI Buildup (call)", "Accumulo open interest call"],
            ["Rosso chiaro", "OI Buildup (put)", "Accumulo open interest put"],
        ]
    )

    add_h2("4.3 GEX Profile — Sidebar")
    add_paragraph("Barre verdi (a destra): GEX positivo (call gamma) — pressure che spinge il prezzo in alto. Barre rosse (a sinistra): GEX negativo (put gamma) — pressione che spinge il prezzo in basso. L'etichetta gialla 'Zero GEX' indica il Gamma Flip — il prezzo di equilibrio.")

    add_h2("4.4 Smart Money Power Meter")
    add_table(
        ["Metrica", "Descrizione"],
        [
            ["Net Flow", "Flusso netto call - put (in $) ultimi 5 min"],
            ["Drift", "EMA(120s) del net flow — direzione trend"],
            ["Sentinels", "Numero block trades (>$50K) rilevati"],
            ["Reg M", "Tick indicator per Regulation M"],
        ]
    )

    story.append(PageBreak())

    # ─────────────────────────────────────────────
    # SECTION 5: STRATEGIA
    # ─────────────────────────────────────────────
    add_h1("5. La Strategia di Trading")

    add_h2("5.1 Setup Base — Reversal alla GEX")

    add_paragraph("<b>Precondizioni (tutte devono essere vere):</b>", 'Body_Custom')
    story.append(Spacer(1, 4))
    add_bullet("Il prezzo è <b>vicino</b> a un livello GEX chiave (ZGL, CW, PW) — entro 0.3%")
    add_bullet("Il <b>Momentum Score</b> è < 30 (ribasso) o > 70 (rialzo)")
    add_bullet("C'è <b>convergenza</b> tra più indicatori (flow + GEX + price action)")
    story.append(Spacer(1, 8))

    add_paragraph("<b>Setup Rialzista (Long):</b>", 'Body_Custom')
    add_bullet("Prezzo vicino al <b>Put Wall</b> (supporto put gamma)")
    add_bullet("Momentum Score < 30")
    add_bullet("Net Flow positivo con drift in salita")
    add_bullet("Trigger: candle di <b>rientro</b> dopo pullback al PW")

    add_paragraph("<b>Setup Ribassista (Short):</b>", 'Body_Custom')
    add_bullet("Prezzo vicino al <b>Call Wall</b> (resistenza call gamma)")
    add_bullet("Momentum Score > 70")
    add_bullet("Net Flow negativo con drift in discesa")
    add_bullet("Trigger: candle di <b>rientro</b> dopo rialzo al CW")

    add_h2("5.2 Momentum Score — Componenti")
    add_table(
        ["Componente", "Peso", "Descrizione"],
        [
            ["Flow Velocity", "35%", "EMA del net flow call-put a 5 min"],
            ["Price Action", "25%", "Rendimento a 15 min normalizzato"],
            ["GEX Positioning", "20%", "Distanza prezzo da ZGL (in sigma)"],
            ["Volume Ratio", "10%", "Volume attuale vs media 5 min"],
            ["Theta Effect", "10%", "Decadimento temporale opzioni"],
        ]
    )

    add_paragraph("<b>Interpretazione:</b>", 'Body_Custom')
    add_bullet("Score <b>< 20</b>: ipervenduto estremo — inversione rialzista probabile")
    add_bullet("Score <b>20-40</b>: bias rialzista — cerca long")
    add_bullet("Score <b>40-60</b>: neutrale — no posizioni directional")
    add_bullet("Score <b>60-80</b>: bias ribassista — cerca short")
    add_bullet("Score <b>> 80</b>: ipercomprato estremo — inversione ribassista probabile")

    add_h2("5.3 Zone Alerts")
    add_paragraph("Quando il prezzo supera le soglie di prossimità ai livelli GEX, il sistema genera alert:")
    add_table(
        ["Distanza da Livello", "Segnale", "Azione"],
        [
            ["< 0.2% da ZGL", "REVERSAL IMMINENTE", "Inverti direzione"],
            ["< 0.5% da CW/PW", "CONSOLIDAMENTO", "No entry directional"],
            ["> 1% da qualsiasi livello", "MERCATO LIBERO", "No resistenze GEX"],
        ]
    )

    add_h2("5.4 Gestione del Rischio")

    add_paragraph("<b>Stop Loss:</b>", 'Body_Custom')
    add_bullet("Sempre <b>oltre il livello GEX</b> che ha innescato il trade")
    add_bullet("Esempio: long da 7120 con PW a 7115 → stop sotto 7115")

    add_paragraph("<b>Take Profit:</b>", 'Body_Custom')
    add_bullet("Al <b>prossimo livello GEX</b> significativo")
    add_bullet("R:R minimo <b>3:1</b>")

    add_paragraph("<b>Position Sizing:</b>", 'Body_Custom')
    add_paragraph("Size = (Account × 1%) / (Entry − Stop) × Contract Multiplier", 'Code_Custom')
    add_paragraph("Per ES (50$ per punto): Conto $50,000, rischio 1% = $500. Distanza stop = 5 punti ES → Size = $500 / (5 × $50) = 2 contratti", 'Body_Custom')

    add_h2("5.5 Cosa Evitare")
    add_bullet("<b>Non tradare in direzione opposta a un Call/Put Wall forte</b> — MM difendono questi livelli")
    add_bullet("<b>Non entrare se il prezzo è tra due livelli GEX vicini</b> — consolidamento, aspetta breakout")
    add_bullet("<b>Non ignorare il Momentum Score</b> — Score < 30 + prezzo vicino PW = setup rialzista")
    add_bullet("<b>Non aggiungere a posizioni in perdita</b> — la GEX non è ancora girata a tuo favore")

    story.append(PageBreak())

    # ─────────────────────────────────────────────
    # SECTION 6: ESEMPI
    # ─────────────────────────────────────────────
    add_h1("6. Esempi Pratici di Trading")

    add_h2("6.1 Esempio: Long su ES al Put Wall")
    add_paragraph("<b>Scenario:</b>", 'Body_Custom')
    add_table(
        ["Parametro", "Valore"],
        [
            ["ES (US500-F)", "7166"],
            ["ZGL", "7170"],
            ["Put Wall", "7115"],
            ["Momentum Score", "28 (bias rialzista)"],
            ["Net Flow", "+$2.3M (positivo)"],
            ["Drift", "In salita da 10 min"],
        ],
        col_widths=[5*cm, 10*cm]
    )
    story.append(Spacer(1, 6))

    add_paragraph("<b>Azione:</b>", 'Body_Custom')
    add_bullet("1. Aspetta pullback verso 7115-7120")
    add_bullet("2. Entra long a 7118 (sopra PW)")
    add_bullet("3. Stop loss: 7108 (sotto PW, 10 punti = $500)")
    add_bullet("4. Take profit 1: 7155 (primo target = 3:1, chiude metà posizione)")
    add_bullet("5. Secondo target: 7170 (ZGL)")

    add_paragraph("<b>Risk/Reward:</b>", 'Body_Custom')
    add_table(
        ["", "Punti", "Valore", "R:R"],
        [
            ["Rischio", "10", "$500", "1:1"],
            ["Reward 1", "37", "$1,850", "3.7:1"],
            ["Reward 2", "52", "$2,600", "5.2:1"],
        ],
        col_widths=[4*cm, 3*cm, 4*cm, 4*cm]
    )

    add_h2("6.2 Esempio: Short su NQ al Call Wall")
    add_paragraph("<b>Scenario:</b>", 'Body_Custom')
    add_table(
        ["Parametro", "Valore"],
        [
            ["NQ (NAS100-F)", "26853"],
            ["ZGL", "26906"],
            ["Call Wall", "26864"],
            ["Momentum Score", "75 (bias ribassista)"],
            ["Net Flow", "-$1.8M (negativo)"],
        ],
        col_widths=[5*cm, 10*cm]
    )
    story.append(Spacer(1, 6))

    add_paragraph("<b>Azione:</b>", 'Body_Custom')
    add_bullet("1. Aspetta rally verso 26864-26870")
    add_bullet("2. Entra short a 26865")
    add_bullet("3. Stop loss: 26910 (sopra ZGL, 45 punti)")
    add_bullet("4. Take profit 1: 26750 (chiude metà)")
    add_bullet("5. Secondo target: 26650 (livello strutturale)")

    story.append(PageBreak())

    # ─────────────────────────────────────────────
    # SECTION 7: GLOSSARIO
    # ─────────────────────────────────────────────
    add_h1("7. Glossario")
    add_table(
        ["Termine", "Definizione"],
        [
            ["GEX", "Gamma Exposure — misura della pressione di hedging dei market maker"],
            ["ZGL", "Zero Gamma Level — strike dove la GEX cumulativa è zero"],
            ["Call Wall", "Strike con massimo GEX positivo — resistenza dinamica"],
            ["Put Wall", "Strike con massimo GEX negativo — supporto dinamico"],
            ["0DTE", "Opzioni con scadenza lo stesso giorno (zero days to expiration)"],
            ["Delta", "Sensitività del prezzo dell'opzione al sottostante"],
            ["Gamma", "Variazione del delta al variare del prezzo del sottostante"],
            ["Open Interest", "Numero contratti opzioni aperti"],
            ["Smart Money", "Flussi opzioni istituzionali (block trades)"],
            ["Flow Velocity", "Tasso di variazione del net flow nel tempo"],
            ["Momentum Score", "Punteggio composito 0-100 per directional bias"],
            ["Block Trade", "Operazione grande (>$50K) — rivela sentiment istituzionale"],
            ["Call Wall", "Massimo GEX positivo — resistenza call gamma"],
            ["Put Wall", "Massimo GEX negativo — supporto put gamma"],
        ]
    )

    # ─────────────────────────────────────────────
    # SECTION 8: RIFERIMENTI
    # ─────────────────────────────────────────────
    add_h1("8. Link e Riferimenti")
    add_table(
        ["Risorsa", "URL"],
        [
            ["Dashboard", "http://137.220.63.222"],
            ["Backend API", "http://137.220.63.222:8000"],
            ["WebSocket", "ws://137.220.63.222:8000/ws/market_data"],
            ["cTrader", "OpenAPI per futures real-time"],
            ["Tradier", "API per opzioni SPX/QQQ e flusso"],
        ]
    )

    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=TEXT_GRAY))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Questa guida è stata generata per scopi educativi. Il trading di opzioni e futures comporta rischi significativi di perdita. Nessuna garanzia di profitto. GEX 4.0 — Aprile 2026",
        styles['Footer']
    ))

    # Build
    doc.build(story)
    print(f"PDF generato: {pdf_path}")

if __name__ == "__main__":
    md_path = "/Users/paolo/Desktop/GEX 4.0/docs/GEX_4.0_Guida_Sistema.md"
    pdf_path = "/Users/paolo/Desktop/GEX 4.0/docs/GEX_4.0_Guida_Sistema.pdf"
    markdown_to_pdf(md_path, pdf_path)
