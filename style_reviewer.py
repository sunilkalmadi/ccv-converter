"""'Reviewer' style: the same CCV data, organized for grant panels and hiring/T&P committees.

    python xml2html_cv.py --input MyCCV.xml --style reviewer

Builds the same CV structure as ccv_data.build_cv (so both renderers work unchanged),
but with: a title block, a profile with counts, research-first section order,
funding by status and role, emphasized publications (owner's name bold, venue italic,
status tags, year dividers, DOIs), training outcomes, and sections the classic style
leaves out (graduate examinations, event administration, mentoring, ...).
Every record shown in the classic style also appears here. Settings: ccv_config.py.
"""

import re
from collections import Counter, OrderedDict
from itertools import count, groupby

import ccv_config as cfg
from ccv_data import (CV, Entry, Group, Line, Part, Section, _identification, _money,
                      as_list, funding_status_title, group_supervision, join, lines, org,
                      ordered_statuses, present_position, publication_labels, styled, text,
                      year_month)

DASH = '–'
DOT = ' · '


# --- Small helpers ------------------------------------------------------------------

def years(start, end=None, ongoing=False):
    """'2019–2024', '2019', '2005–present' from CCV dates."""
    s, e = year_month(start), year_month(end)
    sy, ey = (s[0] if s else None), (e[0] if e else None)
    if ongoing and not ey:
        return f'{sy}{DASH}present' if sy else 'present'
    if sy and ey:
        return str(sy) if sy == ey else f'{sy}{DASH}{ey}'
    return str(sy or ey or '')


def year_runs(ys):
    """{2010, 2011, 2012, 2015} -> '2010–2012, 2015'."""
    runs = [list(g) for _, g in groupby(sorted(ys), key=lambda y, c=count(): y - next(c))]
    return ', '.join(str(r[0]) if len(r) == 1 else f'{r[0]}{DASH}{r[-1]}' for r in runs)


def muted(*texts, indent=1):
    return [Line(t, indent=indent, muted=True) for t in (text(x) for x in texts) if t]


def link_part(item):
    """Short clickable DOI or web link, or None."""
    doi = text(item.get('DOI'))
    if doi:
        doi = re.sub(r'^(https?://(dx\.)?doi\.org/|doi:\s*)', '', doi, flags=re.I)
        return Part('doi:' + doi, 'link', 'https://doi.org/' + doi)
    url = text(item.get('URL')).split(' ')[0]
    if url:
        href = url if re.match(r'^https?://', url, re.I) else 'https://' + url
        shown = re.sub(r'^https?://(www\.)?', '', url, flags=re.I).rstrip('/')
        return Part(shown if len(shown) <= 45 else shown[:44] + '…', 'link', href)
    return None


def owner_pattern(sections):
    """Regex for the CV owner's name in author lists ('Russ Greiner', 'R. Greiner', 'Greiner R')."""
    ident = (sections.get('Personal Information') or {}).get('Identification') or {}
    first, family = text(ident.get('First Name')), text(ident.get('Family Name'))
    pats = list(cfg.REVIEWER_EXTRA_NAME_PATTERNS)
    if family:
        fam = re.escape(family)
        given = (rf'(?:{re.escape(first[:4])}\w*|{re.escape(first[:1])}\.?)' if first
                 else r'[A-Z]\.?')
        pats.append(rf'(?:\b{given}(?:\s+[A-Z]\.?)?\s+)?\b{fam}\b(?:,?\s+{given}(?![a-z]))?')
    return re.compile('|'.join(f'(?:{p})' for p in pats)) if pats else None


def author_parts(authors, pattern):
    a, out, pos = text(authors), [], 0
    if pattern:
        for m in pattern.finditer(a):
            out += [Part(a[pos:m.start()]), Part(m.group(0), 'self')]
            pos = m.end()
    out.append(Part(a[pos:]))
    return [p for p in out if p.text]


