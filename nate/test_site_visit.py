"""Tests for site_visit.py. Run from nate/: python -m pytest"""
from types import SimpleNamespace

import pytest

import field_capture as fc
import site_visit as sv

RECORDS = [
    {'id': 'BC-01', 'topic': 'Load Path', 'statement': 'Verify a load path.', 'status': 'Compliant', 'basis': 'Seen on site', 'action': '', 'evidence': '', 'tier2_ref': '5.4.1.1', 'photo': ''},
    {'id': 'BC-02', 'topic': 'Adjacent Buildings', 'statement': 'Check separation.', 'status': 'Noncompliant', 'basis': '', 'action': 'Measure gap', 'evidence': '', 'tier2_ref': '5.4.1.2', 'photo': 'BC-02_1.jpg'},
    {'id': 'BC-03', 'topic': 'Mezzanines', 'statement': 'Check mezzanine.', 'status': 'Not reviewed', 'basis': '', 'action': '', 'evidence': '', 'tier2_ref': '5.4.1.3', 'photo': ''},
    {'id': 'VL-01', 'topic': 'Load Path', 'statement': 'Very low.', 'status': 'Unknown', 'basis': '', 'action': '', 'evidence': '', 'tier2_ref': '5.4.1.1', 'photo': ''},
]
PHOTOS = {'BC-02': {'name': 'BC-02_1.jpg', 'takenAt': '2026-10-27T12:00', 'jpeg': b'\xff\xd8fakejpeg', 'location': 'North wall', 'note': '',
                    'interpretation': {'summary': 'Narrow gap <2in> to neighbor.', 'suggestedStatus': 'NC', 'statusRationale': 'Gap looks small.',
                                       'observations': [{'description': 'Gap under 2 in', 'severity': 'moderate'}],
                                       'possibleDeficiencies': [{'description': 'Pounding risk', 'confidence': 'medium'}],
                                       'followUp': ['Measure the gap at roof level'], 'model': 'm'}}}
META = {'project': 'Test & Co <HQ>', 'address': '1 Main St', 'objective': 'Collapse Prevention (CP)', 'seismicity': 'High', 'building_type': 'W1', 'project_id': 'abc123'}


class FakeClient:
    def __init__(self, content):
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)
        self._content = content

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content=self._content)


def tool_use(payload):
    return SimpleNamespace(type='tool_use', name=sv.TOOL_NAME, input=payload)


# baseline_checks / fallback_review

def test_baseline_covers_unresolved_items_and_photo_follow_ups():
    checks = sv.baseline_checks(RECORDS, PHOTOS)
    by_item = {(c['itemId'], c['title']) for c in checks}
    assert {c['itemId'] for c in checks} == {'BC-02', 'BC-03', 'VL-01'}
    assert ('BC-02', 'Measure the gap at roof level') in by_item
    nc = next(c for c in checks if c['itemId'] == 'BC-02' and c['title'].startswith('Resolve'))
    assert nc['priority'] == 'high' and nc['reason'] == 'Measure gap'
    not_reviewed = next(c for c in checks if c['itemId'] == 'BC-03')
    assert not_reviewed['where'] == 'on_site'


def test_fallback_is_not_ready_with_open_high_on_site_checks():
    assert sv.fallback_review(RECORDS[:1], {})['readyToClose'] is True
    review = sv.fallback_review(RECORDS, PHOTOS)
    assert review['model'] is None and review['summary'] == ''
    assert review['readyToClose'] is True  # Noncompliant item is office work in the baseline
    assert len(review['checks']) == 4


# prompt

def test_review_prompt_includes_records_and_photo_interpretations():
    text = sv.build_review_prompt(META, RECORDS, PHOTOS)
    assert '- building_type: W1' in text
    assert '[BC-02] Adjacent Buildings | status: Noncompliant' in text
    assert 'follow-up noted: Measure gap' in text
    assert 'BC-02_1.jpg (item BC-02, location: North wall)' in text
    assert 'possible deficiency (medium): Pounding risk' in text
    assert 'follow-up: Measure the gap at roof level' in text


