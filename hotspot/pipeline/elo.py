import random


def expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def update_elo(rating_a: float, rating_b: float, a_wins: bool, k: int = 32) -> tuple[float, float]:
    e_a = expected_score(rating_a, rating_b)
    e_b = 1.0 - e_a
    s_a = 1.0 if a_wins else 0.0
    s_b = 1.0 - s_a
    new_a = rating_a + k * (s_a - e_a)
    new_b = rating_b + k * (s_b - e_b)
    return new_a, new_b


class EloRanker:
    def __init__(self, initial: int = 1000, k: int = 32, band: int = 200):
        self.initial = initial
        self.k = k
        self.band = band
        self._ratings: dict[str, float] = {}

    def add(self, item_id: str) -> None:
        self._ratings.setdefault(item_id, float(self.initial))

    def set_elo(self, item_id: str, elo: float) -> None:
        self._ratings[item_id] = float(elo)

    def get_elo(self, item_id: str) -> float:
        return self._ratings.get(item_id, float(self.initial))

    def record_match(self, a: str, b: str, winner: str) -> None:
        ra = self.get_elo(a)
        rb = self.get_elo(b)
        a_wins = winner == a
        new_a, new_b = update_elo(ra, rb, a_wins=a_wins, k=self.k)
        self._ratings[a] = new_a
        self._ratings[b] = new_b

    def top_n(self, n: int) -> list[tuple[str, float]]:
        return sorted(self._ratings.items(), key=lambda x: x[1], reverse=True)[:n]

    def all_ratings(self) -> dict[str, float]:
        return dict(self._ratings)

    def pick_opponents(self) -> tuple[str, str | None]:
        ids = list(self._ratings.keys())
        if len(ids) < 2:
            return (ids[0] if ids else "", None)
        first = random.choice(ids)
        first_elo = self._ratings[first]
        candidates = [
            x for x in ids
            if x != first and abs(self._ratings[x] - first_elo) <= self.band
        ]
        if not candidates:
            candidates = [x for x in ids if x != first]
        second = random.choice(candidates)
        return first, second
