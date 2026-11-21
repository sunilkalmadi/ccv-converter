"""Read a CCV XML export and turn it into display-ready entries.

Both renderers (render_pdf.py and render_docx.py) consume the CV object built
here, so the text of every record, the numbering and the supervision lines are
decided in exactly one place.

    parse_xml(path)      -> raw nested dicts, as in the upstream converter
    build_cv(sections)   -> CV(name, sections=[Section(title, groups=[Group(title, entries)])])
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from itertools import count, groupby

import ccv_config as cfg


# --- Shared data structure -----------------------------------------------------

@dataclass
class Part:
    """A styled piece of a line (used by the 'reviewer' style)."""
    text: str
    role: str = ''           # '', 'self' (CV owner's name), 'venue', 'tag', 'muted', 'link'
    href: str | None = None  # for role 'link'


@dataclass
class Line:
    text: str
    indent: int = 0          # 0 = main line, 1 = indented sub-line
    bold: bool = False
    muted: bool = False      # secondary text (grey in the reviewer style)
    kind: str = ''           # '' = normal record line, 'year' = year divider, 'note' = legend/note
    parts: list[Part] | None = None   # styled pieces; their texts join to `text`


def styled(parts, **kw):
    """Line built from Part pieces; blank pieces are dropped."""
    parts = [p for p in parts if p is not None and p.text]
    return Line(''.join(p.text for p in parts), parts=parts, **kw)


@dataclass
class Entry:
    left: str | None         # date range or label (e.g. "J214"); None = no left column
    lines: list[Line]


@dataclass
class Group:
    title: str | None        # subgroup heading, e.g. "Doctorate [n=37]"
    entries: list[Entry]


@dataclass
class Section:
    title: str
    groups: list[Group] = field(default_factory=list)


@dataclass
class CV:
    name: str
    sections: list[Section]
    style: str = 'classic'                                 # picks the template/Word layout
    subtitle: list[Line] = field(default_factory=list)     # lines under the name (reviewer)
    footer: str = ''                                       # page footer text (reviewer)


# --- XML parsing (from the upstream xml2html_cv.py) ------------------------------

def parse_section(item):
    """Convert a CCV <section>/<field>/<refTable> element into dicts/strings."""
    match item.tag:
        case 'section':
            res = {}
            for child in item:
                if 'label' in child.attrib:
                    label = child.attrib['label']
                    if label in res:
                        if not isinstance(res[label], list):
                            res[label] = [res[label]]
                        res[label].append(parse_section(child))
                    else:
                        res[label] = parse_section(child)
            return res
        case 'field':
            if len(item):
                match item[0].tag:
                    case 'value' | 'lov':
                        return item[0].text
                    case 'refTable':
                        return parse_section(item[0])
            return None
        case 'refTable':
            return {child.attrib['label']: child.attrib.get('value')
                    for child in item if 'label' in child.attrib}


class NotCCVError(ValueError):
    """The XML is well formed but is not a CCV export."""


CCV_RECORD_SECTIONS = {'Student/Postdoctoral Supervision', 'Journal Articles', 'Degrees',
                       'Recognitions', 'Research Funding History', 'Employment'}


def parse_xml(path):
    """Return {section label: dict or list of dicts} for every section in the file."""
    root = ET.parse(path).getroot()
    all_sections = root.findall('.//section')
    if not any(s.get('label') in ('Personal Information', 'Contributions', 'Activities')
               or s.get('label') in CCV_RECORD_SECTIONS for s in all_sections):
        raise NotCCVError('This file does not look like a CCV XML export (no CCV sections found).')
    label_counts = {}
    for item in all_sections:
        label_counts[item.attrib['label']] = label_counts.get(item.attrib['label'], 0) + 1
    sections = {}
    for item in all_sections:
        label = item.attrib['label']
        if label_counts[label] > 1:
            sections.setdefault(label, []).append(parse_section(item))
        else:
            sections[label] = parse_section(item)
    sections['_generated'] = root.get('dateTimeGenerated') or ''   # export date, for footers
    return sections


# --- Small text helpers ----------------------------------------------------------

def as_list(value):
    """A CCV section can appear once (dict) or many times (list); always return a list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


# Typographic ligatures become plain letters; invisible zero-width characters are dropped
# (both come from copy-pasting into CCV and break search/copy in the outputs).
_CLEANUP = str.maketrans({'ﬀ': 'ff', 'ﬁ': 'fi', 'ﬂ': 'fl', 'ﬃ': 'ffi',
                          'ﬄ': 'ffl', '​': None, '‌': None, '‍': None,
                          '⁠': None, '﻿': None})


