"""Tests for SM-2 spaced-repetition coding and study cards."""

from selene.study_cards import StudyCardStore, compute_sm2


def test_compute_sm2_ratings_and_ease_floor():
    # Initial review: reps=0 -> reps=1, interval=1.0
    ease1, int1, reps1 = compute_sm2(ease_factor=2.5, interval_days=1.0, repetitions=0, quality=4)
    assert reps1 == 1
    assert int1 == 1.0
    assert ease1 == 2.5

    # Second review good: reps=1 -> reps=2, interval=6.0
    ease2, int2, reps2 = compute_sm2(ease_factor=ease1, interval_days=int1, repetitions=reps1, quality=4)
    assert reps2 == 2
    assert int2 == 6.0

    # Third review easy (quality=5): interval = round(6.0 * ease2, 2), ease increases
    ease3, int3, reps3 = compute_sm2(ease_factor=ease2, interval_days=int2, repetitions=reps2, quality=5)
    assert reps3 == 3
    assert int3 == round(6.0 * ease2, 2)
    assert ease3 > ease2

    # Failing review (quality=1 / again): reps reset to 0, interval resets to 1.0, ease drops
    ease4, int4, reps4 = compute_sm2(ease_factor=ease3, interval_days=int3, repetitions=reps3, quality=1)
    assert reps4 == 0
    assert int4 == 1.0
    assert ease4 < ease3

    # Ease factor never drops below 1.3
    low_ease, _, _ = compute_sm2(ease_factor=1.35, interval_days=1.0, repetitions=0, quality=0)
    assert low_ease == 1.3


def test_study_card_crud_and_due_flow(study_cards: StudyCardStore):
    assert study_cards.total_count() == 0
    assert study_cards.due_count() == 0

    res = study_cards.add_card(
        topic="Python",
        question="What is the GIL?",
        answer="Global Interpreter Lock preventing multi-thread CPU concurrency.",
    )
    assert "Logged study card #1" in res
    assert study_cards.total_count() == 1
    assert study_cards.due_count() == 1

    due = study_cards.due_cards()
    assert len(due) == 1
    assert due[0]["id"] == 1
    assert due[0]["topic"] == "Python"
    assert "GIL" in due[0]["question"]

    summary = study_cards.format_due_summary()
    assert "1 shown of 1 due / 1 total" in summary

    # Successful review pushes due_at into the future
    rev_msg = study_cards.review_card(1, "good")
    assert "Reviewed card #1" in rev_msg
    assert "next review in 1 day(s)" in rev_msg
    assert study_cards.due_count() == 0

    # Invalid rating rejected
    bad_rating = study_cards.review_card(1, "amazing")
    assert "Invalid rating" in bad_rating

    # Missing card id
    missing = study_cards.review_card(999, "good")
    assert "No study card found with ID #999" in missing


def test_add_card_validation(study_cards: StudyCardStore):
    err = study_cards.add_card("Topic", "", "Answer")
    assert "Both a question and answer are required" in err

    err2 = study_cards.add_card("Topic", "Question", "   ")
    assert "Both a question and answer are required" in err2
