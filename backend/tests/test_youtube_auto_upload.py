"""Unit tests for the YouTube auto-upload service (youtube_upload_service).

Covers the pure metadata builder (build_metadata) and the gating in
auto_upload_render: disabled -> no-op, enabled without credentials ->
clean skip, already uploaded -> skip, and the happy path with the
YouTube client mocked. Nothing here touches the network or a real DB.
"""

import asyncio

import pytest

from app.core.config import settings
from app.services import youtube_upload_service as svc


def _video_file(tmp_path):
    path = tmp_path / "render.mp4"
    path.write_bytes(b"0" * 2048)
    return str(path)


def _fake_credential(monkeypatch):
    async def fake_load():
        return {
            "access_token": "token",
            "refresh_token": "refresh",
            "client_id": "client-id",
            "client_secret": "client-secret",
            "token_expiry": None,
            "id": "cred-1",
        }

    monkeypatch.setattr(svc, "_load_active_credential", fake_load)


# ── build_metadata ──────────────────────────────────────────


def test_title_is_truncated_to_youtubes_100_chars():
    meta = svc.build_metadata("x" * 150)
    assert len(meta["title"]) == 100
    assert meta["title"].endswith("...")


def test_title_whitespace_collapsed_and_default_applied():
    assert svc.build_metadata("  My   Story  ")["title"] == "My Story"
    assert svc.build_metadata("")["title"] == "Untitled video"
    assert svc.build_metadata(None)["title"] == "Untitled video"


def test_description_gets_footer_and_is_capped():
    meta = svc.build_metadata("T", description="A short summary.")
    assert meta["description"].startswith("A short summary.")
    assert svc.DESCRIPTION_FOOTER in meta["description"]

    long_meta = svc.build_metadata("T", description="y" * 6000)
    assert len(long_meta["description"]) == svc.MAX_DESCRIPTION_LENGTH


def test_tags_merge_story_and_config_without_duplicates(monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_TAGS", "drama, Mystery , ,")
    meta = svc.build_metadata("T", tags=["Drama", " shorts "])
    # Story tags win, config tags append, case-insensitive de-duplication.
    assert meta["tags"] == ["Drama", "shorts", "Mystery"]


def test_privacy_and_category_default_from_settings(monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_PRIVACY_STATUS", "private")
    monkeypatch.setattr(settings, "UPLOAD_CATEGORY_ID", "22")
    meta = svc.build_metadata("T")
    assert meta["privacyStatus"] == "private"
    assert meta["categoryId"] == "22"


def test_privacy_and_category_explicit_override():
    meta = svc.build_metadata("T", privacy_status="unlisted", category_id="27")
    assert meta["privacyStatus"] == "unlisted"
    assert meta["categoryId"] == "27"


# ── gating ──────────────────────────────────────────────────


def test_disabled_auto_upload_is_a_noop(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "AUTO_UPLOAD_YOUTUBE", False)

    async def explode():
        raise AssertionError("credential loader must not run while disabled")

    monkeypatch.setattr(svc, "_load_active_credential", explode)
    result = asyncio.run(
        svc.auto_upload_render("out-1", _video_file(tmp_path), title="T")
    )
    assert result["status"] == "skipped"


def test_dispatch_returns_false_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "AUTO_UPLOAD_YOUTUBE", False)
    assert svc.dispatch_auto_upload("out-1", "/nonexistent.mp4") is False


def test_enabled_without_credentials_skips_cleanly(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "AUTO_UPLOAD_YOUTUBE", True)
    monkeypatch.setattr(svc, "_already_uploaded", lambda rid: False)

    async def no_credential():
        return None

    monkeypatch.setattr(svc, "_load_active_credential", no_credential)
    result = asyncio.run(
        svc.auto_upload_render("out-1", _video_file(tmp_path), title="T")
    )
    assert result["status"] == "skipped"
    assert "credentials" in result["reason"]


def test_enabled_but_already_uploaded_skips_before_credentials(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(settings, "AUTO_UPLOAD_YOUTUBE", True)
    monkeypatch.setattr(svc, "_already_uploaded", lambda rid: True)

    async def explode():
        raise AssertionError("credential loader must not run for a duplicate")

    monkeypatch.setattr(svc, "_load_active_credential", explode)
    result = asyncio.run(
        svc.auto_upload_render("out-1", _video_file(tmp_path), title="T")
    )
    assert result["status"] == "skipped"
    assert "already uploaded" in result["reason"]


# ── happy path (client + DB mocked) ─────────────────────────


def test_successful_auto_upload_records_video_id(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "AUTO_UPLOAD_YOUTUBE", True)
    monkeypatch.setattr(svc, "_already_uploaded", lambda rid: False)
    _fake_credential(monkeypatch)

    updates = {}
    monkeypatch.setattr(svc, "_create_upload_record", lambda *a: "rec-1")
    monkeypatch.setattr(
        svc,
        "_update_upload_record",
        lambda record_id, **kw: updates.update(kw),
    )

    async def no_notify(text):
        return None

    monkeypatch.setattr(svc, "_notify_telegram", no_notify)

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def upload_video(self, **kwargs):
            assert kwargs["privacy_status"] == settings.UPLOAD_PRIVACY_STATUS
            return {"video_id": "vid123", "url": "https://youtube.com/watch?v=vid123"}

    monkeypatch.setattr(svc, "YouTubeClient", FakeClient)

    result = asyncio.run(
        svc.auto_upload_render("out-1", _video_file(tmp_path), title="My Story")
    )
    assert result["status"] == "uploaded"
    assert result["video_id"] == "vid123"
    assert updates["status"] == "uploaded"
    assert updates["video_id"] == "vid123"