def text(value):
    """Plain text for a field value; refTables become 'a, b'; None becomes ''.

    Line breaks and repeated spaces inside a field collapse to one space, so PDF
    and DOCX show the same text. Punctuation-only placeholders become ''.
    """
    if value is None:
        return ''
    if isinstance(value, dict):
        return join(*value.values())
    if isinstance(value, list):
        return join(*value)
    value = ' '.join(str(value).translate(_CLEANUP).split())
    # A field holding only punctuation (e.g. '.' or '-') is a placeholder: treat it as blank.
    return value if any(ch.isalnum() for ch in value) else ''


def org(item, key='Organization', other_key='Other Organization'):
    """Organization name from a refTable, falling back to the free-text field."""
    value = item.get(key)
    if isinstance(value, dict):
        name = text(value.get('Organization')) or text(value)
    else:
        name = text(value)
    return name or text(item.get(other_key))


def join(*parts, sep=', '):
    """Join the non-blank parts."""
    return sep.join(t for t in (text(p) for p in parts) if t)


def date_range(start, end=None):
    start, end = text(start), text(end)
    if start and end:
        return f'{start} - {end}'
    return start or (f'- {end}' if end else '')


def sentence(*parts):
    """Join citation parts as 'A. B. C.' without doubling final punctuation."""
    out = []
    for part in parts:
        part = text(part)
        if part:
            out.append(part if part[-1] in '.?!' else part + '.')
    return ' '.join(out)


def year(value):
    """'(2024)' for citations, or '' when the year is blank."""
    return f'({text(value)})' if text(value) else ''


def year_month(value):
    """(year, month) from CCV dates such as '2019/4', '2019-04-01' or '2019'; None if no year."""
    m = re.search(r'(\d{4})(?:[/-](\d{1,2}))?', text(value))
    return (int(m.group(1)), int(m.group(2) or 0)) if m else None


def lines(*texts, indent=0):
    return [Line(t, indent) for t in (text(x) for x in texts) if t]


def _norm(label):
    return text(label).replace('’', "'").casefold()


# --- Section builders (one per CV section, same order as the upstream template) --

def _identification(pi):
    ident = pi.get('Identification') or {}
    name = join(ident.get('Title'), ident.get('First Name'), ident.get('Family Name'), sep=' ')
    entries = []
    for key, value in ident.items():
        if key in ('Title', 'First Name', 'Family Name') or not text(value):
            continue
        if key == 'Country of Citizenship':
            value = join(*(c.get('Country of Citizenship') if isinstance(c, dict) else c
                           for c in as_list(value)))
        entries.append(Entry(None, lines(f'{key}: {text(value)}')))
    return Section(name or 'Curriculum Vitae', [Group(None, entries)] if entries else [])


def _contact(pi):
    groups = []
    addresses = [Entry(text(a.get('Address Type')), lines(
        a.get('Address - Line 1'), a.get('Line 2'), a.get('Line 3'),
        join(a.get('City'), (a.get('Location') or {}).get('Subdivision'),
             a.get('Postal / Zip Code'), sep=' '),
        (a.get('Location') or {}).get('Country'))) for a in as_list(pi.get('Address'))]
    phones = [Entry(text(p.get('Phone Type')), lines(
        join(p.get('Country Code'), p.get('Area Code'), p.get('Telephone Number'), sep='-')))
        for p in as_list(pi.get('Telephone'))]
    emails = [Entry(text(e.get('Email Type')), lines(e.get('Email Address')))
              for e in as_list(pi.get('Email'))]
    sites = [Entry(text(w.get('Website Type')), lines(w.get('URL')))
             for w in as_list(pi.get('Website'))]
    for title, entries in (('Address', addresses), ('Telephone', phones),
                           ('Email', emails), ('Website', sites)):
        if entries:
            groups.append(Group(title, entries))
    return Section('Contact Information', groups)


def _degrees(s):
    entries = []
    for d in as_list((s.get('Education') or {}).get('Degrees')):
        sups = [join(x.get('Supervisor Name'), date_range(x.get('Start Date'), x.get('End Date')))
                for x in as_list(d.get('Supervisors'))]
        entries.append(Entry(
            date_range(d.get('Degree Start Date'), d.get('Degree Received Date')),
            lines(join(d.get('Degree Type'), d.get('Degree Name'), d.get('Specialization'),
                       org(d)),
                  f"Degree Status: {text(d.get('Degree Status'))}" if text(d.get('Degree Status')) else '',
                  f"Supervisors: {'; '.join(x for x in sups if x)}" if any(sups) else '')))
    return Section('Degrees', [Group(None, entries)])


