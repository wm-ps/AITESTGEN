from explorer_worker.hunt import emptied


def test_emptied_removes_records_but_keeps_shape():
    assert emptied([{"id": 1}]) == []
    page = {"content": [{"id": 1}], "totalElements": 7, "number": 0, "meta": {"items": [1, 2]}}
    assert emptied(page) == {"content": [], "totalElements": 0, "number": 0, "meta": {"items": []}}
    assert emptied("plain") == "plain"


def test_switched_on_flips_only_feature_switches():
    from explorer_worker.hunt import switched_on

    data = {"newCheckoutEnabled": False, "isDeleted": False, "items": [{"betaFeature": False}]}
    changed, flipped = switched_on(data)
    assert flipped == 2
    assert changed["newCheckoutEnabled"] is True and changed["isDeleted"] is False
    assert changed["items"][0]["betaFeature"] is True
