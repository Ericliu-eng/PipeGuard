from pipeguard.database import _engine_kwargs


def test_sqlite_url_allows_cross_thread_access() -> None:
    assert _engine_kwargs("sqlite:///./pipeguard.db") == {
        "connect_args": {"check_same_thread": False}
    }


def test_postgres_url_validates_pooled_connections() -> None:
    kwargs = _engine_kwargs("postgresql://user:pass@host:5432/pipeguard")

    assert kwargs["pool_pre_ping"] is True
    assert kwargs["pool_recycle"] == 300
