import pytest
from pytest_httpx import HTTPXMock

from homefinance.sources.ynab.client import YNABAuthError, YNABClient, YNABClientError


def _client() -> YNABClient:
    return YNABClient(token="TEST-TOKEN", base_url="https://api.ynab.com/v1")


def test_get_user_sends_bearer_token(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://api.ynab.com/v1/user",
        json={"data": {"user": {"id": "u-1"}}},
    )
    resp = _client().get_user()
    assert resp.data.user.id == "u-1"
    sent = httpx_mock.get_requests()[0]
    assert sent.headers["Authorization"] == "Bearer TEST-TOKEN"


def test_401_raises_auth_error(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://api.ynab.com/v1/user",
        status_code=401,
        json={"error": {"id": "401", "name": "unauthorized", "detail": "bad token"}},
    )
    with pytest.raises(YNABAuthError):
        _client().get_user()


def test_get_transactions_passes_cursor(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://api.ynab.com/v1/budgets/B/transactions?last_knowledge_of_server=42",
        json={"data": {"server_knowledge": 99, "transactions": []}},
    )
    resp = _client().get_transactions(budget_id="B", cursor=42)
    assert resp.data.server_knowledge == 99
    assert resp.data.transactions == []


def test_5xx_is_retried_then_succeeds(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="https://api.ynab.com/v1/user", status_code=503)
    httpx_mock.add_response(
        url="https://api.ynab.com/v1/user",
        json={"data": {"user": {"id": "u-1"}}},
    )
    resp = _client().get_user()
    assert resp.data.user.id == "u-1"
    assert len(httpx_mock.get_requests()) == 2


@pytest.mark.httpx_mock(assert_all_responses_were_requested=False)
def test_persistent_5xx_raises_client_error(httpx_mock: HTTPXMock) -> None:
    for _ in range(4):
        httpx_mock.add_response(url="https://api.ynab.com/v1/user", status_code=500)
    with pytest.raises(YNABClientError):
        _client().get_user()


def test_client_has_no_write_methods() -> None:
    for attr in ("post", "put", "patch", "delete", "create_transaction", "update_transaction"):
        assert not hasattr(YNABClient, attr), f"YNABClient must not expose {attr!r}"
