from app.services.keyword_service import KeywordService


def test_extract_related_query_rows_preserves_value_labels():
    payloads = [
        {
            "keyword": "image",
            "payload": {
                "default": {
                    "rankedList": [
                        {"rankedKeyword": []},
                        {
                            "rankedKeyword": [
                                {"query": "trump jesus image", "value": "Breakout"},
                                {"query": "allbirds ai", "value": 4500},
                            ]
                        },
                    ]
                }
            },
        }
    ]

    rows = KeywordService.extract_related_query_rows(payloads)

    assert rows == [
        {
            "source_keyword": "image",
            "query": "trump jesus image",
            "value_label": "Breakout",
            "is_breakout": True,
        },
        {
            "source_keyword": "image",
            "query": "allbirds ai",
            "value_label": "+4500%",
            "is_breakout": False,
        },
    ]