def sentence_parts(*segments):
    """Like ccv_data.sentence but for styled pieces: 'A. B. C.' without doubled punctuation."""
    out = []
    for seg in segments:
        pieces = [p for p in (seg if isinstance(seg, list) else [seg])
                  if p is not None and p.text.strip()]
        if not pieces:
            continue
        if out:
            out.append(Part(' '))
        out += pieces
        if pieces[-1].text.rstrip()[-1] not in '.?!':
            out.append(Part('.'))
    return out


def P(value, role=''):
    return Part(text(value), role)


def with_years(group_title, entries, ys, dividers):
    """Insert a small year divider before the first entry of each year."""
    if not dividers:
        return Group(group_title, entries)
    out, last = [], None
    for entry, y in zip(entries, ys):
        if y and y != last:
            out.append(Entry(None, [Line(y, kind='year')]))
            last = y
        out.append(entry)
    return Group(group_title, out)


# --- Title block and profile --------------------------------------------------------

def _current_positions(s):
    emp = s.get('Employment') or {}
    jobs = [e for e in as_list(emp.get('Academic Work Experience')) +
            as_list(emp.get('Non-academic Work Experience'))
            if not text(e.get('End Date')) and text(e.get('Position Title'))
            not in cfg.EMPLOYMENT_HIDE_TITLES]
    jobs.sort(key=lambda e: year_month(e.get('Start Date')) or (0, 0), reverse=True)
    return [join(e.get('Position Title'), e.get('Department'), org(e)) for e in jobs]


def _title_block(s, pi):
    out = [Line(t) for t in _current_positions(s)]
    emails = [text(e.get('Email Address')) for e in as_list(pi.get('Email'))]
    phones = [join(p.get('Country Code'), p.get('Area Code'), p.get('Telephone Number'), sep='-')
              for p in as_list(pi.get('Telephone'))]
    sites = [text(w.get('URL')) for w in as_list(pi.get('Website'))]
    contact = DOT.join(x for x in emails + phones + sites if x)
    if contact:
        out.append(Line(contact, muted=True))
    addresses = as_list(pi.get('Address'))
    primary = next((a for a in addresses if 'primary' in text(a.get('Address Type')).lower()),
                   addresses[0] if addresses else None)
    if primary:
        loc = primary.get('Location') or {}
        out.append(Line(join(primary.get('Address - Line 1'), primary.get('Line 2'),
                             primary.get('Line 3'), join(primary.get('City'), loc.get('Subdivision'),
                                                         primary.get('Postal / Zip Code'), sep=' '),
                             loc.get('Country')), muted=True))
    ident = _identification(pi)                        # all identification fields, kept by choice
    details = DOT.join(l.text for g in ident.groups for e in g.entries for l in e.lines)
    if details:
        out.append(Line(details, muted=True))
    return out


def _profile(s):
    entries = []
    profile = s.get('User Profile') or {}
    interests = '; '.join(x.strip() for x in str(profile.get('Research Interests') or '').splitlines()
                          if x.strip())
    if interests:
        entries.append(Entry('Interests', lines(interests)))
    keywords = [text(k.get('Research Specialization Keywords')) for k in
                as_list(s.get('Research Specialization Keywords'))]
    if any(keywords):
        entries.append(Entry('Keywords', lines('; '.join(k for k in keywords if k))))

    pubs = s.get('Publications') or {}
    def n_ref(cat):
        items = as_list(pubs.get(cat))
        return len(items), sum(text(p.get('Refereed?')) == 'Yes' for p in items)
    pub_bits = []
    for cat, word in (('Journal Articles', 'journal articles'),
                      ('Conference Publications', 'conference papers')):
        n, r = n_ref(cat)
        if n:
            pub_bits.append(f'{n} {word} ({r} refereed)')
    for cat, word in (('Book Chapters', 'book chapters'), ('Magazine Entries', 'magazine articles'),
                      ('Reports', 'reports'), ('Encyclopedia Entries', 'encyclopedia entries')):
        if as_list(pubs.get(cat)):
            pub_bits.append(f'{len(as_list(pubs.get(cat)))} {word}')
    if pub_bits:
        entries.append(Entry('Publications', lines(DOT.join(pub_bits))))

    grants = as_list(s.get('Research Funding History'))
    if grants:
        pi = sum(text(g.get('Funding Role')) in cfg.REVIEWER_PI_ROLES for g in grants)
        active = sum(text(g.get('Funding Status')) == 'Awarded' for g in grants)
        entries.append(Entry('Funding', lines(
            f'{len(grants)} grants and awards{DOT}{pi} as principal investigator/applicant{DOT}'
            f'{len(grants) - pi} as co-investigator, co-applicant or collaborator{DOT}{active} active')))

    trainees = as_list(s.get('Student/Postdoctoral Supervision'))
    if trainees:
        levels = DOT.join(f'{len(items)} {label}' for label, items in group_supervision(trainees))
        ongoing = sum(text(t.get('Student Degree Status')) == 'In Progress' for t in trainees)
        entries.append(Entry('Training', lines(f'{len(trainees)} trainees ({ongoing} in progress)'
                                               f': {levels}')))

    talks = as_list(s.get('Presentations'))
    if talks:
        keynotes = sum(text(t.get('Keynote?')) == 'Yes' for t in talks)
        entries.append(Entry('Presentations', lines(f'{len(talks)} presentations, including '
                                                    f'{keynotes} keynote addresses')))
    return Section('Profile', [Group(None, entries)])


