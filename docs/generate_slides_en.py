#!/usr/bin/env python3
"""Generate GEX 4.0 trading slides PDF — ENGLISH VERSION"""

from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor, black, white
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image, HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
import os

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
        "/Users/paolo/Desktop/GEX 4.0/docs/GEX_4.0_Trading_Slides.pdf",
        pagesize=landscape(A4),
        rightMargin=1*cm,
        leftMargin=1*cm,
        topMargin=1*cm,
        bottomMargin=1*cm,
        title="GEX 4.0 — How to Enter the Market",
        author="GEX Dashboard"
    )

    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(name='SlideTitle', fontSize=36, textColor=ACCENT_YELLOW,
        fontName='Helvetica-Bold', alignment=TA_CENTER, spaceAfter=10, leading=42))
    styles.add(ParagraphStyle(name='SlideSubtitle', fontSize=18, textColor=TEXT_GRAY,
        fontName='Helvetica', alignment=TA_CENTER, spaceAfter=20))
    styles.add(ParagraphStyle(name='StepTitle', fontSize=28, textColor=ACCENT_YELLOW,
        fontName='Helvetica-Bold', spaceBefore=10, spaceAfter=8, leading=34))
    styles.add(ParagraphStyle(name='BodyBig', fontSize=16, textColor=TEXT_WHITE,
        fontName='Helvetica', spaceAfter=10, leading=22))
    styles.add(ParagraphStyle(name='BulletSlide', fontSize=15, textColor=TEXT_WHITE,
        fontName='Helvetica', spaceAfter=10, leading=22, leftIndent=20))
    styles.add(ParagraphStyle(name='Caption', fontSize=11, textColor=TEXT_GRAY,
        fontName='Helvetica', alignment=TA_CENTER, spaceAfter=6))
    styles.add(ParagraphStyle(name='Footer', fontSize=9, textColor=TEXT_GRAY,
        fontName='Helvetica', alignment=TA_CENTER))
    styles.add(ParagraphStyle(name='GreenText', fontSize=15, textColor=ACCENT_GREEN,
        fontName='Helvetica-Bold', spaceAfter=8, leading=20))
    styles.add(ParagraphStyle(name='RedText', fontSize=15, textColor=ACCENT_RED,
        fontName='Helvetica-Bold', spaceAfter=8, leading=20))
    styles.add(ParagraphStyle(name='YellowText', fontSize=15, textColor=ACCENT_YELLOW,
        fontName='Helvetica-Bold', spaceAfter=8, leading=20))

    story = []

    def add_bullet(text, color=None):
        c = {'green': '#10b981', 'red': '#ef4444', 'yellow': '#FFB300'}.get(color, '#f1f5f9')
        story.append(Paragraph(f'<font color="{c}">•</font>  {text}', styles['BulletSlide']))

    # ─── SLIDE 1: COVER ───────────────────────────────────────────────────
    story.append(Spacer(1, 3*cm))
    story.append(Paragraph("GEX 4.0", styles['SlideTitle']))
    story.append(Paragraph("How to Enter the Market", styles['SlideSubtitle']))
    story.append(Spacer(1, 1*cm))
    story.append(HRFlowable(width="60%", thickness=2, color=ACCENT_YELLOW, spaceAfter=20))
    story.append(Spacer(1, 1*cm))

    data = [
        [Paragraph("<b>3 THINGS TO CHECK</b>", ParagraphStyle('t', fontSize=22, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("① Momentum Score", ParagraphStyle('t', fontSize=18, textColor=ACCENT_GREEN, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("② GEX Levels (ZGL, CW, PW)", ParagraphStyle('t', fontSize=18, textColor=ACCENT_BLUE, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("③ Reversal Alerts", ParagraphStyle('t', fontSize=18, textColor=ACCENT_ORANGE, fontName='Helvetica-Bold', alignment=TA_CENTER))],
    ]
    t = Table(data, colWidths=[12*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0),(-1,-1), BG_CARD),
        ('ALIGN', (0,0),(-1,-1), 'CENTER'),
        ('VALIGN', (0,0),(-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0),(-1,-1), 12), ('BOTTOMPADDING', (0,0),(-1,-1), 12),
        ('LINEBELOW', (0,0),(-1,0), 2, ACCENT_YELLOW),
        ('LINEBELOW', (0,1),(-1,1), 1, HexColor('#334155')),
        ('LINEBELOW', (0,2),(-1,2), 1, HexColor('#334155')),
    ]))
    story.append(t)
    story.append(Spacer(1, 1.5*cm))
    story.append(Paragraph("Dashboard: <font color='#FFB300'>http://137.220.63.222</font>", styles['Footer']))
    story.append(PageBreak())

    # ─── SLIDE 2: MOMENTUM SCORE ─────────────────────────────────────────
    story.append(Paragraph("① Momentum Score", styles['StepTitle']))
    story.append(Paragraph("The market thermometer — always visible on screen", styles['SlideSubtitle']))
    story.append(Spacer(1, 0.3*cm))

    img_path = "/Users/paolo/Desktop/GEX 4.0/docs/screenshot_dashboard_1920.png"
    if os.path.exists(img_path):
        img = Image(img_path, width=14*cm, height=8*cm)
        story.append(img)
        story.append(Paragraph("Momentum Score (0-100) shown in the SCALPING SIGNAL panel", styles['Caption']))

    story.append(Spacer(1, 0.5*cm))

    data = [
        [Paragraph("SCORE", ParagraphStyle('h', fontSize=13, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("MEANING", ParagraphStyle('h', fontSize=13, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("ACTION", ParagraphStyle('h', fontSize=13, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("< 30", ParagraphStyle('t', fontSize=16, textColor=ACCENT_GREEN, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("Oversold — bounce likely", ParagraphStyle('t', fontSize=14, textColor=TEXT_WHITE, alignment=TA_CENTER)),
         Paragraph("Look for LONG", ParagraphStyle('t', fontSize=16, textColor=ACCENT_GREEN, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("30–60", ParagraphStyle('t', fontSize=16, textColor=TEXT_GRAY, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("Neutral — no directional trade", ParagraphStyle('t', fontSize=14, textColor=TEXT_GRAY, alignment=TA_CENTER)),
         Paragraph("STAY OUT", ParagraphStyle('t', fontSize=16, textColor=TEXT_GRAY, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("> 70", ParagraphStyle('t', fontSize=16, textColor=ACCENT_RED, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("Overbought — drop likely", ParagraphStyle('t', fontSize=14, textColor=TEXT_WHITE, alignment=TA_CENTER)),
         Paragraph("Look for SHORT", ParagraphStyle('t', fontSize=16, textColor=ACCENT_RED, fontName='Helvetica-Bold', alignment=TA_CENTER))],
    ]
    t = Table(data, colWidths=[4*cm, 10*cm, 4*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0),(-1,0), BG_CARD),
        ('BACKGROUND', (0,1),(-1,1), GREEN_BG),
        ('BACKGROUND', (0,2),(-1,2), BG_CARD),
        ('BACKGROUND', (0,3),(-1,3), RED_BG),
        ('ALIGN', (0,0),(-1,-1), 'CENTER'),
        ('VALIGN', (0,0),(-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0),(-1,-1), 10), ('BOTTOMPADDING', (0,0),(-1,-1), 10),
        ('GRID', (0,0),(-1,-1), 1, HexColor('#334155')),
    ]))
    story.append(t)
    story.append(PageBreak())

    # ─── SLIDE 3: GEX LEVELS ─────────────────────────────────────────────
    story.append(Paragraph("② GEX Levels on the Chart", styles['StepTitle']))
    story.append(Paragraph("Yellow, green and red horizontal lines — here's what they mean", styles['SlideSubtitle']))
    story.append(Spacer(1, 0.3*cm))

    data = [
        [Paragraph("COLOR", ParagraphStyle('h', fontSize=13, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("LEVEL", ParagraphStyle('h', fontSize=13, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("MEANING", ParagraphStyle('h', fontSize=13, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("WHEN TO ENTER", ParagraphStyle('h', fontSize=13, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph(" YELLOW ", ParagraphStyle('t', fontSize=14, textColor=black, fontName='Helvetica-Bold', alignment=TA_CENTER, backColor=ACCENT_YELLOW)),
         Paragraph("0GEX (ZGL)", ParagraphStyle('t', fontSize=13, textColor=TEXT_WHITE, fontName='Helvetica-Bold')),
         Paragraph("Equilibrium point — reversal trigger", ParagraphStyle('t', fontSize=12, textColor=TEXT_WHITE)),
         Paragraph("Price returns toward ZGL from far away", ParagraphStyle('t', fontSize=12, textColor=ACCENT_GREEN))],
        [Paragraph(" GREEN ", ParagraphStyle('t', fontSize=14, textColor=black, fontName='Helvetica-Bold', alignment=TA_CENTER, backColor=ACCENT_GREEN)),
         Paragraph("CW (Call Wall)", ParagraphStyle('t', fontSize=13, textColor=TEXT_WHITE, fontName='Helvetica-Bold')),
         Paragraph("Resistance — MM must sell", ParagraphStyle('t', fontSize=12, textColor=TEXT_WHITE)),
         Paragraph("Price rises to CW + Score > 70", ParagraphStyle('t', fontSize=12, textColor=ACCENT_RED))],
        [Paragraph(" RED ", ParagraphStyle('t', fontSize=14, textColor=white, fontName='Helvetica-Bold', alignment=TA_CENTER, backColor=ACCENT_RED)),
         Paragraph("PW (Put Wall)", ParagraphStyle('t', fontSize=13, textColor=TEXT_WHITE, fontName='Helvetica-Bold')),
         Paragraph("Support — MM must buy", ParagraphStyle('t', fontSize=12, textColor=TEXT_WHITE)),
         Paragraph("Price drops to PW + Score < 30", ParagraphStyle('t', fontSize=12, textColor=ACCENT_GREEN))],
    ]
    t = Table(data, colWidths=[3*cm, 4*cm, 7*cm, 6*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0),(-1,0), BG_CARD),
        ('BACKGROUND', (0,1),(-1,1), HexColor('#1a2e1a')),
        ('BACKGROUND', (0,2),(-1,2), BG_CARD),
        ('BACKGROUND', (0,3),(-1,3), HexColor('#2a1a1a')),
        ('ALIGN', (0,0),(0,-1), 'CENTER'),
        ('ALIGN', (1,0),(-1,-1), 'LEFT'),
        ('VALIGN', (0,0),(-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0),(-1,-1), 10), ('BOTTOMPADDING', (0,0),(-1,-1), 10),
        ('LEFTPADDING', (0,0),(-1,-1), 8),
        ('GRID', (0,0),(-1,-1), 1, HexColor('#334155')),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.5*cm))
    add_bullet("Find these levels as colored horizontal lines on the ES/NQ chart at the top", 'yellow')
    add_bullet("ZGL (0GEX) is where the market is in equilibrium — closer = more likely reversal")
    add_bullet("Call Wall (green) = resistance. Put Wall (red) = support")
    story.append(PageBreak())

    # ─── SLIDE 4: ALERTS ───────────────────────────────────────────────────
    story.append(Paragraph("③ Reversal Alerts", styles['StepTitle']))
    story.append(Paragraph("The system tells you when to enter — in the ALERTS panel", styles['SlideSubtitle']))
    story.append(Spacer(1, 0.3*cm))

    data = [
        [Paragraph("ALERT", ParagraphStyle('h', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("WHAT IT MEANS", ParagraphStyle('h', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("WHAT TO DO", ParagraphStyle('h', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("▲ SPX REVERSAL BULLISH", ParagraphStyle('t', fontSize=13, textColor=ACCENT_GREEN, fontName='Helvetica-Bold')),
         Paragraph("Price is bouncing — bullish bias", ParagraphStyle('t', fontSize=12, textColor=TEXT_WHITE)),
         Paragraph("Enter LONG near the Put Wall", ParagraphStyle('t', fontSize=13, textColor=ACCENT_GREEN, fontName='Helvetica-Bold'))],
        [Paragraph("▼ QQQ REVERSAL BEARISH", ParagraphStyle('t', fontSize=13, textColor=ACCENT_RED, fontName='Helvetica-Bold')),
         Paragraph("Price is falling — bearish bias", ParagraphStyle('t', fontSize=12, textColor=TEXT_WHITE)),
         Paragraph("Enter SHORT near the Call Wall", ParagraphStyle('t', fontSize=13, textColor=ACCENT_RED, fontName='Helvetica-Bold'))],
    ]
    t = Table(data, colWidths=[5*cm, 8*cm, 7*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0),(-1,0), BG_CARD),
        ('BACKGROUND', (0,1),(-1,1), GREEN_BG),
        ('BACKGROUND', (0,2),(-1,2), RED_BG),
        ('ALIGN', (0,0),(0,-1), 'LEFT'),
        ('ALIGN', (1,0),(-1,-1), 'LEFT'),
        ('VALIGN', (0,0),(-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0),(-1,-1), 12), ('BOTTOMPADDING', (0,0),(-1,-1), 12),
        ('LEFTPADDING', (0,0),(-1,-1), 12),
        ('GRID', (0,0),(-1,-1), 1, HexColor('#334155')),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.5*cm))
    add_bullet("Alerts appear in the ALERTS panel at the bottom right", 'yellow')
    add_bullet("Confluence = how much the indicators agree (higher = safer)")
    add_bullet("Example: 'Confluence: 76%' means 3 out of 4 indicators say LONG")
    story.append(PageBreak())

    # ─── SLIDE 5: LONG EXAMPLE ────────────────────────────────────────────
    story.append(Paragraph("📈 Practical Example: LONG on ES", styles['StepTitle']))
    story.append(Paragraph("Bullish setup right now", styles['SlideSubtitle']))
    story.append(Spacer(1, 0.3*cm))

    data = [
        [Paragraph("CURRENT ES SETUP (US500-F)", ParagraphStyle('h', fontSize=16, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("• Momentum Score: <b><font color='#10b981'>69%</font></b> → BEARISH (near 70 = overbought)", ParagraphStyle('t', fontSize=14, textColor=TEXT_WHITE, alignment=TA_LEFT))],
        [Paragraph("• ZGL (0GEX): <b><font color='#FFB300'>7177</font></b> — current price 7179", ParagraphStyle('t', fontSize=14, textColor=TEXT_WHITE, alignment=TA_LEFT))],
        [Paragraph("• Alert: <b><font color='#10b981'>▲ SPX REVERSAL BULLISH</font></b> with Confluence 76%", ParagraphStyle('t', fontSize=14, textColor=TEXT_WHITE, alignment=TA_LEFT))],
        [Paragraph("• Key Level: 7120.3 (Put Wall)", ParagraphStyle('t', fontSize=14, textColor=TEXT_WHITE, alignment=TA_LEFT))],
    ]
    t = Table(data, colWidths=[18*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0),(-1,-1), BG_CARD),
        ('TOPPADDING', (0,0),(-1,-1), 8), ('BOTTOMPADDING', (0,0),(-1,-1), 8),
        ('LEFTPADDING', (0,0),(-1,-1), 15),
        ('LINEBELOW', (0,0),(-1,0), 2, ACCENT_YELLOW),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.4*cm))

    data = [
        [Paragraph("ACTION", ParagraphStyle('h', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("PRICE", ParagraphStyle('h', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("NOTE", ParagraphStyle('h', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("⏳ WAIT", ParagraphStyle('t', fontSize=14, textColor=TEXT_GRAY, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("Pullback to 7120–7130", ParagraphStyle('t', fontSize=13, textColor=TEXT_WHITE, alignment=TA_CENTER)),
         Paragraph("Price must return toward PW", ParagraphStyle('t', fontSize=12, textColor=TEXT_GRAY, alignment=TA_CENTER))],
        [Paragraph("✅ GO LONG", ParagraphStyle('t', fontSize=14, textColor=ACCENT_GREEN, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("~7125", ParagraphStyle('t', fontSize=14, textColor=ACCENT_GREEN, alignment=TA_CENTER)),
         Paragraph("Above Put Wall", ParagraphStyle('t', fontSize=12, textColor=TEXT_GRAY, alignment=TA_CENTER))],
        [Paragraph("🛑 STOP LOSS", ParagraphStyle('t', fontSize=14, textColor=ACCENT_RED, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("7112", ParagraphStyle('t', fontSize=14, textColor=ACCENT_RED, alignment=TA_CENTER)),
         Paragraph("Below PW — risk 13 pts = $650", ParagraphStyle('t', fontSize=12, textColor=TEXT_GRAY, alignment=TA_CENTER))],
        [Paragraph("🎯 TARGET 1", ParagraphStyle('t', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("7155", ParagraphStyle('t', fontSize=14, textColor=ACCENT_YELLOW, alignment=TA_CENTER)),
         Paragraph("Close half — 3:1 ratio", ParagraphStyle('t', fontSize=12, textColor=TEXT_GRAY, alignment=TA_CENTER))],
        [Paragraph("🎯 TARGET 2", ParagraphStyle('t', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("7177", ParagraphStyle('t', fontSize=14, textColor=ACCENT_YELLOW, alignment=TA_CENTER)),
         Paragraph("ZGL — close full position", ParagraphStyle('t', fontSize=12, textColor=TEXT_GRAY, alignment=TA_CENTER))],
    ]
    t = Table(data, colWidths=[4*cm, 4*cm, 10*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0),(-1,0), BG_CARD),
        ('ALIGN', (0,0),(-1,-1), 'CENTER'),
        ('VALIGN', (0,0),(-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0),(-1,-1), 8), ('BOTTOMPADDING', (0,0),(-1,-1), 8),
        ('GRID', (0,0),(-1,-1), 1, HexColor('#334155')),
        ('ROWBACKGROUNDS', (0,1),(-1,-1), [BG_CARD, HexColor('#0f172a')]),
    ]))
    story.append(t)
    story.append(PageBreak())

    # ─── SLIDE 6: SHORT EXAMPLE ────────────────────────────────────────────
    story.append(Paragraph("📉 Practical Example: SHORT on NQ", styles['StepTitle']))
    story.append(Paragraph("Bearish setup right now", styles['SlideSubtitle']))
    story.append(Spacer(1, 0.3*cm))

    data = [
        [Paragraph("CURRENT NQ SETUP (NAS100-F)", ParagraphStyle('h', fontSize=16, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("• Momentum Score: <b><font color='#ef4444'>69%</font></b> → BEARISH (above 70 = overbought)", ParagraphStyle('t', fontSize=14, textColor=TEXT_WHITE, alignment=TA_LEFT))],
        [Paragraph("• ZGL (0GEX): <b><font color='#FFB300'>26910</font></b> — current price 26885", ParagraphStyle('t', fontSize=14, textColor=TEXT_WHITE, alignment=TA_LEFT))],
        [Paragraph("• Alert: <b><font color='#ef4444'>▼ QQQ REVERSAL BEARISH</font></b> with Confluence 74%", ParagraphStyle('t', fontSize=14, textColor=TEXT_WHITE, alignment=TA_LEFT))],
        [Paragraph("• Call Wall: ~26905 (near current price)", ParagraphStyle('t', fontSize=14, textColor=TEXT_WHITE, alignment=TA_LEFT))],
    ]
    t = Table(data, colWidths=[18*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0),(-1,-1), BG_CARD),
        ('TOPPADDING', (0,0),(-1,-1), 8), ('BOTTOMPADDING', (0,0),(-1,-1), 8),
        ('LEFTPADDING', (0,0),(-1,-1), 15),
        ('LINEBELOW', (0,0),(-1,0), 2, ACCENT_YELLOW),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.4*cm))

    data = [
        [Paragraph("ACTION", ParagraphStyle('h', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("PRICE", ParagraphStyle('h', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("NOTE", ParagraphStyle('h', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("⏳ WAIT", ParagraphStyle('t', fontSize=14, textColor=TEXT_GRAY, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("Rally to 26900–26920", ParagraphStyle('t', fontSize=13, textColor=TEXT_WHITE, alignment=TA_CENTER)),
         Paragraph("Price must rise toward CW", ParagraphStyle('t', fontSize=12, textColor=TEXT_GRAY, alignment=TA_CENTER))],
        [Paragraph("✅ GO SHORT", ParagraphStyle('t', fontSize=14, textColor=ACCENT_RED, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("~26905", ParagraphStyle('t', fontSize=14, textColor=ACCENT_RED, alignment=TA_CENTER)),
         Paragraph("At the Call Wall", ParagraphStyle('t', fontSize=12, textColor=TEXT_GRAY, alignment=TA_CENTER))],
        [Paragraph("🛑 STOP LOSS", ParagraphStyle('t', fontSize=14, textColor=ACCENT_RED, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("26920", ParagraphStyle('t', fontSize=14, textColor=ACCENT_RED, alignment=TA_CENTER)),
         Paragraph("Above ZGL — risk 15 pts", ParagraphStyle('t', fontSize=12, textColor=TEXT_GRAY, alignment=TA_CENTER))],
        [Paragraph("🎯 TARGET 1", ParagraphStyle('t', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("26750", ParagraphStyle('t', fontSize=14, textColor=ACCENT_YELLOW, alignment=TA_CENTER)),
         Paragraph("Close half position", ParagraphStyle('t', fontSize=12, textColor=TEXT_GRAY, alignment=TA_CENTER))],
        [Paragraph("🎯 TARGET 2", ParagraphStyle('t', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("26600", ParagraphStyle('t', fontSize=14, textColor=ACCENT_YELLOW, alignment=TA_CENTER)),
         Paragraph("Structural support", ParagraphStyle('t', fontSize=12, textColor=TEXT_GRAY, alignment=TA_CENTER))],
    ]
    t = Table(data, colWidths=[4*cm, 4*cm, 10*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0),(-1,0), BG_CARD),
        ('ALIGN', (0,0),(-1,-1), 'CENTER'),
        ('VALIGN', (0,0),(-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0),(-1,-1), 8), ('BOTTOMPADDING', (0,0),(-1,-1), 8),
        ('GRID', (0,0),(-1,-1), 1, HexColor('#334155')),
        ('ROWBACKGROUNDS', (0,1),(-1,-1), [BG_CARD, HexColor('#0f172a')]),
    ]))
    story.append(t)
    story.append(PageBreak())

    # ─── SLIDE 7: CHECKLIST ───────────────────────────────────────────────
    story.append(Paragraph("✅ Entry Checklist", styles['StepTitle']))
    story.append(Paragraph("Before entering — check EVERYTHING", styles['SlideSubtitle']))
    story.append(Spacer(1, 0.3*cm))

    data = [
        [Paragraph("#", ParagraphStyle('h', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("CHECK", ParagraphStyle('h', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("WHERE TO LOOK", ParagraphStyle('h', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("✓", ParagraphStyle('h', fontSize=14, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("1", ParagraphStyle('t', fontSize=16, textColor=TEXT_WHITE, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("Score < 30 (long) or > 70 (short)", ParagraphStyle('t', fontSize=13, textColor=TEXT_WHITE)),
         Paragraph("Scalping Signal panel", ParagraphStyle('t', fontSize=12, textColor=TEXT_GRAY)),
         Paragraph("[  ]", ParagraphStyle('t', fontSize=16, textColor=TEXT_GRAY, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("2", ParagraphStyle('t', fontSize=16, textColor=TEXT_WHITE, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("Price near PW (long) or CW (short)", ParagraphStyle('t', fontSize=13, textColor=TEXT_WHITE)),
         Paragraph("Chart — red or green line", ParagraphStyle('t', fontSize=12, textColor=TEXT_GRAY)),
         Paragraph("[  ]", ParagraphStyle('t', fontSize=16, textColor=TEXT_GRAY, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("3", ParagraphStyle('t', fontSize=16, textColor=TEXT_WHITE, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("Reversal alert is active", ParagraphStyle('t', fontSize=13, textColor=TEXT_WHITE)),
         Paragraph("ALERTS panel at bottom", ParagraphStyle('t', fontSize=12, textColor=TEXT_GRAY)),
         Paragraph("[  ]", ParagraphStyle('t', fontSize=16, textColor=TEXT_GRAY, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("4", ParagraphStyle('t', fontSize=16, textColor=TEXT_WHITE, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("Confluence > 70%", ParagraphStyle('t', fontSize=13, textColor=TEXT_WHITE)),
         Paragraph("Shown in the alert itself", ParagraphStyle('t', fontSize=12, textColor=TEXT_GRAY)),
         Paragraph("[  ]", ParagraphStyle('t', fontSize=16, textColor=TEXT_GRAY, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("5", ParagraphStyle('t', fontSize=16, textColor=TEXT_WHITE, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("Stop loss beyond the GEX level", ParagraphStyle('t', fontSize=13, textColor=TEXT_WHITE)),
         Paragraph("Calculate before entry", ParagraphStyle('t', fontSize=12, textColor=TEXT_GRAY)),
         Paragraph("[  ]", ParagraphStyle('t', fontSize=16, textColor=TEXT_GRAY, fontName='Helvetica-Bold', alignment=TA_CENTER))],
    ]
    t = Table(data, colWidths=[1.5*cm, 9*cm, 5.5*cm, 1.5*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0),(-1,0), BG_CARD),
        ('ALIGN', (0,0),(-1,-1), 'LEFT'),
        ('ALIGN', (0,0),(0,-1), 'CENTER'),
        ('ALIGN', (3,0),(3,-1), 'CENTER'),
        ('VALIGN', (0,0),(-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0),(-1,-1), 10), ('BOTTOMPADDING', (0,0),(-1,-1), 10),
        ('LEFTPADDING', (0,0),(-1,-1), 8),
        ('GRID', (0,0),(-1,-1), 1, HexColor('#334155')),
        ('ROWBACKGROUNDS', (0,1),(-1,-1), [BG_CARD, HexColor('#0f172a')]),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.8*cm))
    story.append(HRFlowable(width="80%", thickness=1, color=HexColor('#334155'), spaceAfter=10))
    story.append(Paragraph("<font color='#ef4444'>✗</font>  If even 1 check is missing — DO NOT enter", ParagraphStyle('t', fontSize=16, textColor=TEXT_WHITE, fontName='Helvetica-Bold', alignment=TA_CENTER)))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph("<font color='#10b981'>✓</font>  If all 5 checks pass — enter with confidence", ParagraphStyle('t', fontSize=16, textColor=TEXT_WHITE, fontName='Helvetica-Bold', alignment=TA_CENTER)))
    story.append(PageBreak())

    # ─── SLIDE 8: RISK ────────────────────────────────────────────────────
    story.append(Paragraph("⚠️ Risk Management", styles['StepTitle']))
    story.append(Paragraph("Fixed rules — never break them", styles['SlideSubtitle']))
    story.append(Spacer(1, 0.5*cm))

    data = [
        [Paragraph("RULE", ParagraphStyle('h', fontSize=16, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("HOW TO APPLY", ParagraphStyle('h', fontSize=16, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("MAX RISK", ParagraphStyle('t', fontSize=15, textColor=ACCENT_RED, fontName='Helvetica-Bold')),
         Paragraph("Never risk more than 1% of account per trade", ParagraphStyle('t', fontSize=14, textColor=TEXT_WHITE))],
        [Paragraph("STOP LOSS", ParagraphStyle('t', fontSize=15, textColor=ACCENT_RED, fontName='Helvetica-Bold')),
         Paragraph("Always beyond the GEX level (PW or CW)", ParagraphStyle('t', fontSize=14, textColor=TEXT_WHITE))],
        [Paragraph("TAKE PROFIT", ParagraphStyle('t', fontSize=15, textColor=ACCENT_GREEN, fontName='Helvetica-Bold')),
         Paragraph("At next GEX level — close half, move stop to breakeven", ParagraphStyle('t', fontSize=14, textColor=TEXT_WHITE))],
        [Paragraph("NO AVG DOWN", ParagraphStyle('t', fontSize=15, textColor=ACCENT_RED, fontName='Helvetica-Bold')),
         Paragraph("Never add to losing positions", ParagraphStyle('t', fontSize=14, textColor=TEXT_WHITE))],
        [Paragraph("MIN R:R", ParagraphStyle('t', fontSize=15, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold')),
         Paragraph("3:1 mandatory — if target is less than 3x the stop, skip the trade", ParagraphStyle('t', fontSize=14, textColor=TEXT_WHITE))],
    ]
    t = Table(data, colWidths=[5*cm, 13*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0),(-1,0), BG_CARD),
        ('ALIGN', (0,0),(-1,-1), 'LEFT'),
        ('VALIGN', (0,0),(-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0),(-1,-1), 10), ('BOTTOMPADDING', (0,0),(-1,-1), 10),
        ('LEFTPADDING', (0,0),(-1,-1), 15),
        ('GRID', (0,0),(-1,-1), 1, HexColor('#334155')),
        ('ROWBACKGROUNDS', (0,1),(-1,-1), [BG_CARD, HexColor('#0f172a')]),
        ('LINEBELOW', (0,0),(-1,0), 2, ACCENT_YELLOW),
    ]))
    story.append(t)
    story.append(PageBreak())

    # ─── SLIDE 9: FINAL COVER ─────────────────────────────────────────────
    story.append(Spacer(1, 3*cm))
    story.append(Paragraph("GEX 4.0", styles['SlideTitle']))
    story.append(Paragraph("Trade with Intelligence", styles['SlideSubtitle']))
    story.append(Spacer(1, 1*cm))
    story.append(HRFlowable(width="60%", thickness=2, color=ACCENT_YELLOW, spaceAfter=20))
    story.append(Spacer(1, 1*cm))

    data = [
        [Paragraph("THE 3 PILLARS", ParagraphStyle('t', fontSize=20, textColor=ACCENT_YELLOW, fontName='Helvetica-Bold', alignment=TA_CENTER))],
        [Paragraph("① Momentum Score  →  When the market is extended", ParagraphStyle('t', fontSize=16, textColor=TEXT_WHITE, alignment=TA_CENTER))],
        [Paragraph("② GEX Levels    →  Where the market bounces", ParagraphStyle('t', fontSize=16, textColor=TEXT_WHITE, alignment=TA_CENTER))],
        [Paragraph("③ Alert System  →  When to enter", ParagraphStyle('t', fontSize=16, textColor=TEXT_WHITE, alignment=TA_CENTER))],
    ]
    t = Table(data, colWidths=[16*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0),(-1,-1), BG_CARD),
        ('ALIGN', (0,0),(-1,-1), 'CENTER'),
        ('TOPPADDING', (0,0),(-1,-1), 10), ('BOTTOMPADDING', (0,0),(-1,-1), 10),
        ('LINEBELOW', (0,0),(-1,0), 2, ACCENT_YELLOW),
        ('LINEBELOW', (0,1),(-1,1), 1, HexColor('#334155')),
        ('LINEBELOW', (0,2),(-1,2), 1, HexColor('#334155')),
    ]))
    story.append(t)
    story.append(Spacer(1, 2*cm))
    story.append(Paragraph("Dashboard: <font color='#FFB300'>http://137.220.63.222</font>", styles['Footer']))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph("Remember: discipline > intuition. Follow the checklist every time.", styles['Footer']))

    doc.build(story)
    print("English slides PDF generated: GEX_4.0_Trading_Slides.pdf")

if __name__ == "__main__":
    create_slides()
