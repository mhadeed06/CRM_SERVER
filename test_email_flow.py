"""
Full email flow tests — run with: python test_email_flow.py
"""
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
import time

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/")
    assert r.status_code == 200
    print("TEST 1: Health check - PASSED")


def test_send_single_email():
    payload = {
        "subject": "Test Subject",
        "html": "<h1>Hello</h1>",
        "text": "Hello",
        "from_email": "sender@example.com",
        "recipients": [
            {"to_email": "user@example.com", "thread_id": 1, "message_id": 100}
        ],
    }
    with patch(
        "app.api.v1.routes.email.send_email_bulk",
        return_value=(True, "mock-sg-id-123"),
    ):
        r = client.post("/api/v1/email/send", json=payload)
    body = r.json()
    assert r.status_code == 200
    assert body["status"] is True
    assert len(body["results"]) == 1
    assert body["results"][0]["status"] == "accepted"
    assert body["results"][0]["to_email"] == "user@example.com"
    assert body["results"][0]["thread_id"] == 1
    assert body["results"][0]["message_id"] == 100
    print("TEST 2: Send single email - PASSED")


def test_send_with_threading():
    payload = {
        "subject": "Re: Original Subject",
        "html": "<p>Reply</p>",
        "from_email": "sender@example.com",
        "recipients": [
            {
                "to_email": "user@example.com",
                "thread_id": 1,
                "message_id": 102,
                "reply_to_message_id": "<msg-100@sg.com>",
                "references": "<msg-99@sg.com>,<msg-100@sg.com>",
            }
        ],
    }
    captured = {}

    def mock_send(**kw):
        captured.update(kw)
        return (True, "mock-id")

    with patch("app.api.v1.routes.email.send_email_bulk", side_effect=mock_send):
        r = client.post("/api/v1/email/send", json=payload)
    assert r.status_code == 200
    recip = captured["recipients"][0]
    assert recip["reply_to_message_id"] == "<msg-100@sg.com>"
    assert recip["references"] == "<msg-99@sg.com>,<msg-100@sg.com>"
    print("TEST 3: Email with threading headers - PASSED")


def test_bulk_500():
    payload = {
        "subject": "Bulk Test",
        "html": "<h1>Bulk</h1>",
        "from_email": "sender@example.com",
        "recipients": [
            {
                "to_email": f"user{i}@example.com",
                "thread_id": i,
                "message_id": 1000 + i,
            }
            for i in range(500)
        ],
    }
    with patch(
        "app.api.v1.routes.email.send_email_bulk", return_value=(True, "bulk-id")
    ):
        r = client.post("/api/v1/email/send", json=payload)
    body = r.json()
    assert r.status_code == 200
    assert len(body["results"]) == 500
    assert all(res["status"] == "accepted" for res in body["results"])
    print("TEST 4: Bulk 500 recipients - PASSED")


def test_reject_over_1000():
    payload = {
        "subject": "Too many",
        "html": "<h1>X</h1>",
        "from_email": "sender@example.com",
        "recipients": [
            {
                "to_email": f"user{i}@example.com",
                "thread_id": i,
                "message_id": 2000 + i,
            }
            for i in range(1001)
        ],
    }
    with patch("app.services.email_sendgrid.CONFIG") as mock_cfg:
        mock_cfg.SENDGRID_API_KEY = "fake-key"
        r = client.post("/api/v1/email/send", json=payload)
    body = r.json()
    assert body["status"] is False
    assert "max 1000" in body["results"][0]["status"]
    print("TEST 5: Reject >1000 recipients - PASSED")


def test_error_response_matches_model():
    with patch(
        "app.api.v1.routes.email.send_email_bulk",
        side_effect=RuntimeError("SendGrid down"),
    ):
        r = client.post(
            "/api/v1/email/send",
            json={
                "subject": "Test",
                "html": "<p>X</p>",
                "from_email": "a@b.com",
                "recipients": [
                    {"to_email": "c@d.com", "thread_id": 1, "message_id": 1}
                ],
            },
        )
    assert r.status_code == 200  # not 500!
    body = r.json()
    assert body["status"] is False
    assert "error" in body["results"][0]["status"]
    print("TEST 6: Error response matches model (no 500 crash) - PASSED")