# --- Career -------------------------------------------------------------------------

def _degrees(s):
    entries = []
    for d in as_list((s.get('Education') or {}).get('Degrees')):
        status = text(d.get('Degree Status'))
        sups = [text(x.get('Supervisor Name')) for x in as_list(d.get('Supervisors'))]
        entries.append(Entry(years(d.get('Degree Start Date'), d.get('Degree Received Date')),
                             lines(join(d.get('Degree Type'), d.get('Degree Name'),
                                        d.get('Specialization'), org(d)))
                             + muted(f'Status: {status}' if status and status != 'Completed' else '',
                                     'Supervisor: ' + '; '.join(x for x in sups if x)
                                     if any(sups) else '')))
    return Section('Degrees', [Group(None, entries)])


def _employment(s):
    emp = s.get('Employment') or {}
    records = as_list(emp.get('Academic Work Experience')) + \
        as_list(emp.get('Non-academic Work Experience'))
    records.sort(key=lambda e: (9999, 0) if not text(e.get('End Date'))
                 else (year_month(e.get('End Date')) or (0, 0)), reverse=True)
    entries = []
    for e in records:
        if text(e.get('Position Title')) in cfg.EMPLOYMENT_HIDE_TITLES:
            continue
        rank = text(e.get('Academic Rank'))
        title = text(e.get('Position Title'))
        entries.append(Entry(
            years(e.get('Start Date'), e.get('End Date'), ongoing=not text(e.get('End Date'))),
            [styled([Part(title), Part(f' ({rank})' if rank and rank != title else '', 'muted')])]
            + muted(join(e.get('Department'), e.get('Faculty / School / Campus'), org(e)),
                    join(e.get('Position Status'), e.get('Position Type')))))
    return Section('Employment', [Group(None, entries)])


def _recognitions(s):
    entries = []
    for r in as_list(s.get('Recognitions')):
        where = org(r)
        entries.append(Entry(years(r.get('Effective Date'), r.get('End Date')),
                             [styled([P(r.get('Recognition Name')),
                                      Part(f'{DOT}{where}' if where else '', 'muted')])]
                             + muted(r.get('Description'))))
    return Section('Awards and Recognitions', [Group(None, entries)])


# --- Funding ------------------------------------------------------------------------

CURRENCY = {'Canadian dollar': 'CAD', 'US dollar': 'USD', 'Euro': 'EUR', 'British pound': 'GBP'}


def _amount(src):
    total = text(src.get('Total Funding'))
    if not total:
        return '', None, 0
    cur = CURRENCY.get(text(src.get('Currency of Total Funding')),
                       text(src.get('Currency of Total Funding')))
    try:
        value = float(total)
    except ValueError:
        value = 0
    return join(cur, _money(total), sep=' '), cur, value


