"""DOCX output: CV data -> editable Word document (python-docx).

Every record is ordinary paragraphs: "label<TAB>text" with a hanging indent, and
indented sub-lines below it. Nothing is placed in text boxes or at fixed page
positions, so editing one record only reflows the text after it.
Page size, fonts and spacing for Word are set in the constants below.
"""

import re

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_LINE_SPACING, WD_TAB_ALIGNMENT
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from ccv_data import Line

FONT = 'Arial'
FONT_SIZE = Pt(8)
HEADING_1 = dict(size=Pt(14), color=RGBColor(0x00, 0x8B, 0x8B))   # darkcyan, as in the PDF
HEADING_2 = dict(size=Pt(9.5), color=RGBColor(0x00, 0x00, 0x00))
MARGIN = Inches(0.5)
SUB_INDENT = Inches(0.2)          # extra indent for sub-lines (thesis title, >> position)
ENTRY_SPACE_AFTER = Pt(3)


def _setup_styles(doc):
    normal = doc.styles['Normal']
    normal.font.name = FONT
    normal.font.size = FONT_SIZE
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(0)
    for name, spec, before in (('Heading 1', HEADING_1, Pt(10)), ('Heading 2', HEADING_2, Pt(6))):
        style = doc.styles[name]
        style.font.name = FONT
        rfonts = style.element.rPr.rFonts
        for attr in ('w:asciiTheme', 'w:hAnsiTheme', 'w:eastAsiaTheme', 'w:cstheme'):
            rfonts.attrib.pop(qn(attr), None)     # theme fonts would override FONT
        style.font.size = spec['size']
        style.font.color.rgb = spec['color']
        style.font.bold = True
        style.paragraph_format.space_before = before
        style.paragraph_format.space_after = Pt(3)
    for sec in doc.sections:
        sec.page_width, sec.page_height = Inches(8.5), Inches(11)
        sec.left_margin = sec.right_margin = sec.top_margin = sec.bottom_margin = MARGIN


def _label_width(entries):
    """Width of the label column, sized to the longest date range/label in the group."""
    longest = max((len(e.left or '') for e in entries), default=0)
    return Inches(min(1.6, max(0.4, 0.065 * longest + 0.15)))


def _add_entry(doc, entry, width):
    rows = entry.lines
    if entry.left is not None and (not rows or rows[0].indent):
        rows = [Line('')] + rows          # the label always gets its own first line
    for i, line in enumerate(rows):
        p = doc.add_paragraph()
        fmt = p.paragraph_format
        fmt.keep_together = True
        fmt.keep_with_next = i < len(rows) - 1             # keep a record on one page
        if i == len(rows) - 1:
            fmt.space_after = ENTRY_SPACE_AFTER
        if entry.left is None:
            fmt.left_indent = SUB_INDENT * line.indent
        elif i == 0:
            fmt.left_indent = width
            fmt.first_line_indent = -width
            fmt.tab_stops.add_tab_stop(width, WD_TAB_ALIGNMENT.LEFT)
            p.add_run(f'{entry.left}\t')
        else:
            fmt.left_indent = width + SUB_INDENT * line.indent
        p.add_run(line.text).bold = line.bold or None


# --- 'Reviewer' style ------------------------------------------------------------------
# Same structure, but with named Word styles so a user can restyle every record at once
# (Home > Styles): "CV Record", "CV Continued", "CV Subline", "CV Year", "CV Note",
# and character styles "CV Self", "CV Venue", "CV Muted", "CV Tag", "CV Link".

R_FONT_SIZE = Pt(8.5)
R_LINE = Pt(10.5)                         # exact line spacing
R_ACCENT = RGBColor(0x00, 0x70, 0x7A)
R_MUTED = RGBColor(0x66, 0x66, 0x66)
R_TEXT = RGBColor(0x1A, 0x1A, 0x1A)
R_LABEL = Inches(0.97)                    # date/label column (0.85in) + gap
R_LABEL_RIGHT = Inches(0.82)              # right edge for J214-style labels
R_SUB = Inches(0.14)                      # extra indent for sub-lines
R_SIDE, R_TOPBOTTOM = Inches(0.6), Inches(0.7)


def _plain_font(style, size=None, color=None, bold=None, italic=None):
    style.font.name = FONT
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn('w:rFonts'))
    if rfonts is not None:
        for attr in ('w:asciiTheme', 'w:hAnsiTheme', 'w:eastAsiaTheme', 'w:cstheme'):
            rfonts.attrib.pop(qn(attr), None)
    if size:
        style.font.size = size
    if color is not None:
        style.font.color.rgb = color
    if bold is not None:
        style.font.bold = bold
    if italic is not None:
        style.font.italic = italic


