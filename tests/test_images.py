"""Tests for FLUX image generation via the LiteLLM proxy.

The proxy speaks the OpenAI images API, so generate_image just calls
client.images.generate(...) and pulls the base64 PNG. The client is injected so
this runs offline.
"""

import base64

from content_pipeline.generate.images import GeneratedImage, generate_image


class _FakeImage:
    def __init__(self, b64):
        self.b64_json = b64
        self.url = None


class _FakeResp:
    def __init__(self, b64):
        self.data = [_FakeImage(b64)]


class _FakeClient:
    def __init__(self, b64):
        self._b64 = b64
        self.calls = []

        class _Images:
            def generate(_self, **kwargs):
                self.calls.append(kwargs)
                return _FakeResp(self._b64)

        self.images = _Images()


def test_generate_image_returns_b64_and_records_model():
    b64 = base64.b64encode(b"PNGDATA").decode()
    client = _FakeClient(b64)
    img = generate_image("a juggling otter, tabloid cover", client=client,
                         model="m3/ollama/flux2-klein")
    assert isinstance(img, GeneratedImage)
    assert img.b64_png == b64
    assert img.model == "m3/ollama/flux2-klein"
    # The model and prompt were passed through to the proxy.
    assert client.calls[0]["model"] == "m3/ollama/flux2-klein"
    assert "otter" in client.calls[0]["prompt"]


def test_generate_image_decodes_to_bytes():
    b64 = base64.b64encode(b"PNGDATA").decode()
    img = generate_image("x", client=_FakeClient(b64), model="m")
    assert img.to_bytes() == b"PNGDATA"