def _funding(s):
    records = as_list(s.get('Research Funding History'))
    groups = []
    for status in ordered_statuses(text(f.get('Funding Status')) or 'Status not specified'
                                   for f in records):
        in_status = [f for f in records
                     if (text(f.get('Funding Status')) or 'Status not specified') == status]
        for principal in (True, False):
            chosen = [f for f in in_status
                      if (text(f.get('Funding Role')) in cfg.REVIEWER_PI_ROLES) == principal]
            if not chosen:
                continue
            totals, entries = Counter(), []
            for f in chosen:
                body = [Line(text(f.get('Funding Title')))]
                role = text(f.get('Funding Role'))
                for i, src in enumerate(as_list(f.get('Funding Sources'))):
                    amount, cur, value = _amount(src)
                    totals[cur or ''] += value
                    body += muted(join(role if i == 0 and not principal else '',
                                       org(src, 'Funding Organization', 'Other Funding Organization'),
                                       src.get('Program Name'), amount, sep=DOT))
                if len(body) == 1 and not principal and role:
                    body += muted(role)
                entries.append(Entry(years(f.get('Funding Start Date'), f.get('Funding End Date')),
                                     body))
            who = 'as principal investigator' if principal else \
                'as co-investigator, co-applicant or collaborator'
            money = '; '.join(join(cur, f'{v:,.0f}', sep=' ') for cur, v in totals.items() if v)
            title = f'{funding_status_title(status)}, {who} [n={len(chosen)}]'
            if money:
                title += f'{DOT}total award value {money}'
            groups.append(Group(title, entries))
    return Section('Research Funding', groups)


# --- Publications and presentations --------------------------------------------------

def _citation(category, p, pattern):
    authors = author_parts(p.get('Authors'), pattern)
    year = text(p.get('Year') or p.get('Year Submitted'))
    yr = Part(f'({year})') if year else None
    match category:
        case 'Journal Articles':
            vol = text(p.get('Volume')) + (f"({text(p.get('Issue'))})" if text(p.get('Issue')) else '')
            body = [P(p.get('Article Title')), P(p.get('Journal'), 'em'),
                    P(join(vol, p.get('Page Range'), sep=': '))]
        case 'Conference Publications':
            body = [P(p.get('Publication Title')), P(p.get('Conference Name'), 'em'),
                    P(p.get('Published In')),
                    P(join(join(p.get('City'), p.get('Conference Location')),
                           f"({text(p.get('Page Range'))})" if text(p.get('Page Range')) else '',
                           sep=' '))]
        case 'Book Chapters':
            body = [P(p.get('Chapter Title')), [Part('In '), P(p.get('Book Title'), 'em')]
                    if text(p.get('Book Title')) else None, P(p.get('Publisher'))]
        case 'Magazine Entries':
            body = [P(p.get('Article Title')), P(p.get('Magazine Name'), 'em'),
                    P(join(p.get('Volume'), p.get('Page Range'), sep=': '))]
        case 'Encyclopedia Entries':
            body = [P(p.get('Entry Title')), P(p.get('Encyclopedia Name'), 'em'),
                    P(p.get('Page Range')), P(p.get('Publisher'))]
        case _:  # Reports
            body = [P(p.get('Report Title')), P(org(p), 'em')]
    parts = sentence_parts(authors, yr, *body)
    status = text(p.get('Publishing Status'))
    if status in cfg.REVIEWER_STATUS_TAGS:
        parts += [Part(' '), Part(f'[{status}]', 'tag')]
    link = link_part(p)
    if link:
        parts += [Part(' '), link]
    return styled(parts)


