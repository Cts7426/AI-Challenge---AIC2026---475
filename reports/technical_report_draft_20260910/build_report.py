"""Dàn trang bản thảo từ Markdown; không đọc hay thay đổi artifact thi."""
from pathlib import Path
import re
from xml.sax.saxutils import escape
import xml.etree.ElementTree as ET

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Flowable
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parents[1] / 'output' / 'pdf'
OUT.mkdir(parents=True, exist_ok=True)
for name, file in [('Arial', 'arial.ttf'), ('Arial-Bold', 'arialbd.ttf'), ('Arial-Italic', 'ariali.ttf')]:
    pdfmetrics.registerFont(TTFont(name, str(Path('C:/Windows/Fonts') / file)))
pdfmetrics.registerFontFamily('Arial', normal='Arial', bold='Arial-Bold', italic='Arial-Italic', boldItalic='Arial-Bold')
PAGE_W, PAGE_H = A4
MARGIN = 43
WIDTH = PAGE_W - 2 * MARGIN
STYLES = {
    'body': ParagraphStyle('body', fontName='Arial', fontSize=10.5, leading=14.2, alignment=TA_JUSTIFY, spaceAfter=6),
    'title': ParagraphStyle('title', fontName='Arial-Bold', fontSize=16, leading=20, spaceAfter=7),
    'h1': ParagraphStyle('h1', fontName='Arial-Bold', fontSize=12.4, leading=16, spaceBefore=7, spaceAfter=6, keepWithNext=True),
    'h2': ParagraphStyle('h2', fontName='Arial-Bold', fontSize=10.8, leading=14.3, spaceBefore=6, spaceAfter=4, keepWithNext=True),
    'caption': ParagraphStyle('caption', fontName='Arial-Italic', fontSize=9, leading=12, spaceBefore=5, spaceAfter=6),
    'ref': ParagraphStyle('ref', fontName='Arial', fontSize=8.4, leading=10.9, spaceAfter=3, splitLongWords=True),
    'cell': ParagraphStyle('cell', fontName='Arial', fontSize=9, leading=12),
    'cellhead': ParagraphStyle('cellhead', fontName='Arial-Bold', fontSize=9, leading=12),
    'center': ParagraphStyle('center', fontName='Arial', fontSize=10, leading=13, alignment=TA_CENTER),
}

class Architecture(Flowable):
    """Vẽ đúng tập con SVG tĩnh của hình kiến trúc bằng vector PDF."""
    def __init__(self):
        super().__init__()
        self.root = ET.parse(ROOT / 'architecture.svg').getroot()
        self.factor = WIDTH / 1000
        self.width, self.height = WIDTH, 470 * self.factor

    def draw(self):
        c = self.canv
        c.saveState(); c.scale(self.factor, self.factor)
        def visit(el, inherited):
            attrs = dict(inherited); attrs.update(el.attrib)
            tag = el.tag.split('}')[-1]
            fill, stroke = attrs.get('fill', 'black'), attrs.get('stroke', 'none')
            c.saveState()
            if fill != 'none': c.setFillColor(colors.HexColor(fill) if fill.startswith('#') else colors.toColor(fill))
            if stroke != 'none': c.setStrokeColor(colors.HexColor(stroke) if stroke.startswith('#') else colors.toColor(stroke))
            c.setLineWidth(float(attrs.get('stroke-width',1)))
            dash = attrs.get('stroke-dasharray')
            c.setDash([float(n) for n in dash.split()] if dash else [])
            if tag == 'rect':
                x,y,w,h = [float(attrs.get(k,0)) for k in ('x','y','width','height')]
                c.roundRect(x,470-y-h,w,h,float(attrs.get('rx',0)),stroke=stroke!='none',fill=fill!='none')
            elif tag == 'text':
                c.setFont('Arial-Bold' if attrs.get('font-weight')=='bold' else 'Arial', float(attrs.get('font-size',19)))
                x,y = float(attrs['x']),470-float(attrs['y'])
                if attrs.get('text-anchor') == 'middle': c.drawCentredString(x,y,el.text or '')
                else: c.drawString(x,y,el.text or '')
            elif tag == 'path':
                tokens = re.findall(r'[MLHV]|-?\d+(?:\.\d+)?',attrs['d'])
                p=c.beginPath(); i=0; x=y=0
                while i<len(tokens):
                    cmd=tokens[i]; i+=1
                    if cmd in ('M','L'):
                        x,y=float(tokens[i]),float(tokens[i+1]); i+=2
                        (p.moveTo if cmd=='M' else p.lineTo)(x,470-y)
                    elif cmd=='H': x=float(tokens[i]); i+=1; p.lineTo(x,470-y)
                    elif cmd=='V': y=float(tokens[i]); i+=1; p.lineTo(x,470-y)
                    else: raise ValueError(f'Unsupported SVG path {cmd}')
                c.drawPath(p,stroke=stroke!='none',fill=fill!='none')
            for child in el: visit(child,attrs)
            c.restoreState()
        visit(self.root,{})
        c.restoreState()

