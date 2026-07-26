from hotspot.pipeline.elo import EloRanker, expected_score, update_elo


def test_expected_score_equal_ratings():
    e = expected_score(1000, 1000)
    assert abs(e - 0.5) < 1e-9


def test_expected_score_higher_rating_favored():
    e = expected_score(1400, 1000)
    assert e > 0.9


def test_update_elo_winner_gains_loser_loses():
    ra, rb = update_elo(1000, 1000, a_wins=True, k=32)
    assert ra > 1000
    assert rb < 1000
    assert ra + rb == 2000


def test_update_elo_upset_bigger_change():
    ra_win, _ = update_elo(1000, 1400, a_wins=True, k=32)
    ra_lose, _ = update_elo(1400, 1000, a_wins=True, k=32)
    gain_upset = ra_win - 1000
    gain_expected = ra_lose - 1400
    assert gain_upset > gain_expected


def test_ranker_initialization():
    r = EloRanker(initial=1000, k=32, band=200)
    r.add("a")
    r.add("b")
    assert r.get_elo("a") == 1000
    assert r.get_elo("b") == 1000


def test_ranker_record_match():
    r = EloRanker(initial=1000, k=32, band=200)
    r.add("a")
    r.add("b")
    r.record_match("a", "b", winner="a")
    assert r.get_elo("a") > 1000
    assert r.get_elo("b") < 1000


def test_ranker_top_n():
    r = EloRanker(initial=1000, k=32, band=200)
    for x in ["a", "b", "c"]:
        r.add(x)
    r.record_match("a", "b", winner="a")
    r.record_match("a", "c", winner="a")
    top = r.top_n(2)
    assert top[0][0] == "a"
    assert top[0][1] > 1000


def test_ranker_pick_opponents_returns_two_distinct():
    r = EloRanker(initial=1000, k=32, band=200)
    r.add("a")
    r.add("b")
    r.set_elo("a", 1100)
    r.set_elo("b", 1500)
    a, b = r.pick_opponents()
    assert a is not None
    assert b is not None
    assert a != b
