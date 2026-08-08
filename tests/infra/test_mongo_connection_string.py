"""Tests for the shared MongoDB connection-string builder.

These cover every branch of the helper that ``get_mongo_client`` previously
inlined, including the credential and ``mongodb+srv://`` branches that the
existing client test does not exercise.
"""

from urllib.parse import quote_plus

from src.infra.storage import mongodb


def _set_conn_settings(monkeypatch, **overrides):
    defaults = {
        "MONGODB_URL": "mongodb://localhost:27017",
        "MONGODB_USERNAME": "",
        "MONGODB_PASSWORD": "",
        "MONGODB_AUTH_SOURCE": "admin",
    }
    defaults.update(overrides)
    for key, value in defaults.items():
        monkeypatch.setattr(mongodb.settings, key, value)


def test_plain_url_without_credentials(monkeypatch):
    _set_conn_settings(monkeypatch, MONGODB_URL="mongodb://localhost:27017")

    assert mongodb.build_mongo_connection_string() == "mongodb://localhost:27017"


def test_plain_url_with_credentials(monkeypatch):
    _set_conn_settings(
        monkeypatch,
        MONGODB_URL="mongodb://host:27017/db",
        MONGODB_USERNAME="u@ser",
        MONGODB_PASSWORD="p@ss/word",
        MONGODB_AUTH_SOURCE="mydb",
    )

    expected = (
        f"mongodb://{quote_plus('u@ser')}:{quote_plus('p@ss/word')}@host:27017/db?authSource=mydb"
    )
    assert mongodb.build_mongo_connection_string() == expected


def test_srv_url_with_credentials(monkeypatch):
    _set_conn_settings(
        monkeypatch,
        MONGODB_URL="mongodb+srv://cluster.example.net/db",
        MONGODB_USERNAME="user",
        MONGODB_PASSWORD="pass",
        MONGODB_AUTH_SOURCE="admin",
    )

    expected = (
        f"mongodb+srv://{quote_plus('user')}:{quote_plus('pass')}@cluster.example.net/db"
        f"?authSource=admin"
    )
    assert mongodb.build_mongo_connection_string() == expected


def test_only_username_present_falls_back_to_plain_url(monkeypatch):
    _set_conn_settings(
        monkeypatch,
        MONGODB_URL="mongodb://localhost:27017",
        MONGODB_USERNAME="user",
        MONGODB_PASSWORD="",
    )

    assert mongodb.build_mongo_connection_string() == "mongodb://localhost:27017"


def test_url_without_known_scheme_passthrough(monkeypatch):
    _set_conn_settings(
        monkeypatch,
        MONGODB_URL="mongodb+custom://example/db",
        MONGODB_USERNAME="user",
        MONGODB_PASSWORD="pass",
    )

    assert mongodb.build_mongo_connection_string() == "mongodb+custom://example/db"