def inline(text):
    """Chuyển markup giới hạn sang Paragraph XML; không thực thi nội dung."""
    text = escape(text).replace('–', '-').replace('—', '-')
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'(https://[^\s]+)', r'<link href="\1" color="#23445c">\1</link>', text)
    return text

def table(lines):
    """Tạo bảng tự tăng chiều cao, giữ qualification cùng cell."""
    rows = [[c.strip() for c in line.strip('|').split('|')] for line in lines]
    rows = [row for row in rows if not all(re.fullmatch(r'[-: ]+', cell) for cell in row)]
    widths = [WIDTH*x for x in ([.22, .30, .21, .27] if len(rows[0]) == 4 else [.13, .34, .53])]
    values = [[Paragraph(inline(c), STYLES['cellhead' if i == 0 else ('center' if len(row)==3 else 'cell')]) for c in row] for i,row in enumerate(rows)]
    tab = Table(values, colWidths=widths, repeatRows=1, hAlign='LEFT')
    cmds = [('GRID', (0,0), (-1,-1), .45, colors.HexColor('#D9D9D9')),
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#dfe8ef')),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('LEFTPADDING', (0,0), (-1,-1), 7), ('RIGHTPADDING', (0,0), (-1,-1), 7),
            ('TOPPADDING', (0,0), (-1,-1), 6), ('BOTTOMPADDING', (0,0), (-1,-1), 6)]
    tab.setStyle(TableStyle(cmds))
    return tab

def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont('Arial', 8)
    canvas.setFillColor(colors.HexColor('#555555'))
    canvas.drawRightString(PAGE_W-MARGIN, 24, str(doc.page))
    canvas.restoreState()

def build():
    """Sinh PDF A4 và kiểm số trang thực tế; không suy từ pagebreak nguồn."""
    lines = (ROOT / 'ThanhNghe_TechnicalReport.md').read_text(encoding='utf-8').splitlines()
    story, buffer = [], []
    references = False
    def flush():
        if buffer:
            text = ' '.join(buffer)
            style = 'ref' if references else ('caption' if text.startswith('*') and not text.startswith('**') else 'body')
            if style == 'caption':
                text = text.strip('*')
            story.append(Paragraph(inline(text), STYLES[style]))
            buffer.clear()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            flush()
        elif line == '<!-- PAGEBREAK -->':
            flush(); story.append(PageBreak())
        elif line.startswith('#'):
            flush()
            level, text = line.split(' ',1)
            references = text == 'Tài liệu tham khảo'
            story.append(Paragraph(inline(text), STYLES[{'#':'title','##':'h1','###':'h2'}[level]]))
        elif line.startswith('!['):
            flush()
            story.append(Architecture())
        elif line.startswith('|'):
            flush(); block=[]
            while i < len(lines) and lines[i].strip().startswith('|'):
                block.append(lines[i].strip()); i += 1
            story.append(table(block)); story.append(Spacer(1,7)); continue
        elif re.match(r'^\d+\. ', line):
            flush(); story.append(Paragraph(inline(line), STYLES['body']))
        else:
            buffer.append(line)
        i += 1
    flush()
    destination = OUT/'ThanhNghe_TechnicalReport.pdf'
    doc = SimpleDocTemplate(str(destination), pagesize=A4, rightMargin=MARGIN, leftMargin=MARGIN,
                            topMargin=37, bottomMargin=37, title='Báo cáo kỹ thuật Vòng Sơ tuyển AI Challenge TP.HCM 2026', author='Đội Thanh Nghệ')
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    reader = PdfReader(destination)
    print(f'PDF: {destination}\nPAGES: {len(reader.pages)}\nBYTES: {destination.stat().st_size}')
    for number, page in enumerate(reader.pages,1):
        text = page.extract_text() or ''
        print(f'PAGE {number}: {len(text)} chars; HEAD {text[:110]!r}; TAIL {text[-110:]!r}')

if __name__ == '__main__':
    build()
