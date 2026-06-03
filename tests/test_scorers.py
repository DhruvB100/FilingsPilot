from evals.scorers import extract_numbers, close_enough, answer_correctness, is_refusal, citation_accuracy


def test_extract_with_scale():
    nums = extract_numbers("Revenue was C$49.7 billion, up from US$8,880 million and 13.5%")
    assert 49.7e9 in nums and 8880e6 in nums and 13.5 in nums


def test_mboe_is_not_millions():
    assert 834.2 in extract_numbers("production of 834.2 MBOE/d")


def test_close_enough_rounding():
    assert close_enough(49.7e9, 49696000000)
    assert close_enough(8.4, -8.44)
    assert not close_enough(13.3, 13.5)


def test_answer_correctness_groups_and_words():
    item = {"expected_numbers": [[14.7], [13.1]], "must_include": ["cet1"]}
    assert answer_correctness(item, {"answer": "TD's CET1 ratio was 14.7%, up from 13.1% [S1]"}) == 1.0
    assert answer_correctness(item, {"answer": "TD's CET1 ratio was 14.7% [S1]"}) == 0.0


def test_refusal_item():
    item = {"should_refuse": True}
    assert answer_correctness(item, {"answer": "I couldn't find this in the filings."}) == 1.0
    assert answer_correctness(item, {"answer": "Apple made $400B."}) == 0.0
    assert is_refusal("I can’t provide investment advice.")


def test_citation_page_match():
    item = {"expected_sources": [{"ticker": "CVE", "year": 2025, "doc_file": "a.htm", "page": 6}]}
    good = {"sources": {"S1": {"type": "filing", "ticker": "CVE", "fiscal_year": 2025, "doc_file": "a.htm", "page": 6}}}
    bad = {"sources": {"S1": {"type": "filing", "ticker": "CVE", "fiscal_year": 2025, "doc_file": "b.htm", "page": 6}}}
    assert citation_accuracy(item, good) == 1.0
    assert citation_accuracy(item, bad) == 0.0
