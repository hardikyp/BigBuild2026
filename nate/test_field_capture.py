"""Tests for field_capture.py. Run from nate/: python -m pytest"""
import base64
import io
from types import SimpleNamespace

import pytest
from PIL import Image

import field_capture as fc


def make_image(w, h, fmt='PNG', orientation=None):
    img = Image.new('RGB', (w, h), (120, 130, 140))
    out = io.BytesIO()
    kwargs = {}
    if orientation:
        exif = Image.Exif()
        exif[0x0112] = orientation
        kwargs['exif'] = exif.tobytes()
    img.save(out, format=fmt, **kwargs)
    return out.getvalue()


class FakeClient:
    def __init__(self, content):
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)
        self._content = content

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content=self._content)


def tool_use(payload, name=fc.TOOL_NAME):
    return SimpleNamespace(type='tool_use', name=name, input=payload)


# prepare_photo

def test_prepare_photo_resizes_long_edge_and_outputs_jpeg():
    out = fc.prepare_photo(make_image(4000, 3000))
    img = Image.open(io.BytesIO(out))
    assert img.format == 'JPEG'
    assert img.size == (1568, 1176)


def test_prepare_photo_keeps_small_images_and_strips_exif():
    out = fc.prepare_photo(make_image(800, 600, 'JPEG', orientation=1))
    img = Image.open(io.BytesIO(out))
    assert img.size == (800, 600)
    assert 0x0112 not in img.getexif()


def test_prepare_photo_applies_exif_rotation():
    # Orientation 6 = rotate 90° clockwise to display.
    out = fc.prepare_photo(make_image(400, 200, 'JPEG', orientation=6))
    assert Image.open(io.BytesIO(out)).size == (200, 400)


def test_prepare_photo_rejects_non_images():
    with pytest.raises(fc.InterpretError) as e:
        fc.prepare_photo(b'not an image')
    assert e.value.code == 'bad_request'


# build_user_prompt

def test_user_prompt_includes_context_and_item():
    text = fc.build_user_prompt({
        'building_type': 'W1', 'performance_level': 'LS', 'seismicity': 'High',
        'location_in_building': 'Level 2', 'user_note': 'crack near sill',
        'checklist_item': {'id': 'BC-01', 'title': 'Load Path', 'text': 'Verify a load path.'},
    })
    assert '- Building type: W1' in text
    assert '- Performance level: LS (Life Safety)' in text
    assert '- Level of seismicity: High' in text
    assert '- Location in building: Level 2' in text
    assert '- Checklist item being evaluated: [BC-01] Load Path' in text
    assert '- Item statement: Verify a load path.' in text
    assert "- Engineer's note: crack near sill" in text
    assert text.endswith('Interpret the photo.')


def test_user_prompt_without_item_asks_for_null_status():
    text = fc.build_user_prompt({'building_type': 'URM', 'location_in_building': ''})
    assert 'set suggestedStatus to null' in text
    assert 'Location in building' not in text


# normalize_interpretation

def test_normalize_fills_defaults_and_drops_bad_values():
    out = fc.normalize_interpretation({'suggestedStatus': 'maybe', 'followUp': ['ok', 3], 'imageQuality': 'bad'}, 'm')
    assert out['summary'] == ''
    assert out['components'] == [] and out['observations'] == [] and out['possibleDeficiencies'] == []
    assert out['suggestedStatus'] is None
    assert out['followUp'] == ['ok']
    assert out['imageQuality'] == {'usable': True, 'issues': []}
    assert out['model'] == 'm' and out['createdAt']


def test_normalize_keeps_valid_fields():
    raw = {'summary': 's', 'suggestedStatus': 'N/A', 'statusRationale': 'r',
           'imageQuality': {'usable': False, 'issues': ['blurry']}}
    out = fc.normalize_interpretation(raw, 'm')
    assert out['suggestedStatus'] == 'N/A'
    assert out['statusRationale'] == 'r'
    assert out['imageQuality'] == {'usable': False, 'issues': ['blurry']}


# interpret_photo

def test_interpret_photo_sends_forced_tool_call_with_image_and_context():
    client = FakeClient([tool_use({'summary': 'Wood stud wall.', 'suggestedStatus': 'U'})])
    jpeg = fc.prepare_photo(make_image(100, 100))
    out = fc.interpret_photo(jpeg, {'building_type': 'W1'}, client=client, model='test-model')

    call = client.calls[0]
    assert call['model'] == 'test-model'
    assert call['system'] == fc.SYSTEM_PROMPT
    assert call['tool_choice'] == {'type': 'tool', 'name': fc.TOOL_NAME}
    assert call['tools'][0]['input_schema'] is fc.OUTPUT_SCHEMA
    image, text = call['messages'][0]['content']
    assert image['source']['media_type'] == 'image/jpeg'
    assert base64.b64decode(image['source']['data']) == jpeg
    assert 'Building type: W1' in text['text']
    assert out['summary'] == 'Wood stud wall.'
    assert out['suggestedStatus'] == 'U'
    assert out['model'] == 'test-model'


def test_interpret_photo_uses_env_model(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_MODEL', 'env-model')
    client = FakeClient([tool_use({})])
    assert fc.interpret_photo(b'x', client=client)['model'] == 'env-model'


def test_interpret_photo_without_tool_use_is_invalid_output():
    client = FakeClient([SimpleNamespace(type='text', text='hello')])
    with pytest.raises(fc.InterpretError) as e:
        fc.interpret_photo(b'x', client=client)
    assert e.value.code == 'invalid_model_output'


def test_interpret_photo_requires_api_key(monkeypatch):
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    with pytest.raises(fc.InterpretError) as e:
        fc.interpret_photo(b'x')
    assert e.value.code == 'server_misconfigured'


def test_interpret_photo_rejects_oversize_image():
    with pytest.raises(fc.InterpretError) as e:
        fc.interpret_photo(b'x' * (fc.MAX_IMAGE_BYTES + 1), client=FakeClient([]))
    assert e.value.code == 'image_too_large'


def test_interpret_photo_maps_api_errors():
    import anthropic

    def boom(**kwargs):
        # Built without __init__ so the test doesn't depend on the SDK's HTTP transport.
        raise anthropic.APIConnectionError.__new__(anthropic.APIConnectionError, 'Connection error.')

    client = SimpleNamespace(messages=SimpleNamespace(create=boom))
    with pytest.raises(fc.InterpretError) as e:
        fc.interpret_photo(b'x', client=client)
    assert e.value.code == 'upstream_error'
