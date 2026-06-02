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


def test_generate_image_does_not_send_response_format():
    # The Ollama image route rejects response_format — we must not send it.
    client = _FakeClient(base64.b64encode(b"x").decode())
    generate_image("x", client=client, model="m")
    assert "response_format" not in client.calls[0]


class _UrlResp:
    def __init__(self, url):
        class _I:
            def __init__(s):
                s.b64_json = None
                s.url = url
        self.data = [_I()]


def test_generate_image_handles_url_response():
    class _UrlClient:
        def __init__(self):
            class _Images:
                def generate(_s, **kw):
                    return _UrlResp("https://cdn/x.png")
            self.images = _Images()

    img = generate_image("x", client=_UrlClient(), model="m")
    assert img.url == "https://cdn/x.png"
    assert img.b64_png is None