def _publications(s, pattern):
    pubs = s.get('Publications') or {}
    groups = [Group(None, [Entry(None, [Line(cfg.REVIEWER_PUBLICATION_LEGEND, kind='note',
                                             muted=True)])])]
    names = {'Journal Articles': 'Journal articles', 'Conference Publications': 'Conference papers',
             'Book Chapters': 'Book chapters', 'Magazine Entries': 'Magazine articles',
             'Reports': 'Reports', 'Encyclopedia Entries': 'Encyclopedia entries'}
    order = ['Journal Articles', 'Conference Publications', 'Book Chapters',
             'Magazine Entries', 'Reports', 'Encyclopedia Entries']
    order += [c for c in cfg.PUBLICATION_ORDER if c not in order]
    for cat in order:
        items = as_list(pubs.get(cat))
        labelled = list(zip(publication_labels(cat, len(items)), items))   # same numbers as classic
        flag = lambda p: text(p.get('Refereed?'))           # 'Yes', 'No' or '' (not recorded)
        flags = {flag(p) for _, p in labelled}
        chunks = [([(l, p) for l, p in labelled if flag(p) == 'Yes'], ', refereed'),
                  ([(l, p) for l, p in labelled if flag(p) == 'No'], ', not refereed'),
                  ([(l, p) for l, p in labelled if flag(p) not in ('Yes', 'No')],
                   ', refereed status not recorded')]
        if len(flags) == 1:                                  # all the same: no split, no suffix
            chunks = [(labelled, '')]
        for chunk, suffix in chunks:
            if not chunk:
                continue
            entries = [Entry(l, [_citation(cat, p, pattern)]) for l, p in chunk]
            ys = [text(p.get('Year') or p.get('Year Submitted')) for _, p in chunk]
            groups.append(with_years(f'{names.get(cat, cat)}{suffix} [n={len(chunk)}]', entries, ys,
                                     cat in cfg.REVIEWER_YEAR_DIVIDERS))
    return Section('Publications', groups)


def _presentations(s):
    talks = as_list(s.get('Presentations'))
    def entry(t):
        where = join(t.get('City'), t.get('Location'))
        return Entry(text(t.get('Presentation Year')),
                     [styled([P(t.get('Presentation Title')),
                              Part(DOT) if text(t.get('Conference / Event Name')) else None,
                              P(t.get('Conference / Event Name'), 'em'),
                              Part(f', {where}' if where else '', 'muted')])])
    keynotes = [t for t in talks if text(t.get('Keynote?')) == 'Yes']
    others = [t for t in talks if text(t.get('Keynote?')) != 'Yes']
    groups = []
    if keynotes:
        groups.append(Group(f'Keynote addresses [n={len(keynotes)}]', [entry(t) for t in keynotes]))
    if others:
        groups.append(Group(f'{"Other presentations" if keynotes else "Presentations"} '
                            f'[n={len(others)}]', [entry(t) for t in others]))
    return Section('Presentations', groups)


# --- Training, teaching, service, media ----------------------------------------------------

def _trainee(item):
    status = text(item.get('Student Degree Status'))
    role = text(item.get('Supervision Role'))
    name = [P(item.get('Student Name'))]
    if role and role != 'Principal Supervisor':
        name.append(Part(f' ({role.lower()})', 'muted'))
    if status and status not in ('Completed', 'In Progress'):
        name += [Part(' '), Part(f'[{status}]', 'tag')]
    body = [styled(name)]
    thesis = text(item.get(cfg.SUPERVISION_TITLE_FIELD))
    if thesis:
        body.append(styled([Part(thesis, 'em')], indent=1))
    present = present_position(item)
    if present:
        body.append(Line('→ ' + present, indent=1, muted=True))
    return Entry(years(item.get('Supervision Start Date'), item.get('Supervision End Date'),
                       ongoing=status == 'In Progress'), body)


