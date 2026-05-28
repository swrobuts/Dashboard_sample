from backend.data.cleaner import clean_html


SAMPLE_HTML = """
<div class="mw-parser-output">
  <p>Einleitungstext über Apple.</p>
  <table class="infobox"><tr><td>infobox content (should be dropped)</td></tr></table>
  <h2><span class="mw-headline" id="Geschichte">Geschichte</span><span class="mw-editsection">[edit]</span></h2>
  <p>Apple wurde 1976 gegründet.</p>
  <h3><span class="mw-headline" id="Gr.C3.BCndung">Gründung</span></h3>
  <p>Steve Jobs, Steve Wozniak und Ronald Wayne.</p>
  <h2><span class="mw-headline" id="Produkte">Produkte</span></h2>
  <p>iPhone, iPad, Mac.</p>
  <h2><span class="mw-headline" id="Weblinks">Weblinks</span></h2>
  <p>https://apple.com (should be dropped by section title)</p>
</div>
"""


def test_clean_html_extracts_sections_and_strips_infobox():
    doc = clean_html(SAMPLE_HTML, "Apple")
    headings = [s.heading for s in doc.sections]
    assert "Geschichte" in headings
    assert "Produkte" in headings
    assert "Weblinks" not in headings
    assert "infobox content" not in doc.markdown


def test_section_tree_nests_h3_under_h2():
    doc = clean_html(SAMPLE_HTML, "Apple")
    history = next(s for s in doc.sections if s.heading == "Geschichte")
    assert any(c.heading == "Gründung" for c in history.children)
    gruendung = next(c for c in history.children if c.heading == "Gründung")
    assert gruendung.path == "Geschichte > Gründung"
    assert "Wozniak" in gruendung.text


def test_intro_paragraphs_become_einleitung_section():
    doc = clean_html(SAMPLE_HTML, "Apple")
    intro = next((s for s in doc.sections if s.heading == "Einleitung"), None)
    assert intro is not None
    assert "Einleitungstext" in intro.text


def test_edit_links_are_stripped_from_headings():
    doc = clean_html(SAMPLE_HTML, "Apple")
    assert all("[edit]" not in s.heading for s in doc.sections)