_AFTER_PBDR = ('w:shd', 'w:tabs', 'w:suppressAutoHyphens', 'w:kinsoku', 'w:wordWrap',
               'w:overflowPunct', 'w:topLinePunct', 'w:autoSpaceDE', 'w:autoSpaceDN', 'w:bidi',
               'w:adjustRightInd', 'w:snapToGrid', 'w:spacing', 'w:ind', 'w:contextualSpacing',
               'w:mirrorIndents', 'w:suppressOverlap', 'w:jc', 'w:textDirection',
               'w:textAlignment', 'w:textboxTightWrap', 'w:outlineLvl', 'w:divId', 'w:cnfStyle',
               'w:rPr', 'w:sectPr', 'w:pPrChange')


def _border(element, side='bottom', size=4, color='00707A', space=1):
    """Thin line under a paragraph or paragraph style (Word measures size in 1/8 pt)."""
    ppr = element.get_or_add_pPr()
    bdr = ppr.find(qn('w:pBdr'))
    if bdr is None:
        bdr = OxmlElement('w:pBdr')
        ppr.insert_element_before(bdr, *_AFTER_PBDR)      # Word requires this element order
    edge = OxmlElement(f'w:{side}')
    for k, v in (('w:val', 'single'), ('w:sz', str(size)), ('w:space', str(space)),
                 ('w:color', color)):
        edge.set(qn(k), v)
    bdr.append(edge)


def _reviewer_styles(doc):
    styles = doc.styles
    normal = styles['Normal']
    _plain_font(normal, R_FONT_SIZE, R_TEXT)
    pf = normal.paragraph_format
    pf.space_before = pf.space_after = Pt(0)
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pf.line_spacing = R_LINE
    pf.widow_control = True
    h1 = styles['Heading 1']
    _plain_font(h1, Pt(12), R_ACCENT, bold=True)
    h1.paragraph_format.space_before, h1.paragraph_format.space_after = Pt(10), Pt(3)
    h1.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    _border(h1.element)
    h2 = styles['Heading 2']
    _plain_font(h2, Pt(9), R_TEXT, bold=True)
    h2.paragraph_format.space_before, h2.paragraph_format.space_after = Pt(6), Pt(2)
    h2.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE

    def para(name, left=None, first=None, before=None, keep_next=False, **font):
        st = styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
        st.base_style = normal
        st.quick_style = True
        if font:
            _plain_font(st, **font)
        f = st.paragraph_format
        if left is not None:
            f.left_indent = left
        if first is not None:
            f.first_line_indent = first
        if before is not None:
            f.space_before = before
        f.keep_together = True
        f.keep_with_next = keep_next
        return st

    para('CV Name', size=Pt(18), bold=True).paragraph_format.line_spacing_rule = \
        WD_LINE_SPACING.SINGLE
    para('CV Subtitle')
    rec = para('CV Record', left=R_LABEL, first=-R_LABEL)
    rec.paragraph_format.tab_stops.add_tab_stop(R_LABEL, WD_TAB_ALIGNMENT.LEFT)
    para('CV Continued', left=R_LABEL)
    para('CV Subline', left=R_LABEL + R_SUB)
    para('CV Year', before=Pt(4), keep_next=True, size=Pt(8), color=R_MUTED, bold=True)
    para('CV Note', size=Pt(8), color=R_MUTED, italic=True).paragraph_format.space_after = Pt(4)

    def char(name, **font):
        st = styles.add_style(name, WD_STYLE_TYPE.CHARACTER)
        for k, v in font.items():
            if k == 'color':
                st.font.color.rgb = v
            else:
                setattr(st.font, k, v)
        return st

    char('CV Self', bold=True)
    char('CV Venue', italic=True)
    char('CV Muted', color=R_MUTED)
    char('CV Tag', color=R_MUTED, size=Pt(7.5))
    char('CV Link', color=R_ACCENT)
    char('CV Label', color=R_MUTED)
    for sec in doc.sections:
        sec.page_width, sec.page_height = Inches(8.5), Inches(11)
        sec.left_margin = sec.right_margin = R_SIDE
        sec.top_margin = sec.bottom_margin = R_TOPBOTTOM


ROLE_STYLES = {'self': 'CV Self', 'em': 'CV Venue', 'muted': 'CV Muted', 'tag': 'CV Tag'}