def _training(s):
    records = as_list(s.get('Student/Postdoctoral Supervision'))
    grouped = group_supervision(records)
    groups = []
    if records:
        summary = []
        for label, items in grouped:
            st = Counter(text(i.get('Student Degree Status')) or 'status not given' for i in items)
            rl = Counter(text(i.get('Supervision Role')) or 'role not given' for i in items)
            status_txt = DOT.join(f'{n} {k.lower()}' for k, n in st.most_common())
            role_txt = DOT.join(f'{n} {k.lower()}' for k, n in rl.most_common())
            summary.append(Entry('', [styled([Part(label, 'self'),
                                              Part(f': {len(items)} total{DOT}{status_txt}')]),
                                      Line(role_txt, indent=1, muted=True)]))
        groups.append(Group('Summary', summary))
        groups += [Group(f'{label} [n={len(items)}]', [_trainee(i) for i in items])
                   for label, items in grouped]
    exams = as_list(s.get('Graduate Examination Activities'))
    if exams:
        groups.append(Group(f'Graduate examinations [n={len(exams)}]', [
            Entry(years(e.get('Start Date'), e.get('End Date')),
                  [styled([P(e.get('Graduate Examination Activity Role')),
                           Part(DOT) if text(e.get('Student Name')) else None,
                           P(e.get('Student Name'))])] + muted(join(e.get('Department'), org(e))))
            for e in exams]))
    staff = []
    for st in as_list(s.get('Staff Supervision')):
        bits = [f"{text(v)} {k.replace('Number of', '').strip().lower()}"
                for k, v in st.items() if k.startswith('Number of') and text(v)]
        if bits:
            staff.append(Entry(years(st.get('Start Date'), st.get('End Date')),
                               lines(DOT.join(' '.join(b.split()) for b in bits))))
    if staff:
        groups.append(Group('Staff supervision', staff))
    mentoring = as_list(s.get('Mentoring Activities'))
    if mentoring:
        groups.append(Group('Mentoring', [
            Entry(years(m.get('Start Date'), m.get('End Date'), ongoing=not text(m.get('End Date'))),
                  lines(m.get('Role')) + muted(join(org(m), f"{text(m.get('Number of Mentorees'))} "
                                                    f"mentoree(s)" if text(m.get('Number of Mentorees'))
                                                    else ''), m.get('Activity Description')))
            for m in mentoring]))
    return Section('Training and Mentoring', groups)


def _teaching(s):
    courses = OrderedDict()                   # merged by title, like the classic style
    for c in as_list(s.get('Courses Taught')):
        info = courses.setdefault(text(c.get('Course Title')),
                                  {'code': '', 'level': '', 'years': set()})
        info['code'] = info['code'] or text(c.get('Course Code'))
        info['level'] = info['level'] or text(c.get('Course Level'))
        start = (year_month(c.get('Start Date')) or (None,))[0]
        end = (year_month(c.get('End Date')) or (start,))[0]
        span = set(range(min(start, end), max(start, end) + 1)) if start and end else \
            ({start or end} if (start or end) else set())
        info['years'].update(span)
    groups = []
    if courses:
        groups.append(Group('Courses taught', [
            Entry(year_runs(c['years']) if c['years'] else '',
                  [styled([Part(f"{c['code']} " if c['code'] else '', 'muted'), Part(title),
                           Part(f" ({c['level'].lower()})" if c['level'] else '', 'muted')])])
            for title, c in courses.items()]))
    dev = as_list(s.get('Course Development'))
    if dev:
        groups.append(Group('Course development', [
            Entry(years(d.get('Date First Taught')),
                  [styled([P(d.get('Course Title')),
                           Part(f" ({text(d.get('Course Level')).lower()})"
                                if text(d.get('Course Level')) else '', 'muted')])]
                  + muted(d.get('Course Description')))
            for d in dev]))
    return Section('Teaching', groups)


def _dated(r, start='Start Date', end='End Date'):
    return years(r.get(start), r.get(end))