def test_validation_missing_subject():
    r = client.post(
        "/api/v1/email/send",
        json={
            "html": "<p>X</p>",
            "from_email": "a@b.com",
            "recipients": [
                {"to_email": "c@d.com", "thread_id": 1, "message_id": 1}
            ],
        },
    )
    assert r.status_code == 422
    print("TEST 7: Validation - missing subject - PASSED")


def test_validation_invalid_email():
    r = client.post(
        "/api/v1/email/send",
        json={
            "subject": "Test",
            "html": "<p>X</p>",
            "from_email": "not-an-email",
            "recipients": [
                {"to_email": "c@d.com", "thread_id": 1, "message_id": 1}
            ],
        },
    )
    assert r.status_code == 422
    print("TEST 8: Validation - invalid email format - PASSED")


def test_build_references():
    from app.services.email_sendgrid import _build_references

    # fresh email
    assert _build_references(None, None) is None
    # first reply
    assert _build_references(None, "<msg-1@sg.com>") == "<msg-1@sg.com>"
    # continuing thread
    assert (
        _build_references("<msg-1@sg.com>,<msg-2@sg.com>", "<msg-3@sg.com>")
        == "<msg-1@sg.com> <msg-2@sg.com> <msg-3@sg.com>"
    )
    # no duplicate when reply_to already in refs
    assert (
        _build_references("<msg-1@sg.com>,<msg-2@sg.com>", "<msg-2@sg.com>")
        == "<msg-1@sg.com> <msg-2@sg.com>"
    )
    print("TEST 9: _build_references threading logic - PASSED")


def test_personalization_headers():
    from app.services.email_sendgrid import send_email_bulk

    mock_response = MagicMock()
    mock_response.status_code = 202
    mock_response.headers = {"X-Message-Id": "test-bulk-id"}

    captured_payload = {}

    def capture_post(request_body):
        captured_payload.update(request_body)
        return mock_response

    with patch("app.services.email_sendgrid.CONFIG") as mock_cfg:
        mock_cfg.SENDGRID_API_KEY = "fake"
        with patch("app.services.email_sendgrid.reply_to_email", "reply@test.com"):
            with patch("app.services.email_sendgrid.SendGridAPIClient") as MockSG:
                MockSG.return_value.client.mail.send.post = capture_post
                send_email_bulk(
                    subject="Thread Test",
                    html="<p>Hi</p>",
                    text=None,
                    from_email="sender@test.com",
                    recipients=[
                        {
                            "to_email": "a@test.com",
                            "thread_id": 1,
                            "message_id": 10,
                            "reply_to_message_id": None,
                            "references": None,
                        },
                        {
                            "to_email": "b@test.com",
                            "thread_id": 2,
                            "message_id": 20,
                            "reply_to_message_id": "<original@sg.com>",
                            "references": "<root@sg.com>,<original@sg.com>",
                        },
                    ],
                )

    p = captured_payload["personalizations"]
    # First: new email, no threading headers
    assert "headers" not in p[0]
    # Second: reply, has correct headers
    assert p[1]["headers"]["In-Reply-To"] == "<original@sg.com>"
    assert p[1]["headers"]["References"] == "<root@sg.com> <original@sg.com>"
    assert captured_payload["reply_to"]["email"] == "reply@test.com"
    print("TEST 10: SendGrid personalization headers - PASSED")


def test_webhook_events_batch():
    mock_crm = AsyncMock(return_value=(200, "ok"))
    with patch(
        "app.api.v1.routes.webhooks_sendgrid.send_email_event_to_crm", mock_crm
    ):
        with patch(
            "app.api.v1.routes.webhooks_sendgrid.get_region_from_ip",
            return_value={},
        ):
            events = [
                {
                    "event": "delivered",
                    "email": f"user{i}@test.com",
                    "timestamp": 1700000000 + i,
                    "sg_message_id": f"sg-{i}",
                    "smtp-id": f"<smtp-{i}@sg.com>",
                    "ip": "1.2.3.4",
                    "custom_args": {"thread_id": i + 1, "message_id": 100 + i},
                }
                for i in range(10)
            ]
            r = client.post("/api/v1/webhooks/sendgrid/events", json=events)
    assert r.status_code == 200
    assert mock_crm.call_count == 10
    first = mock_crm.call_args_list[0][0][0]
    assert first["eventType"] == "delivered"
    assert first["threadSeqNum"] == 1
    print("TEST 11: Webhook events batch (10 events) - PASSED")


