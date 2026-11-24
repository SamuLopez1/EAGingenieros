"""El catálogo de grabación descubre un ID nuevo en una consulta posterior."""
from pathlib import Path

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base
from app.db.repository import SqlOpportunityRepository
from app.secop.client import HttpxClient


def test_recording_refresh_discovers_new_id_and_does_not_duplicate(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3] / "scripts"))
    from liciscope_recording import refresh_catalog

    rows = [{"id_del_proceso": "CO1.REQ.FIXTURE-A"}]

    def reply(self, url, *, params, timeout):
        assert url.endswith("/p6dx-8zbt.json")
        assert "estado_del_procedimiento = 'Publicado'" in params["$where"]
        assert "fecha_de_recepcion_de > " in params["$where"]
        assert params["$order"] == "id_del_proceso ASC, :id ASC"
        assert params["$limit"] == 750 and params["$offset"] == 0
        return httpx.Response(200, json=rows)

    monkeypatch.setattr(HttpxClient, "get", reply)
    engine = create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(engine)
        factory = sessionmaker(engine, expire_on_commit=False)
        first = refresh_catalog(factory, trigger="inicial")
        assert first.outcome == "completed" and first.records_created == 1
        rows.append({"id_del_proceso": "CO1.REQ.FIXTURE-B"})
        second = refresh_catalog(factory)
        assert second.outcome == "completed" and second.records_created == 1
        third = refresh_catalog(factory)
        assert third.outcome == "completed" and third.records_created == 0
        with factory() as session:
            repo = SqlOpportunityRepository(session)
            assert repo.count() == 2
            assert repo.get_by_source("p6dx-8zbt", "CO1.REQ.FIXTURE-B") is not None
    finally:
        engine.dispose()