def _recognitions(s):
    entries = [Entry(date_range(r.get('Effective Date'), r.get('End Date')),
                     lines(r.get('Recognition Name'), org(r), r.get('Recognition Type'),
                           r.get('Description')))
               for r in as_list(s.get('Recognitions'))]
    return Section('Recognitions', [Group(None, entries)])


def _employment(s):
    emp = s.get('Employment') or {}
    records = as_list(emp.get('Academic Work Experience')) + \
        as_list(emp.get('Non-academic Work Experience'))

    def end_key(x):
        end = text(x.get('End Date'))
        if not end:
            return (9999, 0)                        # no end date = current job, listed first
        return year_month(end) or (0, 0)            # unreadable dates go last
    records.sort(key=end_key, reverse=True)
    entries = []
    for e in records:
        if text(e.get('Position Title')) in cfg.EMPLOYMENT_HIDE_TITLES:
            continue
        entries.append(Entry(date_range(e.get('Start Date'), e.get('End Date')), lines(
            e.get('Position Title'),
            join(e.get('Department'), e.get('Faculty / School / Campus'), org(e)),
            join(e.get('Position Status'), e.get('Position Type'), e.get('Academic Rank')))))
    return Section('Employment', [Group(None, entries)])


def _money(value):
    try:
        return '{:,}'.format(int(float(text(value))))
    except (ValueError, OverflowError):
        return text(value)


def _funding(s):
    entries = []
    for f in as_list(s.get('Research Funding History')):
        body = lines(f.get('Funding Title'), f.get('Funding Role'))
        sources = as_list(f.get('Funding Sources'))
        if sources:
            body.append(Line('Funding Sources:', bold=True))
        for src in sources:
            total = text(src.get('Total Funding'))
            body += lines(join(date_range(src.get('Funding Start Date'), src.get('Funding End Date')),
                               src.get('Funding Organization'), src.get('Program Name'),
                               f'Total Funding - {_money(total)}' if total else ''), indent=1)
        status = text(f.get('Funding Status')) or 'Status not specified'
        entries.append((status, Entry(date_range(f.get('Funding Start Date'),
                                                 f.get('Funding End Date')), body)))
    return Section('Research Funding History', [
        Group(funding_status_title(status), [e for st, e in entries if st == status])
        for status in ordered_statuses(st for st, _ in entries)])


def ordered_statuses(statuses):
    """Funding statuses in the order of FUNDING_STATUS_ORDER, then any others as found."""
    found = list(dict.fromkeys(statuses))
    rank = {k: i for i, k in enumerate(cfg.FUNDING_STATUS_ORDER)}
    return sorted(found, key=lambda st: rank.get(st, len(rank)))


def funding_status_title(status):
    return cfg.FUNDING_STATUS_TITLES.get(status, status)


def _courses(s):
    years = {}
    for c in as_list(s.get('Courses Taught')):
        start = (year_month(c.get('Start Date')) or (None,))[0]
        end = (year_month(c.get('End Date')) or (start,))[0]
        span = set()
        if start and end:
            span = set(range(min(start, end), max(start, end) + 1))
        elif start or end:
            span = {start or end}
        years.setdefault(text(c.get('Course Title')), set()).update(span)  # undated: still listed
    entries = []
    for title, ys in years.items():
        runs = [list(g) for _, g in groupby(sorted(ys), key=lambda y, c=count(): y - next(c))]
        label = ', '.join(str(r[0]) if len(r) == 1 else f'{r[0]}-{r[-1]}' for r in runs)
        entries.append(Entry(label, lines(title)))
    return Section('Courses Taught', [Group(None, entries)])


def present_position(item):
    """'Present Position, Present Organization' (organization left out if the position names it)."""
    position = text(item.get(cfg.SUPERVISION_POSITION_FIELD))
    organization = text(item.get(cfg.SUPERVISION_ORG_FIELD))
    if isinstance(item.get(cfg.SUPERVISION_ORG_FIELD), dict):
        organization = org(item, cfg.SUPERVISION_ORG_FIELD, '')
    already_named = re.search(r'(?<!\w)' + re.escape(organization) + r'(?!\w)', position,
                              re.IGNORECASE) if organization else None
    if cfg.SUPERVISION_SHOW_ORGANIZATION and organization and not already_named:
        return join(position, organization)
    return position