def _hyperlink(paragraph, text, url):
    """Clickable link run (python-docx has no direct API for this)."""
    r_id = paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True)
    link = OxmlElement('w:hyperlink')
    link.set(qn('r:id'), r_id)
    run = OxmlElement('w:r')
    rpr = OxmlElement('w:rPr')
    rstyle = OxmlElement('w:rStyle')
    rstyle.set(qn('w:val'), paragraph.part.document.styles['CV Link'].style_id)
    rpr.append(rstyle)
    run.append(rpr)
    t = OxmlElement('w:t')
    t.text = text
    t.set(qn('xml:space'), 'preserve')
    run.append(t)
    link.append(run)
    paragraph._p.append(link)


def _add_runs(p, line):
    if line.parts:
        for part in line.parts:
            if part.role == 'link' and part.href:
                _hyperlink(p, part.text, part.href)
            else:
                run = p.add_run(part.text)
                if part.role in ROLE_STYLES:
                    run.style = ROLE_STYLES[part.role]
                if line.muted and not part.role:
                    run.style = 'CV Muted'
    else:
        run = p.add_run(line.text)
        if line.muted:
            run.style = 'CV Muted'
        if line.bold:
            run.bold = True


def _reviewer_entry(doc, entry):
    if entry.left is None:
        for line in entry.lines:
            style = {'year': 'CV Year', 'note': 'CV Note'}.get(line.kind, 'CV Subtitle')
            p = doc.add_paragraph(style=style)
            if line.kind == 'year':
                p.add_run(line.text)
            else:
                _add_runs(p, line)
        return
    rows = entry.lines
    if not rows or rows[0].indent:
        rows = [Line('')] + rows          # the label always gets its own first line
    for i, line in enumerate(rows):
        style = 'CV Record' if i == 0 else ('CV Subline' if line.indent else 'CV Continued')
        p = doc.add_paragraph(style=style)
        p.paragraph_format.keep_with_next = i < len(rows) - 1      # keep a record together
        if i == len(rows) - 1:
            p.paragraph_format.space_after = Pt(2.5)
        if i == 0:
            if re.fullmatch(r'[A-Z]{1,2}\d+', entry.left or ''):   # J214: right-aligned number
                p.paragraph_format.tab_stops.add_tab_stop(R_LABEL_RIGHT, WD_TAB_ALIGNMENT.RIGHT)
                p.add_run('\t')
            p.add_run(entry.left).style = 'CV Label'
            p.add_run('\t')
        _add_runs(p, line)


def _field(run_parent, instr, style_id):
    fld = OxmlElement('w:fldSimple')
    fld.set(qn('w:instr'), instr)
    r = OxmlElement('w:r')
    rpr = OxmlElement('w:rPr')
    rstyle = OxmlElement('w:rStyle')
    rstyle.set(qn('w:val'), style_id)
    rpr.append(rstyle)
    r.append(rpr)
    t = OxmlElement('w:t')
    t.text = '1'
    r.append(t)
    fld.append(r)
    run_parent._p.append(fld)


def _reviewer_footer(doc, text):
    for sec in doc.sections:
        p = sec.footer.paragraphs[0]
        p.style = doc.styles['CV Subtitle']
        width = sec.page_width - sec.left_margin - sec.right_margin
        p.paragraph_format.tab_stops.add_tab_stop(width, WD_TAB_ALIGNMENT.RIGHT)
        p.add_run(text + '\tPage ').style = 'CV Tag'
        _field(p, 'PAGE', doc.styles['CV Tag'].style_id)
        p.add_run(' of ').style = 'CV Tag'
        _field(p, 'NUMPAGES', doc.styles['CV Tag'].style_id)


def _write_reviewer(doc, cv):
    _reviewer_styles(doc)
    doc.add_paragraph(cv.name, style='CV Name')
    for i, line in enumerate(cv.subtitle):
        p = doc.add_paragraph(style='CV Subtitle')
        _add_runs(p, line)
        if i == len(cv.subtitle) - 1:
            p.paragraph_format.space_after = Pt(6)
            _border(p._p, color='B9C6C8', size=6, space=4)
    for section in cv.sections:
        doc.add_heading(section.title, level=1)
        for group in section.groups:
            if group.title:
                doc.add_heading(group.title, level=2)
            for entry in group.entries:
                _reviewer_entry(doc, entry)
    _reviewer_footer(doc, cv.footer)


def write_docx(cv, out_path):
    doc = Document()
    doc.core_properties.title = cv.name
    doc.core_properties.author = ''
    if cv.style == 'reviewer':
        _write_reviewer(doc, cv)
        doc.save(str(out_path))
        return
    _setup_styles(doc)
    for section in cv.sections:
        doc.add_heading(section.title, level=1)
        width = _label_width([e for g in section.groups for e in g.entries])  # aligned per section
        for group in section.groups:
            if group.title:
                doc.add_heading(group.title, level=2)
            for entry in group.entries:
                _add_entry(doc, entry, width)
    doc.save(str(out_path))