def test_review_prompt_without_photos():
    assert 'No photos were taken.' in sv.build_review_prompt(META, RECORDS, {})


# normalize / backfill

def test_normalize_drops_bad_checks_and_fills_defaults():
    out = sv.normalize_review({'summary': 3, 'readyToClose': 'yes', 'checks': [
        {'title': 'Measure gap', 'priority': 'urgent', 'where': 'roof'}, {'title': ''}, 'junk', {'priority': 'high'}]}, 'm')
    assert out['summary'] == '' and out['readyToClose'] is False
    assert out['checks'] == [{'itemId': '', 'title': 'Measure gap', 'reason': '', 'priority': 'medium', 'where': 'office'}]


def test_add_missing_baseline_backfills_skipped_items_only():
    review = sv.normalize_review({'summary': 's', 'readyToClose': False, 'checks': [
        {'itemId': 'BC-02', 'title': 'Measure gap', 'priority': 'high', 'where': 'on_site'}]}, 'm')
    out = sv.add_missing_baseline(review, RECORDS)
    assert [c['itemId'] for c in out['checks']] == ['BC-02', 'BC-03', 'VL-01']


# review_visit

def test_review_visit_sends_forced_tool_call_and_backfills():
    client = FakeClient([tool_use({'summary': 'One NC item.', 'readyToClose': False, 'closeRationale': 'Gap not measured.',
                                   'checks': [{'itemId': 'BC-02', 'title': 'Measure gap', 'reason': 'NC', 'priority': 'high', 'where': 'on_site'}]})])
    out = sv.review_visit(META, RECORDS, PHOTOS, client=client, model='test-model')
    call = client.calls[0]
    assert call['model'] == 'test-model'
    assert call['system'] == sv.REVIEW_SYSTEM_PROMPT
    assert call['tool_choice'] == {'type': 'tool', 'name': sv.TOOL_NAME}
    assert '[BC-03] Mezzanines' in call['messages'][0]['content']
    assert out['summary'] == 'One NC item.' and out['model'] == 'test-model'
    assert {c['itemId'] for c in out['checks']} == {'BC-02', 'BC-03', 'VL-01'}


def test_review_visit_requires_api_key(monkeypatch):
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    with pytest.raises(fc.InterpretError) as e:
        sv.review_visit(META, RECORDS, PHOTOS)
    assert e.value.code == 'server_misconfigured'


def test_review_visit_without_tool_use_is_invalid_output():
    with pytest.raises(fc.InterpretError) as e:
        sv.review_visit(META, RECORDS, PHOTOS, client=FakeClient([SimpleNamespace(type='text', text='hi')]))
    assert e.value.code == 'invalid_model_output'


# report

def test_report_escapes_text_embeds_photos_and_marks_checks():
    review = sv.normalize_review({'summary': 'Gap <b>small</b>.', 'readyToClose': False, 'checks': [
        {'itemId': 'BC-02', 'title': 'Measure gap', 'priority': 'high', 'where': 'on_site'},
        {'itemId': '', 'title': 'Get drawings', 'priority': 'low', 'where': 'office'}]}, 'm')
    page = sv.build_report_html(META, RECORDS, PHOTOS, review, {0: True}, '2026-10-27 15:00')
    assert page.startswith('<!doctype html>')
    assert 'Test &amp; Co &lt;HQ&gt;' in page and '<HQ>' not in page
    assert 'Gap &lt;b&gt;small&lt;/b&gt;.' in page
    assert 'Narrow gap &lt;2in&gt; to neighbor.' in page
    assert 'src="data:image/jpeg;base64,' in page
    assert '1 open, 1 done before leaving site.' in page
    assert '<td>Done</td>' in page and '<td>Open</td>' in page
    assert 'AI-drafted by m' in page
    for r in RECORDS:
        assert r['id'] in page


def test_report_without_review_summary_or_photos():
    page = sv.build_report_html({}, RECORDS[:1], {}, sv.fallback_review(RECORDS[:1], {}), {}, 'now')
    assert 'Untitled project' in page
    assert 'Visit summary' not in page
    assert 'No photos taken.' in page
    assert 'None proposed.' in page
