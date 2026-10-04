from mockan.gateway.snapshot_service import Backoff


def test_backoff_doubles_up_to_the_cap_and_resets() -> None:
    backoff = Backoff(initial=0.5, maximum=30)
    assert [backoff.next() for _ in range(9)] == [0.5, 1, 2, 4, 8, 16, 30, 30, 30]
    backoff.reset()
    assert backoff.next() == 0.5