def _service(s):
    groups = []
    panels = as_list(s.get('Research Funding Application Assessment Activities'))
    if panels:
        groups.append(Group('Grant review panels', [
            Entry(_dated(r), lines(join(r.get('Funding Reviewer Role'), r.get('Committee Name'),
                                        r.get('Reviewer Type'), org(r)))
                  + muted(f"{text(r.get('Number of Applications Assessed'))} applications assessed"
                          if text(r.get('Number of Applications Assessed')) else ''))
            for r in panels]))
    editorial = as_list(s.get('Editorial Activities'))
    if editorial:
        groups.append(Group('Editorial roles', [
            Entry(_dated(r), [styled([P(r.get('Role')), Part(DOT), P(r.get('Publication Name'), 'em'),
                                      Part(f" ({text(r.get('Publication Type'))})"
                                           if text(r.get('Publication Type')) else '', 'muted')])]
                  + muted(r.get('Activity Description')))
            for r in editorial]))
    reviews = []
    for key, label in (('Journal Review Activities', 'Journal'),
                       ('Conference Review Activities', 'Conference')):
        merged = OrderedDict()
        for r in as_list(s.get(key)):
            k = (text(r.get('Role')), text(r.get(label)))
            m = merged.setdefault(k, {'years': set(), 'works': 0, 'n': 0})
            m['n'] += 1
            for d in (r.get('Start Date'), r.get('End Date')):
                if year_month(d):
                    m['years'].add(year_month(d)[0])
            try:
                m['works'] += int(float(text(r.get('Number of Works Reviewed / Refereed')) or 0))
            except ValueError:
                pass
        for (role, venue), m in merged.items():
            reviews.append(Entry(year_runs(m['years']) if m['years'] else '',
                                 [styled([P(role), Part(DOT) if venue else None, P(venue, 'em'),
                                          Part(f"{DOT}{m['works']} works reviewed" if m['works']
                                               else '', 'muted')])]))
    if reviews:
        groups.append(Group('Journal and conference reviewing', reviews))
    committees = as_list(s.get('Committee Memberships')) + as_list(s.get('Other Memberships'))
    if committees:
        groups.append(Group('Committees and memberships', [
            Entry(_dated(r, 'Membership Start Date', 'Membership End Date'),
                  lines(join(r.get('Role'), r.get('Committee Name'), org(r))) + muted(r.get('Description')))
            for r in committees]))
    events = as_list(s.get('Event Administration'))
    if events:
        groups.append(Group('Event organization', [
            Entry(_dated(r, 'Activity Start Date', 'Activity End Date'),
                  [styled([P(r.get('Role')), Part(DOT), P(r.get('Event Name')),
                           Part(f" ({text(r.get('Event Type')).lower()})" if text(r.get('Event Type'))
                                else '', 'muted')])] + muted(r.get('Activity Description')))
            for r in events]))
    community = as_list(s.get('Community and Volunteer Activities'))
    if community:
        groups.append(Group('Community and volunteer', [
            Entry(_dated(r), lines(join(r.get('Role'), org(r))) + muted(r.get('Activity Description')))
            for r in community]))
    return Section('Service', groups)


def _media(s):
    groups = []
    broadcast = as_list(s.get('Broadcast Interviews'))
    if broadcast:
        groups.append(Group(f'Broadcast interviews [n={len(broadcast)}]', [
            Entry(years(r.get('First Broadcast Date')),
                  [styled([P(r.get('Topic')), Part(DOT) if text(r.get('Program')) else None,
                           P(r.get('Program'), 'em'),
                           Part(f"{DOT}{text(r.get('Network'))}" if text(r.get('Network')) else '',
                                'muted')])])
            for r in broadcast]))
    textual = as_list(s.get('Text Interviews'))
    if textual:
        rows = []
        for r in textual:
            link = link_part(r)
            rows.append(Entry(years(r.get('Publication Date')),
                              [styled([P(r.get('Topic')), Part(DOT) if text(r.get('Forum')) else None,
                                       P(r.get('Forum'), 'em'),
                                       Part(' ') if link else None, link])]))
        groups.append(Group(f'Print and online interviews [n={len(textual)}]', rows))
    return Section('Media and Outreach', groups)


# --- Whole CV ---------------------------------------------------------------------------

def build_reviewer_cv(s):
    pi = s.get('Personal Information') or {}
    ident = pi.get('Identification') or {}
    name = join(ident.get('Title'), ident.get('First Name'), ident.get('Family Name'), sep=' ') \
        or 'Curriculum Vitae'
    pattern = owner_pattern(s)
    sections = [_profile(s), _degrees(s), _employment(s), _recognitions(s), _funding(s),
                _publications(s, pattern), _presentations(s), _training(s), _teaching(s),
                _service(s), _media(s)]
    for sec in sections:
        sec.groups = [g for g in sec.groups if g.entries]
    generated = text(s.get('_generated'))[:10]
    footer = f'{name} — Curriculum Vitae' + (f' (CCV export {generated})' if generated else '')
    return CV(name, [sec for sec in sections if sec.groups], style='reviewer',
              subtitle=_title_block(s, pi), footer=footer)