def supervision_entry(item):
    """Date range + name, then thesis title and '>> present position' when nonblank."""
    present = present_position(item)
    body = lines(item.get('Student Name'))
    body += lines(item.get(cfg.SUPERVISION_TITLE_FIELD), indent=1)
    if present:
        body.append(Line(cfg.SUPERVISION_POSITION_MARKER + present, indent=1))
    return Entry(date_range(item.get('Supervision Start Date'), item.get('Supervision End Date')),
                 body)


def group_supervision(records):
    """[(heading label, records)] grouped by degree type, in the configured order."""
    groups, shown_as = {}, {}
    for item in records:
        label = text(item.get(cfg.SUPERVISION_GROUP_FIELD)) or cfg.SUPERVISION_GROUP_MISSING
        key = _norm(label)                    # "Master’s" and "Master's" are one group
        shown_as.setdefault(key, label)       # heading uses the first spelling seen
        groups.setdefault(key, []).append(item)
    rank = {_norm(k): i for i, k in enumerate(cfg.SUPERVISION_GROUP_ORDER)}
    ordered = sorted(groups, key=lambda k: rank.get(k, len(rank)))  # stable sort
    return [(shown_as[k], groups[k]) for k in ordered]


def supervision_groups(records):
    """Group supervision records by degree type; headings carry live counts."""
    return [Group(f'{label} [n={len(items)}]', [supervision_entry(i) for i in items])
            for label, items in group_supervision(records)]


def _simple(s, key, left_keys, line_fn, title=None):
    entries = [Entry(date_range(*(r.get(k) for k in left_keys)), line_fn(r))
               for r in as_list(s.get(key))]
    return Section(title or key, [Group(None, entries)])


def _reviewed(r):
    n = text(r.get('Number of Works Reviewed / Refereed'))
    return f'Number of Works Reviewed / Refereed: {n}' if n else ''


def _membership(r):
    return lines(join(r.get('Role'), r.get('Committee Name'), org(r)), r.get('Description'))


# --- Publications ----------------------------------------------------------------

def citation(category, p):
    """Bibliographic text for one publication (formats follow the upstream template)."""
    authors = p.get('Authors')
    match category:
        case 'Journal Articles':
            vol = text(p.get('Volume')) + (f"({text(p.get('Issue'))})" if text(p.get('Issue')) else '')
            pages = text(p.get('Page Range'))
            return sentence(authors, year(p.get('Year')), p.get('Article Title'),
                            p.get('Journal'), join(vol, pages, sep=': '), p.get('URL'))
        case 'Book Chapters':
            return sentence(authors, year(p.get('Year')), p.get('Chapter Title'),
                            p.get('Book Title'), p.get('Publishing Status'), p.get('Publisher'),
                            p.get('Publication Location'), p.get('URL'))
        case 'Encyclopedia Entries':
            return sentence(authors, year(p.get('Year')), p.get('Entry Title'),
                            p.get('Encyclopedia Name'), p.get('Page Range'), p.get('Publisher'),
                            p.get('Publication Location'), p.get('URL'))
        case 'Magazine Entries':
            vol = join(p.get('Volume'), f"({text(p.get('Issue'))})" if text(p.get('Issue')) else '',
                       p.get('Page Range'), sep=' ')
            return sentence(authors, year(p.get('Year')), p.get('Article Title'),
                            p.get('Magazine Name'), vol, p.get('Publisher'),
                            p.get('Publication Location'), p.get('URL'))
        case 'Reports':
            return sentence(authors, year(p.get('Year Submitted')), p.get('Report Title'),
                            org(p))
        case 'Conference Publications':
            pages = text(p.get('Page Range'))
            place = join(p.get('City'), p.get('Location'))
            return sentence(authors, year(p.get('Year')), p.get('Publication Title'),
                            p.get('Published In'), p.get('Conference Name'),
                            join(place, f'({pages})' if pages else '', sep=' '), p.get('URL'))
    return sentence(authors, p.get('Year'))


def publication_labels(category, n):
    """Labels for n entries kept in display order: J214, J213, ... J1 (or 1., 2., ...)."""
    prefix = cfg.PUBLICATION_PREFIXES.get(category)
    if prefix:
        return [f'{prefix}{n - i}' for i in range(n)]
    return [f'{i + 1}.' for i in range(n)]


