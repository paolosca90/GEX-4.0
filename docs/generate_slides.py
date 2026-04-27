#!/usr/bin/env python3
"""Generate simple GEX 4.0 trading slides PDF"""

from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor, black, white
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image, HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Circle
from reportlab.graphics import renderPDF
from reportlab.platypus import Flowable
import os

# Colors
BG_DARK = HexColor('#0a0e17')
BG_CARD = HexColor('#1e293b')
ACCENT_YELLOW = HexColor('#FFB300')
ACCENT_GREEN = HexColor('#10b981')
ACCENT_RED = HexColor('#ef4444')
ACCENT_BLUE = HexColor('#3b82f6')
ACCENT_ORANGE = HexColor('#F97316')
TEXT_WHITE = HexColor('#f1f5f9')
TEXT_GRAY = HexColor('#94a3b8')
GREEN_BG = HexColor('#052e16')
RED_BG = HexColor('#3b0a0a')

PAGE_W, PAGE_H = landscape(A4)

def create_slides():
    doc = SimpleDocTemplate(
        "/Users/paolo/Desktop/GEX 4.0/docs/GEX_4.0_Slide_Trading.pdf",
        pagesize=landscape(A4),
        rightMargin=1*cm,
        leftMargin=1*cm,
        topMargin=1*cm,
        bottomMargin=1*cm,
        title="GEX 4.0 — Come Entrare a Mercato",
        author="GEX Dashboard"
    )

    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name='SlideTitle',
        fontSize=36,
        textColor=ACCENT_YELLOW,
        fontName='Helvetica-Bold',
        alignment=TA_CENTER,
        spaceAfter=10,
        leading=42
    ))

    styles.add(ParagraphStyle(
        name='SlideSubtitle',
        fontSize=18,
        textColor=TEXT_GRAY,
        fontName='Helvetica',
        alignment=TA_CENTER,
        spaceAfter=20,
    ))

    styles.add(ParagraphStyle(
        name='StepTitle',
        fontSize=28,
        textColor=ACCENT_YELLOW,
        fontName='Helvetica-Bold',
        spaceBefore=10,
        spaceAfter=8,
        leading=34
    ))

    styles.add(ParagraphStyle(
        name='StepNum',
        fontSize=64,
        textColor=ACCENT_YELLOW,
        fontName='Helvetica-Bold',
        alignment=TA_CENTER,
        leading=70
    ))

    styles.add(ParagraphStyle(
        name='BodyBig',
        fontSize=16,
        textColor=TEXT_WHITE,
        fontName='Helvetica',
        spaceAfter=10,
        leading=22,
        alignment=TA_LEFT
    ))

    styles.add(ParagraphStyle(
        name='BulletSlide',
        fontSize=15,
        textColor=TEXT_WHITE,
        fontName='Helvetica',
        spaceAfter=10,
        leading=22,
        leftIndent=20
    ))

    styles.add(ParagraphStyle(
        name='GreenText',
        fontSize=15,
        textColor=ACCENT_GREEN,
        fontName='Helvetica-Bold',
        spaceAfter=8,
        leading=20
    ))

    styles.add(ParagraphStyle(
        name='RedText',
        fontSize=15,
        textColor=ACCENT_RED,
        fontName='Helvetica-Bold',
        spaceAfter=8,
        leading=20
    ))

    styles.add(ParagraphStyle(
        name='YellowText',
        fontSize=15,
        textColor=ACCENT_YELLOW,
        fontName='Helvetica-Bold',
        spaceAfter=8,
        leading=20
    ))

    styles.add(ParagraphStyle(
        name='Caption',
        fontSize=11,
        textColor=TEXT_GRAY,
        fontName='Helvetica',
        alignment=TA_CENTER,
        spaceAfter=6
    ))

    styles.add(ParagraphStyle(
        name='Footer',
        fontSize=9,
        textColor=TEXT_GRAY,
        fontName='Helvetica',
        alignment=TA_CENTER
    ))

    story = []

    # ─────────────────────────────────────────────
    # SLIDE 1: COVER
    # ─────────────────────────────────────────────
    def add_cover():
        story.append(Spacer(1, 3*cm))
        story.append(Paragraph("GEX 4.0", styles['SlideTitle']))
        story.append(Paragraph("Come Entrare a Mercato", styles['SlideSubtitle']))
        story.append(Spacer(1, 1*cm))
        story.append(HRFlowable(width="60%", thickness=2, color=ACCENT_YELLOW, spaceAfter=20))
        story.append(Spacer(1, 1*cm))

        data = [
            [Paragraph("<b>3 COSE DA GUARDARE</b>", ParagraphStyle('t', fontSize=22, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER))],
            [Paragraph("① Momentum Score", ParagraphStyle('t', fontSize=18, textColor=ACCENT_GREEN, fontName='Helvetica-Bold', alignment=TA_CENTER))],
            [Paragraph("② Livelli GEX (ZGL, CW, PW)", ParagraphStyle('t', fontSize=18, textColor=ACCENT_BLUE, fontName='Helvetica-Bold', alignment=TA_CENTER))],
            [Paragraph("③ Alerts di Reversal", ParagraphStyle('t', fontSize=18, textColor=ACCENT_ORANGE, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        ]
        t = Table(data, colWidths=[12*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), BG_CARD),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('LEFTPADDING', (0, 0), (-1, -1), 20),
            ('RIGHTPADDING', (0, 0), (-1, -1), 20),
            ('LINEBELOW', (0, 0), (-1, 0), 2, ACCENT_YELLOW),
            ('LINEBELOW', (0, 1), (-1, 1), 1, HexColor('#334155')),
            ('LINEBELOW', (0, 2), (-1, 2), 1, HexColor('#334155')),
        ]))
        story.append(t)
        story.append(Spacer(1, 1.5*cm))
        story.append(Paragraph("Dashboard: <font color='#FFB300'>http://137.220.63.222</font>", styles['Footer']))

    add_cover()
    story.append(PageBreak())

    # ─────────────────────────────────────────────
    # SLIDE 2: COS'E' IL MOMENTUM SCORE
    # ─────────────────────────────────────────────
    def add_slide_header(title, subtitle=""):
        story.append(Paragraph(title, styles['StepTitle']))
        if subtitle:
            story.append(Paragraph(subtitle, styles['SlideSubtitle']))

    def add_bullet_big(text, color=None):
        if color == 'green':
            story.append(Paragraph(f'<font color="#10b981">●</font>  {text}', styles['BulletSlide']))
        elif color == 'red':
            story.append(Paragraph(f'<font color="#ef4444">●</font>  {text}', styles['BulletSlide']))
        elif color == 'yellow':
            story.append(Paragraph(f'<font color="#FFB300">●</font>  {text}', styles['BulletSlide']))
        else:
            story.append(Paragraph(f'•  {text}', styles['BulletSlide']))

    add_slide_header("① Momentum Score", "Il termometro del mercato — sempre visibile")

    # Screenshot del momentum score
    img_path = "/Users/paolo/Desktop/GEX 4.0/docs/screenshot_dashboard_1920.png"
    if os.path.exists(img_path):
        img = Image(img_path, width=14*cm, height=8*cm)
        story.append(img)
        story.append(Paragraph("Il Momentum Score (0-100) è nel pannello SCALPING SIGNAL", styles['Caption']))

    story.append(Spacer(1, 0.5*cm))

    data = [
        [Paragraph("SCORE", ParagraphStyle('h', fontSize=13, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("SIGNIFICATO", ParagraphStyle('h', fontSize=13, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("AZIONE", ParagraphStyle('h', fontSize=13, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("< 30", ParagraphStyle('t', fontSize=16, textColor=ACCENT_GREEN, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("Ipervenduto — possibilità di rimbalzo", ParagraphStyle('t', fontSize=14, textColor=TEXT_WHITE, alignment=TA_CENTER)),
         Paragraph("Cerca LONG", ParagraphStyle('t', fontSize=16, textColor=ACCENT_GREEN, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("30-60", ParagraphStyle('t', fontSize=16, textColor=TEXT_GRAY, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("Neutrale — niente direzionale", ParagraphStyle('t', fontSize=14, textColor=TEXT_GRAY, alignment=TA_CENTER)),
         Paragraph("FUORI", ParagraphStyle('t', fontSize=16, textColor=TEXT_GRAY, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("> 70", ParagraphStyle('t', fontSize=16, textColor=ACCENT_RED, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("Ipercomprato — possibilità di calo", ParagraphStyle('t', fontSize=14, textColor=TEXT_WHITE, alignment=TA_CENTER)),
         Paragraph("Cerca SHORT", ParagraphStyle('t', fontSize=16, textColor=ACCENT_RED, fontName='Helvetica-Bold', alignment=TA_CENTER))],
    ]
    t = Table(data, colWidths=[4*cm, 10*cm, 4*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BG_CARD),
        ('BACKGROUND', (0, 1), (-1, 1), GREEN_BG),
        ('BACKGROUND', (0, 2), (-1, 2), BG_CARD),
        ('BACKGROUND', (0, 3), (-1, 3), RED_BG),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, HexColor('#334155')),
    ]))
    story.append(t)
    story.append(PageBreak())

    # ─────────────────────────────────────────────
    # SLIDE 3: I LIVELLI GEX
    # ─────────────────────────────────────────────
    add_slide_header("② I Livelli GEX", "Le linee gialle, verdi e rosse sul chart")
    story.append(Spacer(1, 0.3*cm))

    # Tabella colori livelli
    data = [
        [Paragraph("COLORE", ParagraphStyle('h', fontSize=13, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("LIVELLO", ParagraphStyle('h', fontSize=13, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("COSA SIGNIFICA", ParagraphStyle('h', fontSize=13, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("QUANDO ENTRARE", ParagraphStyle('h', fontSize=13, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("  GIALLO  ", ParagraphStyle('t', fontSize=14, textColor=black, fontName='Helvetica-Bold', alignment=TA_CENTER, backColor=ACCENT_YELLOW)),
         Paragraph("0GEX (ZGL)", ParagraphStyle('t', fontSize=13, textColor=TEXT_WHITE, fontName='Helvetica-Bold')),
         Paragraph("Punto di equilibrio — reversal point", ParagraphStyle('t', fontSize=12, textColor=TEXT_WHITE)),
         Paragraph("Prezzo torna verso ZGL da lontano", ParagraphStyle('t', fontSize=12, textColor=ACCENT_GREEN))],
        [Paragraph("  VERDE  ", ParagraphStyle('t', fontSize=14, textColor=black, fontName='Helvetica-Bold', alignment=TA_CENTER, backColor=ACCENT_GREEN)),
         Paragraph("CW (Call Wall)", ParagraphStyle('t', fontSize=13, textColor=TEXT_WHITE, fontName='Helvetica-Bold')),
         Paragraph("Resistenza — MM devono vendere", ParagraphStyle('t', fontSize=12, textColor=TEXT_WHITE)),
         Paragraph("Prezzo sale verso CW + Score > 70", ParagraphStyle('t', fontSize=12, textColor=ACCENT_RED))],
        [Paragraph("  ROSSO  ", ParagraphStyle('t', fontSize=14, textColor=white, fontName='Helvetica-Bold', alignment=TA_CENTER, backColor=ACCENT_RED)),
         Paragraph("PW (Put Wall)", ParagraphStyle('t', fontSize=13, textColor=TEXT_WHITE, fontName='Helvetica-Bold')),
         Paragraph("Supporto — MM devono comprare", ParagraphStyle('t', fontSize=12, textColor=TEXT_WHITE)),
         Paragraph("Prezzo scende verso PW + Score < 30", ParagraphStyle('t', fontSize=12, textColor=ACCENT_GREEN))],
    ]
    t = Table(data, colWidths=[3*cm, 4*cm, 7*cm, 6*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BG_CARD),
        ('BACKGROUND', (0, 1), (-1, 1), HexColor('#1a2e1a')),
        ('BACKGROUND', (0, 2), (-1, 2), BG_CARD),
        ('BACKGROUND', (0, 3), (-1, 3), HexColor('#2a1a1a')),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (1, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 1, HexColor('#334155')),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.5*cm))

    add_bullet_big("Sul chart ES/NQ in alto trovi i livelli GEX come linee orizzontali colorate", 'yellow')
    add_bullet_big("Lo ZGL (0GEX) è il prezzo dove il mercato è in equilibrio — più vicino = più probabile il reversal")
    add_bullet_big("Il Call Wall (verde) è una resistenza, il Put Wall (rosso) è un supporto")
    story.append(PageBreak())

    # ─────────────────────────────────────────────
    # SLIDE 4: GLI ALERTS
    # ─────────────────────────────────────────────
    add_slide_header("③ Gli Alerts di Reversal", "Il sistema ti dice quando entrare — nel pannello ALERTS")
    story.append(Spacer(1, 0.3*cm))

    data = [
        [Paragraph("ALERT", ParagraphStyle('h', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("COSA VUOL DIRE", ParagraphStyle('h', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("COSA FARE", ParagraphStyle('h', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("▲ SPX REVERSAL BULLISH", ParagraphStyle('t', fontSize=13, textColor=ACCENT_GREEN, fontName='Helvetica-Bold')),
         Paragraph("Il prezzo sta rimbalzando — bias rialzista", ParagraphStyle('t', fontSize=12, textColor=TEXT_WHITE)),
         Paragraph("Entra LONG vicino al Put Wall", ParagraphStyle('t', fontSize=13, textColor=ACCENT_GREEN, fontName='Helvetica-Bold'))],
        [Paragraph("▼ QQQ REVERSAL BEARISH", ParagraphStyle('t', fontSize=13, textColor=ACCENT_RED, fontName='Helvetica-Bold')),
         Paragraph("Il prezzo sta calando — bias ribassista", ParagraphStyle('t', fontSize=12, textColor=TEXT_WHITE)),
         Paragraph("Entra SHORT vicino al Call Wall", ParagraphStyle('t', fontSize=13, textColor=ACCENT_RED, fontName='Helvetica-Bold'))],
    ]
    t = Table(data, colWidths=[5*cm, 8*cm, 7*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BG_CARD),
        ('BACKGROUND', (0, 1), (-1, 1), GREEN_BG),
        ('BACKGROUND', (0, 2), (-1, 2), RED_BG),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, HexColor('#334155')),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.5*cm))

    add_bullet_big("Gli alert appaiono nel pannello ALERTS in basso a destra", 'yellow')
    add_bullet_big("Confluence = quanto sono d'accordo gli indicatori (più alto = più sicuro)")
    add_bullet_big("Esempio: 'Confluence: 76%' significa che 3 su 4 indicatori dicono LONG")
    story.append(PageBreak())

    # ─────────────────────────────────────────────
    # SLIDE 5: ESEMPIO PRATICO LONG
    # ─────────────────────────────────────────────
    add_slide_header("📈 Esempio Pratico: LONG su ES", "Setup rialzista in atto adesso")
    story.append(Spacer(1, 0.3*cm))

    # Box scenario
    data = [
        [Paragraph("SETUP ATTUALE ES (US500-F)", ParagraphStyle('h', fontSize=16, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("• Momentum Score: <b><font color='#10b981'>69%</font></b> → BEARISH (vicino a 70 = ipercomprato)", ParagraphStyle('t', fontSize=14, textColor=TEXT_WHITE, alignment=TA_LEFT))],
        [Paragraph("• ZGL (0GEX): <b><font color='#FFB300'>7177</font></b> — prezzo attuale 7179", ParagraphStyle('t', fontSize=14, textColor=TEXT_WHITE, alignment=TA_LEFT))],
        [Paragraph("• Alert: <b><font color='#10b981'>▲ SPX REVERSAL BULLISH</font></b> con Confluence 76%", ParagraphStyle('t', fontSize=14, textColor=TEXT_WHITE, alignment=TA_LEFT))],
        [Paragraph("• Key Level: 7120.3 (Put Wall)", ParagraphStyle('t', fontSize=14, textColor=TEXT_WHITE, alignment=TA_LEFT))],
    ]
    t = Table(data, colWidths=[18*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BG_CARD),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 15),
        ('LINEBELOW', (0, 0), (-1, 0), 2, ACCENT_YELLOW),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.4*cm))

    # Azione
    data = [
        [Paragraph("AZIONE", ParagraphStyle('h', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("PREZZO", ParagraphStyle('h', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("NOTA", ParagraphStyle('h', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("⏳ ASPETTA", ParagraphStyle('t', fontSize=14, textColor=TEXT_GRAY, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("Pullback a 7120-7130", ParagraphStyle('t', fontSize=13, textColor=TEXT_WHITE, alignment=TA_CENTER)),
         Paragraph("Prezzo deve tornare verso PW", ParagraphStyle('t', fontSize=12, textColor=TEXT_GRAY, alignment=TA_CENTER))],
        [Paragraph("✅ ENTRA LONG", ParagraphStyle('t', fontSize=14, textColor=ACCENT_GREEN, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("~7125", ParagraphStyle('t', fontSize=14, textColor=ACCENT_GREEN, alignment=TA_CENTER)),
         Paragraph("Sopra Put Wall", ParagraphStyle('t', fontSize=12, textColor=TEXT_GRAY, alignment=TA_CENTER))],
        [Paragraph("🛑 STOP LOSS", ParagraphStyle('t', fontSize=14, textColor=ACCENT_RED, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("7112", ParagraphStyle('t', fontSize=14, textColor=ACCENT_RED, alignment=TA_CENTER)),
         Paragraph("Sotto PW — rischio 13 punti = $650", ParagraphStyle('t', fontSize=12, textColor=TEXT_GRAY, alignment=TA_CENTER))],
        [Paragraph("🎯 TARGET 1", ParagraphStyle('t', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("7155", ParagraphStyle('t', fontSize=14, textColor=ACCENT_YELLOW, alignment=TA_CENTER)),
         Paragraph("Chiude metà posizione — 3:1", ParagraphStyle('t', fontSize=12, textColor=TEXT_GRAY, alignment=TA_CENTER))],
        [Paragraph("🎯 TARGET 2", ParagraphStyle('t', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("7177", ParagraphStyle('t', fontSize=14, textColor=ACCENT_YELLOW, alignment=TA_CENTER)),
         Paragraph("ZGL — chiusura completa", ParagraphStyle('t', fontSize=12, textColor=TEXT_GRAY, alignment=TA_CENTER))],
    ]
    t = Table(data, colWidths=[4*cm, 4*cm, 10*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BG_CARD),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 1, HexColor('#334155')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [BG_CARD, HexColor('#0f172a')]),
    ]))
    story.append(t)
    story.append(PageBreak())

    # ─────────────────────────────────────────────
    # SLIDE 6: ESEMPIO PRATICO SHORT
    # ─────────────────────────────────────────────
    add_slide_header("📉 Esempio Pratico: SHORT su NQ", "Setup ribassista in atto adesso")
    story.append(Spacer(1, 0.3*cm))

    data = [
        [Paragraph("SETUP ATTUALE NQ (NAS100-F)", ParagraphStyle('h', fontSize=16, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("• Momentum Score: <b><font color='#ef4444'>69%</font></b> → BEARISH (sopra 70 = ipercomprato)", ParagraphStyle('t', fontSize=14, textColor=TEXT_WHITE, alignment=TA_LEFT))],
        [Paragraph("• ZGL (0GEX): <b><font color='#FFB300'>26910</font></b> — prezzo attuale 26885", ParagraphStyle('t', fontSize=14, textColor=TEXT_WHITE, alignment=TA_LEFT))],
        [Paragraph("• Alert: <b><font color='#ef4444'>▼ QQQ REVERSAL BEARISH</font></b> con Confluence 74%", ParagraphStyle('t', fontSize=14, textColor=TEXT_WHITE, alignment=TA_LEFT))],
        [Paragraph("• Call Wall: ~26905 (vicino al prezzo)", ParagraphStyle('t', fontSize=14, textColor=TEXT_WHITE, alignment=TA_LEFT))],
    ]
    t = Table(data, colWidths=[18*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BG_CARD),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 15),
        ('LINEBELOW', (0, 0), (-1, 0), 2, ACCENT_YELLOW),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.4*cm))

    data = [
        [Paragraph("AZIONE", ParagraphStyle('h', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("PREZZO", ParagraphStyle('h', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("NOTA", ParagraphStyle('h', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("⏳ ASPETTA", ParagraphStyle('t', fontSize=14, textColor=TEXT_GRAY, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("Rally a 26900-26920", ParagraphStyle('t', fontSize=13, textColor=TEXT_WHITE, alignment=TA_CENTER)),
         Paragraph("Prezzo deve salire verso CW", ParagraphStyle('t', fontSize=12, textColor=TEXT_GRAY, alignment=TA_CENTER))],
        [Paragraph("✅ ENTRA SHORT", ParagraphStyle('t', fontSize=14, textColor=ACCENT_RED, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("~26905", ParagraphStyle('t', fontSize=14, textColor=ACCENT_RED, alignment=TA_CENTER)),
         Paragraph("Al Call Wall", ParagraphStyle('t', fontSize=12, textColor=TEXT_GRAY, alignment=TA_CENTER))],
        [Paragraph("🛑 STOP LOSS", ParagraphStyle('t', fontSize=14, textColor=ACCENT_RED, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("26920", ParagraphStyle('t', fontSize=14, textColor=ACCENT_RED, alignment=TA_CENTER)),
         Paragraph("Sopra ZGL — rischio 15 punti", ParagraphStyle('t', fontSize=12, textColor=TEXT_GRAY, alignment=TA_CENTER))],
        [Paragraph("🎯 TARGET 1", ParagraphStyle('t', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("26750", ParagraphStyle('t', fontSize=14, textColor=ACCENT_YELLOW, alignment=TA_CENTER)),
         Paragraph("Chiude metà posizione", ParagraphStyle('t', fontSize=12, textColor=TEXT_GRAY, alignment=TA_CENTER))],
        [Paragraph("🎯 TARGET 2", ParagraphStyle('t', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("26600", ParagraphStyle('t', fontSize=14, textColor=ACCENT_YELLOW, alignment=TA_CENTER)),
         Paragraph("Supporto strutturale", ParagraphStyle('t', fontSize=12, textColor=TEXT_GRAY, alignment=TA_CENTER))],
    ]
    t = Table(data, colWidths=[4*cm, 4*cm, 10*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BG_CARD),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 1, HexColor('#334155')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [BG_CARD, HexColor('#0f172a')]),
    ]))
    story.append(t)
    story.append(PageBreak())

    # ─────────────────────────────────────────────
    # SLIDE 7: RIEPILOGO
    # ─────────────────────────────────────────────
    add_slide_header("✅ Checklist per Entrate", "Prima di entrare, controlla TUTTO")
    story.append(Spacer(1, 0.3*cm))

    data = [
        [Paragraph("✓", ParagraphStyle('h', fontSize=16, textColor=ACCENT_GREEN, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("CHECK", ParagraphStyle('h', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("QUANDO", ParagraphStyle('h', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("OK?", ParagraphStyle('h', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("1", ParagraphStyle('t', fontSize=16, textColor=TEXT_WHITE, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("Score < 30 (long) o > 70 (short)", ParagraphStyle('t', fontSize=13, textColor=TEXT_WHITE)),
         Paragraph("Scalping Signal panel", ParagraphStyle('t', fontSize=12, textColor=TEXT_GRAY)),
         Paragraph("[ ]", ParagraphStyle('t', fontSize=16, textColor=TEXT_GRAY, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("2", ParagraphStyle('t', fontSize=16, textColor=TEXT_WHITE, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("Prezzo vicino a PW (long) o CW (short)", ParagraphStyle('t', fontSize=13, textColor=TEXT_WHITE)),
         Paragraph("Chart — linea rossa o verde", ParagraphStyle('t', fontSize=12, textColor=TEXT_GRAY)),
         Paragraph("[ ]", ParagraphStyle('t', fontSize=16, textColor=TEXT_GRAY, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("3", ParagraphStyle('t', fontSize=16, textColor=TEXT_WHITE, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("Alert di reversal attivo", ParagraphStyle('t', fontSize=13, textColor=TEXT_WHITE)),
         Paragraph("Pannello ALERTS in basso", ParagraphStyle('t', fontSize=12, textColor=TEXT_GRAY)),
         Paragraph("[ ]", ParagraphStyle('t', fontSize=16, textColor=TEXT_GRAY, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("4", ParagraphStyle('t', fontSize=16, textColor=TEXT_WHITE, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("Confluence > 70%", ParagraphStyle('t', fontSize=13, textColor=TEXT_WHITE)),
         Paragraph("Nell'alert stesso", ParagraphStyle('t', fontSize=12, textColor=TEXT_GRAY)),
         Paragraph("[ ]", ParagraphStyle('t', fontSize=16, textColor=TEXT_GRAY, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("5", ParagraphStyle('t', fontSize=16, textColor=TEXT_WHITE, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("Stop loss oltre il livello GEX", ParagraphStyle('t', fontSize=13, textColor=TEXT_WHITE)),
         Paragraph("Calcola prima di entrare", ParagraphStyle('t', fontSize=12, textColor=TEXT_GRAY)),
         Paragraph("[ ]", ParagraphStyle('t', fontSize=16, textColor=TEXT_GRAY, fontName='Helvetica-Bold', alignment=TA_CENTER))],
    ]
    t = Table(data, colWidths=[1.5*cm, 9*cm, 5*cm, 2*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BG_CARD),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (3, 0), (3, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 1, HexColor('#334155')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [BG_CARD, HexColor('#0f172a')]),
    ]))
    story.append(t)

    story.append(Spacer(1, 0.8*cm))
    story.append(HRFlowable(width="80%", thickness=1, color=HexColor('#334155'), spaceAfter=10))
    story.append(Paragraph("<font color='#ef4444'>❌</font>  Se manca anche solo 1 check, NON entrare", ParagraphStyle('t', fontSize=16, textColor=TEXT_WHITE, fontName='Helvetica-Bold', alignment=TA_CENTER)))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph("<font color='#10b981'>✅</font>  Se tutti i 5 check sono OK, entra con confidenza", ParagraphStyle('t', fontSize=16, textColor=TEXT_WHITE, fontName='Helvetica-Bold', alignment=TA_CENTER)))

    story.append(PageBreak())

    # ─────────────────────────────────────────────
    # SLIDE 8: RISCHIO
    # ─────────────────────────────────────────────
    add_slide_header("⚠️ Gestione del Rischio", "Regole fisse — non cambiarle mai")
    story.append(Spacer(1, 0.5*cm))

    # Box rischio
    data = [
        [Paragraph("REGOLA", ParagraphStyle('h', fontSize=16, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("COME FARE", ParagraphStyle('h', fontSize=16, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("RISCHIO MAX", ParagraphStyle('t', fontSize=15, textColor=ACCENT_RED, fontName='Helvetica-Bold')),
         Paragraph("Non rischiare più dell'1% del conto per trade", ParagraphStyle('t', fontSize=14, textColor=TEXT_WHITE))],
        [Paragraph("STOP LOSS", ParagraphStyle('t', fontSize=15, textColor=ACCENT_RED, fontName='Helvetica-Bold')),
         Paragraph("Sempre oltre il livello GEX (PW o CW)", ParagraphStyle('t', fontSize=14, textColor=TEXT_WHITE))],
        [Paragraph("TAKE PROFIT", ParagraphStyle('t', fontSize=15, textColor=ACCENT_GREEN, fontName='Helvetica-Bold')),
         Paragraph("Al prossimo livello GEX — chiudi metà, sposta stop a breakeven", ParagraphStyle('t', fontSize=14, textColor=TEXT_WHITE))],
        [Paragraph("NO AVG DOWN", ParagraphStyle('t', fontSize=15, textColor=ACCENT_RED, fontName='Helvetica-Bold')),
         Paragraph("Mai aggiungere a posizioni in perdita", ParagraphStyle('t', fontSize=14, textColor=TEXT_WHITE))],
        [Paragraph("R:R MINIMO", ParagraphStyle('t', fontSize=15, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold')),
         Paragraph("3:1 obbligatorio — se il target è a meno di 3x lo stop, salta il trade", ParagraphStyle('t', fontSize=14, textColor=TEXT_WHITE))],
    ]
    t = Table(data, colWidths=[5*cm, 13*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BG_CARD),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 15),
        ('GRID', (0, 0), (-1, -1), 1, HexColor('#334155')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [BG_CARD, HexColor('#0f172a')]),
        ('LINEBELOW', (0, 0), (-1, 0), 2, ACCENT_YELLOW),
    ]))
    story.append(t)
    story.append(PageBreak())

    # ─────────────────────────────────────────────
    # SLIDE 9: COVER FINALE
    # ─────────────────────────────────────────────
    story.append(Spacer(1, 3*cm))
    story.append(Paragraph("GEX 4.0", styles['SlideTitle']))
    story.append(Paragraph("Trading con Intelligenza", styles['SlideSubtitle']))
    story.append(Spacer(1, 1*cm))
    story.append(HRFlowable(width="60%", thickness=2, color=ACCENT_YELLOW, spaceAfter=20))
    story.append(Spacer(1, 1*cm))

    data = [
        [Paragraph("I 3 PILASTRI", ParagraphStyle('t', fontSize=20, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("① Momentum Score  → Quando il mercato è esteso", ParagraphStyle('t', fontSize=16, textColor=TEXT_WHITE, alignment=TA_CENTER))],
        [Paragraph("② Livelli GEX    →  Dove il mercato rimbalza", ParagraphStyle('t', fontSize=16, textColor=TEXT_WHITE, alignment=TA_CENTER))],
        [Paragraph("③ Alerts System  →  Quando entrare", ParagraphStyle('t', fontSize=16, textColor=TEXT_WHITE, alignment=TA_CENTER))],
    ]
    t = Table(data, colWidths=[16*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BG_CARD),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LINEBELOW', (0, 0), (-1, 0), 2, ACCENT_YELLOW),
        ('LINEBELOW', (0, 1), (-1, 1), 1, HexColor('#334155')),
        ('LINEBELOW', (0, 2), (-1, 2), 1, HexColor('#334155')),
    ]))
    story.append(t)

    story.append(Spacer(1, 2*cm))
    story.append(Paragraph("Dashboard: <font color='#FFB300'>http://137.220.63.222</font>", styles['Footer']))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph("Ricorda: disciplina > intuizione. Segui la checklist ogni volta.", styles['Footer']))

    doc.build(story)
    print("Slides PDF generate: GEX_4.0_Slide_Trading.pdf")

if __name__ == "__main__":
    create_slides()
