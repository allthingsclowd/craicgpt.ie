"""Tests for frontend asset sync (so the deployed site never drifts from the repo).

The bug this guards against: the schema-v3 frontend was rebuilt but the assets on
S3 were never re-synced, so the live site rendered the old shell. The publish flow
now syncs the frontend; this proves the diff/upload/skip logic offline.
"""

from content_pipeline.agent import frontend


class _FakeS3:
    def __init__(self, existing=None):
        self.objects = dict(existing or {})   # key -> body bytes
        self.puts = []

    def head_object(self, *, Bucket, Key):
        import hashlib
        if Key not in self.objects:
            from botocore.exceptions import ClientError
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        etag = hashlib.md5(self.objects[Key]).hexdigest()
        return {"ETag": f'"{etag}"'}

    def put_object(self, *, Bucket, Key, Body, **kw):
        self.objects[Key] = Body
        self.puts.append({"Key": Key, **kw})


def _frontend(tmp_path):
    (tmp_path / "index.html").write_text("<html>v3</html>")
    (tmp_path / "static_assets").mkdir()
    (tmp_path / "static_assets" / "main.js").write_text("console.log(1)")
    (tmp_path / "README.md").write_text("ignore me")
    return tmp_path


def test_uploads_all_when_bucket_empty(tmp_path):
    s3 = _FakeS3()
    res = frontend.sync_frontend(_frontend(tmp_path), s3=s3, bucket="b", cloudfront_id=None)
    keys = set(res["uploaded"])
    assert "index.html" in keys and "static_assets/main.js" in keys
    assert "README.md" not in keys                      # excluded


def test_skips_unchanged_uploads_changed(tmp_path):
    import hashlib
    fe = _frontend(tmp_path)
    # Pre-seed S3 with the CURRENT index.html (unchanged) but an OLD main.js.
    s3 = _FakeS3({
        "index.html": b"<html>v3</html>",
        "static_assets/main.js": b"OLD",
    })
    res = frontend.sync_frontend(fe, s3=s3, bucket="b", cloudfront_id=None)
    assert "index.html" not in res["uploaded"]          # identical → skipped
    assert "static_assets/main.js" in res["uploaded"]   # differs → uploaded


def test_content_type_and_cache_control(tmp_path):
    s3 = _FakeS3()
    frontend.sync_frontend(_frontend(tmp_path), s3=s3, bucket="b", cloudfront_id=None)
    by_key = {p["Key"]: p for p in s3.puts}
    assert by_key["static_assets/main.js"]["ContentType"] in (
        "application/javascript", "text/javascript")
    assert by_key["index.html"]["ContentType"] == "text/html"
    # HTML gets a short TTL so future deploys surface fast; assets longer.
    assert "max-age=60" in by_key["index.html"]["CacheControl"]
    assert "max-age=60" not in by_key["static_assets/main.js"]["CacheControl"]


def test_invalidates_only_when_something_changed(tmp_path):
    fe = _frontend(tmp_path)
    seen = {"calls": []}
    frontend.sync_frontend(fe, s3=_FakeS3(), bucket="b", cloudfront_id="CF123",
                           _invalidate=lambda cf, paths: seen["calls"].append((cf, paths)))
    assert seen["calls"], "should invalidate after uploading new assets"
    # nothing-changed case: pre-seed everything, expect no invalidation
    import hashlib
    s3full = _FakeS3({"index.html": b"<html>v3</html>",
                      "static_assets/main.js": b"console.log(1)"})
    seen2 = {"calls": []}
    frontend.sync_frontend(fe, s3=s3full, bucket="b", cloudfront_id="CF123",
                           _invalidate=lambda cf, paths: seen2["calls"].append(1))
    assert not seen2["calls"]
