"""Tests for checklist_text.py, using made-up text in the checklist file's layout. Run from nate/: python -m pytest"""
import checklist_text as ct

SAMPLE = """17.1.1CP Very Low Seismicity Checklist
Table 17-1. Very Low Seismicity Checklist.
Status Evaluation Statement
Tier 2
Reference
Commentary
Reference Comments
Structural Components
C NC N/A U ALPHA: First line of the
alpha statement, which con-
tinues here.
1.2.3.4 A.1.1
C NC N/A U BETA ITEM: Beta statement
without references.

17.1.2CP Basic Configuration Checklist
Table 17-2. Basic Configuration Checklist.
Status Evaluation Statement
Tier 2
Reference
Commentary
Reference Comments
Low Seismicity
Building System—General
C NC N/A U GAMMA: Gamma statement.
1.2.3.5 A.1.2
Building System—Configuration
C NC N/A U DELTA: Delta statement mentioning
Section 4.4.3.7.
1.2.3.6 A.
Moderate Seismicity (Complete the Following Items in Addition to the Items for Low Seismicity)
Site Hazards
C NC N/A U EPSILON: Epsilon statement.
1.2.4.1 A.6.1.1
Status Evaluation Statement
Tier 2
Reference
Commentary
Reference Comments
High Seismicity (Complete the Following Items in Addition to the Items for Moderate Seismicity)
Foundation Configuration
C NC N/A U ZETA TWO
WORDS: Zeta statement.
17.2IO Type W1 and W1a Checklist
Wood Frames
C NC N/A U ETA: Eta statement.
5.5.1.1
"""


def rows_by_topic():
    return {r['topic']: r for r in ct.parse_checklist_text(SAMPLE)}


def test_parses_every_item_with_refs_and_ids():
    rows = ct.parse_checklist_text(SAMPLE)
    assert [r['id'] for r in rows] == ['17.1.1CP-01', '17.1.1CP-02', '17.1.2CP-01', '17.1.2CP-02', '17.1.2CP-03', '17.1.2CP-04', '17.2IO-01']
    alpha = rows[0]
    assert alpha == {'id': '17.1.1CP-01', 'checklist': 'Very Low Seismicity Checklist', 'building_types': 'ALL', 'performance': 'CP',
                     'seismicity': 'Very Low', 'section': 'Structural Components', 'topic': 'Alpha',
                     'statement': 'First line of the alpha statement, which continues here.', 'tier2_ref': '1.2.3.4', 'commentary_ref': 'A.1.1'}


def test_item_without_refs_ends_at_blank_line_or_next_form():
    r = rows_by_topic()
    assert r['Beta Item']['statement'] == 'Beta statement without references.'
    assert r['Beta Item']['tier2_ref'] == ''
    assert r['Zeta Two Words']['statement'] == 'Zeta statement.'


def test_sections_and_cumulative_seismicity():
    r = rows_by_topic()
    assert (r['Gamma']['section'], r['Gamma']['seismicity']) == ('Building System—General', 'Low,Moderate,High')
    assert (r['Delta']['section'], r['Delta']['seismicity']) == ('Building System—Configuration', 'Low,Moderate,High')
    assert (r['Epsilon']['section'], r['Epsilon']['seismicity']) == ('Site Hazards', 'Moderate,High')
    assert (r['Zeta Two Words']['section'], r['Zeta Two Words']['seismicity']) == ('Foundation Configuration', 'High')


def test_statement_numbers_are_not_mistaken_for_refs():
    d = rows_by_topic()['Delta']
    assert d['statement'] == 'Delta statement mentioning Section 4.4.3.7.'
    assert (d['tier2_ref'], d['commentary_ref']) == ('1.2.3.6', 'A.')


def test_building_types_and_performance_from_form_title():
    eta = rows_by_topic()['Eta']
    assert (eta['building_types'], eta['performance'], eta['tier2_ref'], eta['commentary_ref']) == ('W1,W1A', 'IO', '5.5.1.1', '')


def test_load_checklist_missing_file(tmp_path):
    assert ct.load_checklist(tmp_path / 'nope.txt') == []


def test_load_checklist_reads_utf8(tmp_path):
    p = tmp_path / 'list.txt'
    p.write_text(SAMPLE, encoding='utf-8')
    assert len(ct.load_checklist(p)) == 7
