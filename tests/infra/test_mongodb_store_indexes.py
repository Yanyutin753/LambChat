from langgraph.store.base import PutOp

from src.infra.storage import mongodb_store as store_module


def test_setup_removes_legacy_key_only_unique_index_before_compound_index(
    monkeypatch,
) -> None:
    class FakeCollection:
        def __init__(self) -> None:
            self.dropped: list[str] = []
            self.created: list[tuple[object, dict]] = []

        def index_information(self):
            return {
                "_id_": {"key": [("_id", 1)], "unique": True},
                "key_1": {"key": [("key", 1)], "unique": True},
                "store_namespace_idx": {"key": [("namespace", 1)]},
            }

        def drop_index(self, name: str) -> None:
            self.dropped.append(name)

        def create_index(self, keys, **kwargs):
            self.created.append((keys, kwargs))

    collection = FakeCollection()

    class FakeDatabase:
        def __getitem__(self, name):
            return collection

    class FakeDelegate:
        def __getitem__(self, name):
            return FakeDatabase()

    class FakeClient:
        delegate = FakeDelegate()

    fake_client = FakeClient()
    monkeypatch.setattr(store_module, "get_mongo_client", lambda: fake_client)
    store_module.MongoDBStore()._create_indexes_sync()

    assert collection.dropped == ["key_1"]
    assert any(
        keys == [("namespace", 1), ("key", 1)] and kwargs["unique"] is True
        for keys, kwargs in collection.created
    )


def test_repeated_put_updates_existing_namespace_key() -> None:
    class FakeCollection:
        def __init__(self) -> None:
            self.docs: dict[tuple[tuple[str, ...], str], dict] = {}

        def update_one(self, filter_, update, upsert):
            identity = (tuple(filter_["namespace"]), filter_["key"])
            doc = self.docs.setdefault(
                identity, {"namespace": filter_["namespace"], "key": filter_["key"]}
            )
            doc.update(update["$set"])

    class FakeDatabase:
        def __getitem__(self, name):
            return collection

    class FakeDelegate:
        def __getitem__(self, name):
            return FakeDatabase()

    class FakeClient:
        delegate = FakeDelegate()

    collection = FakeCollection()
    store = store_module.MongoDBStore(client=FakeClient())
    store.batch(
        [
            PutOp(("assistant", "workflow"), "/file.txt", {"content": "first"}),
            PutOp(("assistant", "workflow"), "/file.txt", {"content": "second"}),
        ]
    )

    assert len(collection.docs) == 1
    assert next(iter(collection.docs.values()))["value"]["content"] == "second"
