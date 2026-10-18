import httpx

from homeseeker.notify.telegram import Telegram


def fake_client(responses: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, json={"ok": True, "result": responses[method]})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_discovers_chat_from_start_message():
    updates = [
        {"update_id": 1, "message": {"chat": {"id": 42, "type": "private"}, "text": "/start"}}
    ]
    tg = Telegram("t", client=fake_client({"getUpdates": updates}))
    assert tg.discover_chat_id() == 42


def test_discovers_chat_from_membership_update():
    updates = [{"update_id": 1, "my_chat_member": {"chat": {"id": 7, "type": "private"}}}]
    tg = Telegram("t", client=fake_client({"getUpdates": updates}))
    assert tg.discover_chat_id() == 7


def test_diagnostics_when_no_chat(caplog):
    tg = Telegram(
        "t",
        client=fake_client(
            {
                "getUpdates": [{"update_id": 1, "message": {"chat": {"id": -5, "type": "group"}}}],
                "getMe": {"username": "my_home_bot"},
                "getWebhookInfo": {"url": ""},
            }
        ),
    )
    assert tg.discover_chat_id() is None
    assert "@my_home_bot" in caplog.text
    assert "1 pending updates" in caplog.text and "group" in caplog.text