def _publications(s):
    pubs = s.get('Publications') or {}
    groups = []
    for category in cfg.PUBLICATION_ORDER:
        items = as_list(pubs.get(category))
        labels = publication_labels(category, len(items))
        groups.append(Group(category, [Entry(label, lines(citation(category, p)))
                                       for label, p in zip(labels, items)]))
    return Section('Publications', groups)


def _presentations(s):
    items = as_list(s.get('Presentations'))
    entries = []
    for label, p in zip(publication_labels('Presentations', len(items)), items):
        year = text(p.get('Presentation Year'))
        entries.append(Entry(label, lines(join(
            join(f'({year}).' if year else '', p.get('Presentation Title'), sep=' '),
            p.get('Conference / Event Name'), p.get('City'), p.get('Location')))))
    return Section('Presentations', [Group(None, entries)])


# --- Whole CV ----------------------------------------------------------------------

def build_cv(s):
    """Build the shared CV structure from parse_xml() output. Empty sections are dropped."""
    pi = s.get('Personal Information') or {}
    sections = [
        _identification(pi),
        _contact(pi),
        _degrees(s),
        _recognitions(s),
        _employment(s),
        _funding(s),
        _courses(s),
        Section('Student/Postdoctoral Supervision',
                supervision_groups(as_list(s.get('Student/Postdoctoral Supervision')))),
        _simple(s, 'Editorial Activities', ('Start Date', 'End Date'), lambda r: lines(
            join(r.get('Role'), r.get('Publication Name'), r.get('Publication Type')),
            r.get('Activity Description'))),
        _simple(s, 'Journal Review Activities', ('Start Date', 'End Date'), lambda r: lines(
            join(r.get('Role'), r.get('Journal')), _reviewed(r))),
        _simple(s, 'Conference Review Activities', ('Start Date', 'End Date'), lambda r: lines(
            join(r.get('Role'), r.get('Conference'), r.get('Review Type')), _reviewed(r))),
        _simple(s, 'Research Funding Application Assessment Activities', ('Start Date', 'End Date'),
                lambda r: lines(join(r.get('Funding Reviewer Role'), r.get('Committee Name'),
                                     r.get('Reviewer Type'), org(r)),
                                f"Number of Applications Assessed: {text(r.get('Number of Applications Assessed'))}"
                                if text(r.get('Number of Applications Assessed')) else '')),
        _simple(s, 'Community and Volunteer Activities', ('Start Date', 'End Date'), lambda r: lines(
            join(r.get('Role'), org(r)), r.get('Activity Description'))),
        _simple(s, 'Committee Memberships', ('Membership Start Date', 'Membership End Date'),
                _membership),
        _simple(s, 'Other Memberships', ('Membership Start Date', 'Membership End Date'),
                _membership),
        _presentations(s),
        _simple(s, 'Broadcast Interviews', ('First Broadcast Date',), lambda r: lines(
            join(r.get('Topic'), r.get('Program')), r.get('Network'))),
        _simple(s, 'Text Interviews', ('Publication Date',), lambda r: lines(
            join(r.get('Topic'), r.get('Forum')), r.get('URL'))),
        _publications(s),
    ]
    for sec in sections:
        sec.groups = [g for g in sec.groups if g.entries]
    name = sections[0].title
    return CV(name, [sec for sec in sections if sec.groups or sec is sections[0]])


def load_cv(path):
    return build_cv(parse_xml(path))


def summary(cv):
    """Counts and first/last labels only (no names), for private acceptance checks."""
    out = []
    for sec in cv.sections:
        if sec.title in ('Student/Postdoctoral Supervision', 'Publications'):
            total = sum(len(g.entries) for g in sec.groups)
            out.append(f'{sec.title}: {total} records')
            for g in sec.groups:
                line = f'  {g.title}: {len(g.entries)}'
                if sec.title == 'Publications':
                    line += f'  first={g.entries[0].left} last={g.entries[-1].left}'
                else:
                    with_title = sum(1 for e in g.entries
                                     if any(l.indent and not l.text.startswith(
                                         cfg.SUPERVISION_POSITION_MARKER) for l in e.lines))
                    with_pos = sum(1 for e in g.entries if any(
                        l.text.startswith(cfg.SUPERVISION_POSITION_MARKER) for l in e.lines))
                    line += f'  (with title: {with_title}, with present position: {with_pos})'
                out.append(line)
    return '\n'.join(out)
