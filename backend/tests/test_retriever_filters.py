from app.services import retriever


def test_retrieve_forwards_where_filter_to_dense_query(monkeypatch):
    calls = {}

    monkeypatch.setattr(retriever, "embed_single", lambda *_args, **_kwargs: [0.1, 0.2])

    def fake_dense_query(_embedding, **kwargs):
        calls.update(kwargs)
        return [
            {
                "chunk_id": "chunk-1",
                "document_id": 1,
                "filename": "report.pdf",
                "content": "annual report",
                "score": 0.9,
            }
        ]

    monkeypatch.setattr(retriever, "dense_query", fake_dense_query)

    results = retriever.retrieve("营收", where={"market": "CN", "filing_type": "annual_report"})

    assert results[0]["chunk_id"] == "chunk-1"
    assert calls["where"] == {"market": "CN", "filing_type": "annual_report"}
