"""PDF output: CV data -> HTML (Jinja2 template) -> PDF (WeasyPrint).

Page size, fonts and spacing are in the templates:
cv_tmpl.html (classic style) and cv_tmpl_reviewer.html (reviewer style).
"""

import os
import pathlib

import jinja2

TEMPLATE_DIR = pathlib.Path(__file__).resolve().parent
TEMPLATES = {'classic': 'cv_tmpl.html', 'reviewer': 'cv_tmpl_reviewer.html'}


def render_html(cv):
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(TEMPLATE_DIR),
                             autoescape=True, trim_blocks=True, lstrip_blocks=True)
    return env.get_template(TEMPLATES[cv.style]).render(cv=cv)


def write_pdf(cv, out_path):
    # Windows: use MSYS2's Pango libraries if installed in the default place (see README).
    msys = pathlib.Path(r'C:\msys64\mingw64\bin')
    if os.name == 'nt' and msys.is_dir():
        os.environ.setdefault('WEASYPRINT_DLL_DIRECTORIES', str(msys))
    import weasyprint  # imported here so DOCX output works even without WeasyPrint's libraries
    weasyprint.HTML(string=render_html(cv), base_url=str(TEMPLATE_DIR)).write_pdf(str(out_path))