def test_webhook_500_events_load():
    mock_crm = AsyncMock(return_value=(200, "ok"))
    with patch(
        "app.api.v1.routes.webhooks_sendgrid.send_email_event_to_crm", mock_crm
    ):
        with patch(
            "app.api.v1.routes.webhooks_sendgrid.get_region_from_ip",
            return_value={},
        ):
            events = [
                {
                    "event": "delivered",
                    "email": f"user{i}@test.com",
                    "timestamp": 1700000000 + i,
                    "sg_message_id": f"sg-{i}",
                    "smtp-id": f"<smtp-{i}@sg.com>",
                    "custom_args": {"thread_id": i + 1, "message_id": 5000 + i},
                }
                for i in range(500)
            ]
            start = time.time()
            r = client.post("/api/v1/webhooks/sendgrid/events", json=events)
            elapsed = time.time() - start
    assert r.status_code == 200
    assert mock_crm.call_count == 500
    print(f"TEST 12: Webhook 500 events load test - PASSED ({elapsed:.3f}s)")


def test_webhook_skips_invalid():
    mock_crm = AsyncMock(return_value=(200, "ok"))
    with patch(
        "app.api.v1.routes.webhooks_sendgrid.send_email_event_to_crm", mock_crm
    ):
        with patch(
            "app.api.v1.routes.webhooks_sendgrid.get_region_from_ip",
            return_value={},
        ):
            r = client.post(
                "/api/v1/webhooks/sendgrid/events",
                json=[
                    # no custom_args -> skipped
                    {"event": "delivered", "email": "a@b.com", "timestamp": 1700000000},
                    # bounce not in allowed -> skipped
                    {
                        "event": "bounce",
                        "email": "x@y.com",
                        "custom_args": {"thread_id": 1, "message_id": 1},
                    },
                    # valid
                    {
                        "event": "delivered",
                        "email": "c@d.com",
                        "custom_args": {"thread_id": 5, "message_id": 50},
                        "timestamp": 1700000000,
                    },
                ],
            )
    assert r.status_code == 200
    assert mock_crm.call_count == 1
    print("TEST 13: Webhook skips invalid/irrelevant events - PASSED")


def test_webhook_bad_payload():
    r = client.post("/api/v1/webhooks/sendgrid/events", json={"not": "a list"})
    assert r.status_code == 200
    print("TEST 14: Webhook handles bad payload gracefully - PASSED")


def test_inbound_email():
    mock_inbound = AsyncMock(return_value=(200, "ok"))
    with patch(
        "app.api.v1.routes.webhooks_sendgrid.send_inbound_email_to_crm",
        mock_inbound,
    ):
        r = client.post(
            "/api/v1/webhooks/sendgrid/inbound",
            data={
                "headers": "Message-ID: <reply-123@gmail.com>\r\nIn-Reply-To: <original-456@sg.com>\r\n",
                "from": "John Doe <john@gmail.com>",
                "to": "reply@yourapp.com",
                "subject": "Re: Hello",
                "text": "Thanks for reaching out!",
                "html": "<p>Thanks for reaching out!</p>",
            },
        )
    assert r.status_code == 200
    crm = mock_inbound.call_args[0][0]
    assert crm["sendgridMessageId"] == "reply-123@gmail.com"
    assert crm["inReplyTo"] == "original-456@sg.com"
    assert crm["fromEmail"] == "john@gmail.com"
    assert crm["toEmail"] == "reply@yourapp.com"
    assert crm["subject"] == "Re: Hello"
    print("TEST 15: Inbound email webhook - PASSED")


if __name__ == "__main__":
    print("=" * 60)
    print("COMMS SERVICE - EMAIL FLOW TEST SUITE")
    print("=" * 60)
    print()

    test_health()
    test_send_single_email()
    test_send_with_threading()
    test_bulk_500()
    test_reject_over_1000()
    test_error_response_matches_model()
    test_validation_missing_subject()
    test_validation_invalid_email()
    test_build_references()
    test_personalization_headers()
    test_webhook_events_batch()
    test_webhook_500_events_load()
    test_webhook_skips_invalid()
    test_webhook_bad_payload()
    test_inbound_email()

    print()
    print("=" * 60)
    print("ALL 15 TESTS PASSED")
    print("=" * 60)
