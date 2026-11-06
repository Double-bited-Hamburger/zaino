"""PDF con tutti i compiti assegnati dal primo giorno, in ordine di consegna."""

import io
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from pdf_settimana import ACCENT, GIORNI, HEAD, INK, LINE, MARGINE, MESI, MUTED, _font, _giorno


def genera(pagina):
    """`pagina`: l'output di dati.elabora con lo stato. Restituisce i byte del PDF."""
    normale, grassetto = _font()
    testo = ParagraphStyle("testo", fontName=normale, fontSize=8.5, leading=11, textColor=INK)
    piccolo = ParagraphStyle("piccolo", parent=testo, textColor=MUTED)
    testa = ParagraphStyle("testa", parent=testo, fontName=grassetto)
    titolo = ParagraphStyle("titolo", parent=testo, fontName=grassetto, fontSize=17, leading=21)

    fatti = (pagina.get("stato") or {}).get("fatti", {})
    compiti = sorted(pagina["compiti_anno"], key=lambda c: (c["consegna"], c["materia"]))
    if not compiti:
        raise ValueError("Nessun compito nei dati scaricati: aggiorna i dati.")

    righe = [[Paragraph(t, testa) for t in ("Consegna", "Materia", "Compito", "Fatto")]]
    stili = [
        ("GRID", (0, 0), (-1, -1), 0.5, LINE), ("BACKGROUND", (0, 0), (-1, 0), HEAD), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    precedente = None
    for c in compiti:
        giorno = _giorno(c["consegna"])
        nuovo = c["consegna"] != precedente
        if nuovo and precedente is not None:
            stili.append(("LINEABOVE", (0, len(righe)), (-1, len(righe)), 1, ACCENT))
        precedente = c["consegna"]
        righe.append([
            Paragraph(f"<b>{GIORNI[giorno.weekday()][:3]} {giorno.day} {MESI[giorno.month - 1][:3]} {giorno.year}</b>" if nuovo else "", testo),
            Paragraph(f"<b>{escape(c['materia'])}</b><br/><font color='#5d6678'>{escape(c['docente'] or '')}</font>", testo),
            Paragraph(escape(c["testo"]), testo),
            Paragraph("sì" if c["id"] in fatti else "no", testo),
        ])
    larghezza = A4[0] - 2 * MARGINE
    tabella = Table(righe, colWidths=[27 * mm, 36 * mm, larghezza - 27 * mm - 36 * mm - 11 * mm, 11 * mm], repeatRows=1)
    tabella.setStyle(TableStyle(stili))

    primo, ultimo = _giorno(compiti[0]["consegna"]), _giorno(compiti[-1]["consegna"])
    nfatti = sum(c["id"] in fatti for c in compiti)
    storia = [
        Paragraph("Tutti i compiti assegnati", titolo),
        Paragraph(
            f"{escape(pagina.get('studente') or '')}{' · classe ' + escape(pagina['classe']) if pagina.get('classe') else ''} · "
            f"dal {primo.strftime('%d/%m/%Y')} al {ultimo.strftime('%d/%m/%Y')} · {len(compiti)} compiti, {nfatti} spuntati come fatti · "
            f"creato il {datetime.now():%d/%m/%Y}", piccolo),
        Spacer(1, 8),
        tabella,
    ]

    def piede(canvas, doc):
        canvas.saveState()
        canvas.setFont(normale, 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(A4[0] - MARGINE, 6 * mm, f"Pagina {doc.page}")
        canvas.restoreState()

    buffer = io.BytesIO()
    SimpleDocTemplate(buffer, pagesize=A4, leftMargin=MARGINE, rightMargin=MARGINE, topMargin=12 * mm, bottomMargin=12 * mm,
                      title="Tutti i compiti").build(storia, onFirstPage=piede, onLaterPages=piede)
    return buffer.getvalue()
