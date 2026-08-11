from app.services.matching.candidate_matcher import MatchInput, match_row


class FakeCandidate:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.external_candidate_id = kwargs.get("external_candidate_id", "C1")
        self.start_id = kwargs.get("start_id")
        self.candidate_name = kwargs.get("candidate_name", "Jane Doe")
        self.normalized_name = kwargs.get("normalized_name", "jane doe")
        self.client = kwargs.get("client", "Acme")
        self.normalized_client = kwargs.get("normalized_client", "acme")


def test_match_by_candidate_id():
    c = FakeCandidate()
    out = match_row(MatchInput(candidate_id="C1", candidate_name="Other"), [c])
    assert out.match_method == "CANDIDATE_ID"
    assert out.match_result == "MATCHED"
    assert out.confidence == "HIGH"


def test_match_by_name_client():
    c = FakeCandidate()
    out = match_row(MatchInput(candidate_name="Jane Doe", client="Acme"), [c])
    assert out.match_method == "NAME_CLIENT"
    assert out.match_result == "MATCHED"


def test_unmatched():
    c = FakeCandidate()
    out = match_row(MatchInput(candidate_name="Nobody", client="X"), [c])
    assert out.match_result == "UNMATCHED"
