"""Tests for the Telegram transport adapter."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from telegram.constants import ChatAction

from megobari.formatting import TelegramFormatter
from megobari.telegram_transport import TelegramTransport, telegram_handler

# -- Helpers --


def _make_update(
    *,
    text="hello",
    chat_id=12345,
    user_id=67890,
    message_id=42,
    username="testuser",
    first_name="Test",
    last_name="User",
    caption=None,
    has_photo=False,
    has_document=False,
    has_voice=False,
    no_message=False,
    no_user=False,
):
    """Build a mock telegram.Update with sensible defaults."""
    update = MagicMock()

    if no_message:
        update.message = None
    else:
        msg = MagicMock()
        msg.text = text
        msg.caption = caption
        msg.message_id = message_id
        msg.reply_text = AsyncMock(return_value=MagicMock())
        msg.reply_document = AsyncMock()
        msg.reply_photo = AsyncMock()

        msg.photo = (
            [MagicMock(), MagicMock()]  # small, large
            if has_photo
            else []
        )
        msg.document = MagicMock() if has_document else None
        msg.voice = MagicMock() if has_voice else None
        update.message = msg

    update.effective_chat = MagicMock()
    update.effective_chat.id = chat_id

    if no_user:
        update.effective_user = None
    else:
        update.effective_user = MagicMock()
        update.effective_user.id = user_id
        update.effective_user.username = username
        update.effective_user.first_name = first_name
        update.effective_user.last_name = last_name

    return update


def _make_context(*, args=None, bot_data=None):
    """Build a mock telegram.ext context."""
    ctx = MagicMock()
    ctx.args = args
    ctx.bot_data = bot_data if bot_data is not None else {
        "session_manager": MagicMock(),
    }
    ctx.bot = AsyncMock()
    return ctx


def _make_transport(**kwargs):
    """Build a TelegramTransport from mocks, returning (transport, update, context)."""
    update_kw = {}
    ctx_kw = {}
    for k in ("args", "bot_data"):
        if k in kwargs:
            ctx_kw[k] = kwargs.pop(k)
    update_kw = kwargs
    update = _make_update(**update_kw)
    context = _make_context(**ctx_kw)
    return TelegramTransport(update, context), update, context


# ============================================================
# Properties — input data
# ============================================================


class TestProperties:
    def test_args_from_context(self):
        t, _, _ = _make_transport(args=["on", "15"])
        assert t.args == ["on", "15"]

    def test_args_default_empty(self):
        t, _, _ = _make_transport(args=None)
        assert t.args == []

    def test_text(self):
        t, _, _ = _make_transport(text="hi there")
        assert t.text == "hi there"

    def test_text_none_when_no_message(self):
        t, _, _ = _make_transport(no_message=True)
        assert t.text is None

    def test_chat_id(self):
        t, _, _ = _make_transport(chat_id=999)
        assert t.chat_id == 999

    def test_message_id(self):
        t, _, _ = _make_transport(message_id=77)
        assert t.message_id == 77

    def test_user_id(self):
        t, _, _ = _make_transport(user_id=111)
        assert t.user_id == 111

    def test_user_id_zero_when_no_user(self):
        t, _, _ = _make_transport(no_user=True)
        assert t.user_id == 0

    def test_username(self):
        t, _, _ = _make_transport(username="alice")
        assert t.username == "alice"

    def test_username_none_when_no_user(self):
        t, _, _ = _make_transport(no_user=True)
        assert t.username is None

    def test_first_name(self):
        t, _, _ = _make_transport(first_name="Alice")
        assert t.first_name == "Alice"

    def test_first_name_none_when_no_user(self):
        t, _, _ = _make_transport(no_user=True)
        assert t.first_name is None

    def test_last_name(self):
        t, _, _ = _make_transport(last_name="Smith")
        assert t.last_name == "Smith"

    def test_last_name_none_when_no_user(self):
        t, _, _ = _make_transport(no_user=True)
        assert t.last_name is None

    def test_caption(self):
        t, _, _ = _make_transport(caption="look at this")
        assert t.caption == "look at this"

    def test_caption_none_by_default(self):
        t, _, _ = _make_transport()
        assert t.caption is None

    def test_caption_none_when_no_message(self):
        t, _, _ = _make_transport(no_message=True)
        assert t.caption is None


# ============================================================
# Properties — shared state
# ============================================================


class TestSharedState:
    def test_session_manager(self):
        sm = MagicMock()
        t, _, _ = _make_transport(bot_data={"session_manager": sm})
        assert t.session_manager is sm

    def test_formatter_is_telegram(self):
        t, _, _ = _make_transport()
        assert isinstance(t.formatter, TelegramFormatter)

    def test_bot_data(self):
        bd = {"session_manager": MagicMock(), "foo": "bar"}
        t, _, _ = _make_transport(bot_data=bd)
        assert t.bot_data is bd
        assert t.bot_data["foo"] == "bar"


# ============================================================
# Properties — transport metadata
# ============================================================


class TestMetadata:
    def test_transport_name(self):
        t, _, _ = _make_transport()
        assert t.transport_name == "telegram"

    def test_max_message_length(self):
        t, _, _ = _make_transport()
        assert t.max_message_length == 4096


# ============================================================
# Messaging methods
# ============================================================


class TestMessaging:
    async def test_reply_plain(self):
        t, update, _ = _make_transport()
        result = await t.reply("hello")
        update.message.reply_text.assert_awaited_once_with("hello")
        assert result is update.message.reply_text.return_value

    async def test_reply_formatted(self):
        t, update, _ = _make_transport()
        await t.reply("<b>bold</b>", formatted=True)
        update.message.reply_text.assert_awaited_once_with(
            "<b>bold</b>", parse_mode="HTML"
        )

    async def test_reply_document(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("content")
        t, update, _ = _make_transport()
        await t.reply_document(f, "test.txt")
        update.message.reply_document.assert_awaited_once()
        call_kwargs = update.message.reply_document.call_args[1]
        assert call_kwargs["filename"] == "test.txt"
        assert "caption" not in call_kwargs

    async def test_reply_document_with_caption(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("content")
        t, update, _ = _make_transport()
        await t.reply_document(f, "test.txt", caption="here you go")
        call_kwargs = update.message.reply_document.call_args[1]
        assert call_kwargs["caption"] == "here you go"

    async def test_reply_photo(self, tmp_path):
        f = tmp_path / "img.png"
        f.write_bytes(b"\x89PNG")
        t, update, _ = _make_transport()
        await t.reply_photo(f)
        update.message.reply_photo.assert_awaited_once()
        call_kwargs = update.message.reply_photo.call_args[1]
        assert "caption" not in call_kwargs

    async def test_reply_photo_with_caption(self, tmp_path):
        f = tmp_path / "img.png"
        f.write_bytes(b"\x89PNG")
        t, update, _ = _make_transport()
        await t.reply_photo(f, caption="nice pic")
        call_kwargs = update.message.reply_photo.call_args[1]
        assert call_kwargs["caption"] == "nice pic"

    async def test_send_message(self):
        t, _, ctx = _make_transport(chat_id=555)
        await t.send_message("broadcast")
        ctx.bot.send_message.assert_awaited_once_with(
            chat_id=555, text="broadcast"
        )

    async def test_edit_message_plain(self):
        t, _, _ = _make_transport()
        handle = AsyncMock()
        await t.edit_message(handle, "updated")
        handle.edit_text.assert_awaited_once_with("updated")

    async def test_edit_message_formatted(self):
        t, _, _ = _make_transport()
        handle = AsyncMock()
        await t.edit_message(handle, "<i>new</i>", formatted=True)
        handle.edit_text.assert_awaited_once_with(
            "<i>new</i>", parse_mode="HTML"
        )

    async def test_delete_message(self):
        t, _, _ = _make_transport()
        handle = AsyncMock()
        await t.delete_message(handle)
        handle.delete.assert_awaited_once()


# ============================================================
# Indicators
# ============================================================


class TestIndicators:
    async def test_send_typing(self):
        t, _, ctx = _make_transport(chat_id=555)
        await t.send_typing()
        ctx.bot.send_chat_action.assert_awaited_once_with(
            chat_id=555, action=ChatAction.TYPING
        )

    async def test_set_reaction_emoji(self):
        t, _, ctx = _make_transport(chat_id=555, message_id=42)
        await t.set_reaction("\U0001f440")
        ctx.bot.set_message_reaction.assert_awaited_once_with(
            chat_id=555, message_id=42, reaction=["\U0001f440"]
        )

    async def test_set_reaction_clear(self):
        t, _, ctx = _make_transport(chat_id=555, message_id=42)
        await t.set_reaction(None)
        ctx.bot.set_message_reaction.assert_awaited_once_with(
            chat_id=555, message_id=42, reaction=[]
        )

    async def test_set_reaction_swallows_exception(self):
        t, _, ctx = _make_transport()
        ctx.bot.set_message_reaction.side_effect = RuntimeError("API error")
        # Should not raise
        await t.set_reaction("\U0001f44d")


# ============================================================
# File downloads
# ============================================================


class TestDownloads:
    async def test_download_photo_no_message(self):
        t, _, _ = _make_transport(no_message=True)
        assert await t.download_photo() is None

    async def test_download_photo_no_photos(self):
        t, _, _ = _make_transport(has_photo=False)
        assert await t.download_photo() is None

    async def test_download_photo_success(self, tmp_path):
        t, update, _ = _make_transport(
            has_photo=True,
            message_id=10,
            bot_data={"session_manager": MagicMock()},
        )
        # Setup: session with cwd
        sm = t.session_manager
        session = MagicMock()
        session.cwd = str(tmp_path)
        sm.current = session

        # Setup: photo file mock
        photo_file = AsyncMock()
        photo_file.file_path = "photos/image.png"
        photo_file.download_to_drive = AsyncMock()
        largest_photo = update.message.photo[-1]
        largest_photo.get_file = AsyncMock(return_value=photo_file)

        result = await t.download_photo()
        assert result == tmp_path / "photo_10.png"
        photo_file.download_to_drive.assert_awaited_once_with(
            str(tmp_path / "photo_10.png")
        )

    async def test_download_photo_no_file_path_defaults_jpg(self, tmp_path):
        t, update, _ = _make_transport(
            has_photo=True,
            message_id=5,
            bot_data={"session_manager": MagicMock()},
        )
        sm = t.session_manager
        session = MagicMock()
        session.cwd = str(tmp_path)
        sm.current = session

        photo_file = AsyncMock()
        photo_file.file_path = None  # no file_path
        photo_file.download_to_drive = AsyncMock()
        update.message.photo[-1].get_file = AsyncMock(return_value=photo_file)

        result = await t.download_photo()
        assert result == tmp_path / "photo_5.jpg"

    async def test_download_photo_no_session_uses_home(self):
        t, update, _ = _make_transport(
            has_photo=True,
            message_id=1,
            bot_data={"session_manager": MagicMock()},
        )
        sm = t.session_manager
        sm.current = None

        photo_file = AsyncMock()
        photo_file.file_path = "img.jpg"
        photo_file.download_to_drive = AsyncMock()
        update.message.photo[-1].get_file = AsyncMock(return_value=photo_file)

        result = await t.download_photo()
        assert result == Path.home() / "photo_1.jpg"

    async def test_download_document_no_message(self):
        t, _, _ = _make_transport(no_message=True)
        assert await t.download_document() is None

    async def test_download_document_no_document(self):
        t, _, _ = _make_transport(has_document=False)
        assert await t.download_document() is None

    async def test_download_document_success(self, tmp_path):
        t, update, _ = _make_transport(
            has_document=True,
            message_id=20,
            bot_data={"session_manager": MagicMock()},
        )
        sm = t.session_manager
        session = MagicMock()
        session.cwd = str(tmp_path)
        sm.current = session

        doc = update.message.document
        doc.file_name = "report.pdf"
        doc_file = AsyncMock()
        doc_file.download_to_drive = AsyncMock()
        doc.get_file = AsyncMock(return_value=doc_file)

        result = await t.download_document()
        assert result == (tmp_path / "report.pdf", "report.pdf")
        doc_file.download_to_drive.assert_awaited_once_with(
            str(tmp_path / "report.pdf")
        )

    async def test_download_document_no_filename(self, tmp_path):
        t, update, _ = _make_transport(
            has_document=True,
            message_id=20,
            bot_data={"session_manager": MagicMock()},
        )
        sm = t.session_manager
        session = MagicMock()
        session.cwd = str(tmp_path)
        sm.current = session

        doc = update.message.document
        doc.file_name = None
        doc_file = AsyncMock()
        doc_file.download_to_drive = AsyncMock()
        doc.get_file = AsyncMock(return_value=doc_file)

        result = await t.download_document()
        assert result == (tmp_path / "document_20", "document_20")

    async def test_download_document_no_session_uses_home(self):
        t, update, _ = _make_transport(
            has_document=True,
            message_id=3,
            bot_data={"session_manager": MagicMock()},
        )
        sm = t.session_manager
        sm.current = None

        doc = update.message.document
        doc.file_name = "file.txt"
        doc_file = AsyncMock()
        doc_file.download_to_drive = AsyncMock()
        doc.get_file = AsyncMock(return_value=doc_file)

        result = await t.download_document()
        assert result == (Path.home() / "file.txt", "file.txt")

    async def test_download_voice_no_message(self):
        t, _, _ = _make_transport(no_message=True)
        assert await t.download_voice() is None

    async def test_download_voice_no_voice(self):
        t, _, _ = _make_transport(has_voice=False)
        assert await t.download_voice() is None

    async def test_download_voice_success(self):
        t, update, _ = _make_transport(has_voice=True)
        voice_file = AsyncMock()
        voice_file.download_to_drive = AsyncMock()
        update.message.voice.get_file = AsyncMock(return_value=voice_file)

        result = await t.download_voice()
        assert result is not None
        assert str(result).endswith(".ogg")
        voice_file.download_to_drive.assert_awaited_once()


# ============================================================
# telegram_handler wrapper
# ============================================================


class TestTelegramHandler:
    async def test_wraps_handler(self):
        called_with = {}

        async def my_handler(ctx):
            called_with["ctx"] = ctx

        wrapped = telegram_handler(my_handler)
        update = _make_update()
        context = _make_context()
        await wrapped(update, context)

        assert isinstance(called_with["ctx"], TelegramTransport)

    async def test_preserves_function_name(self):
        async def cmd_start(ctx):
            pass

        wrapped = telegram_handler(cmd_start)
        assert wrapped.__name__ == "cmd_start"
