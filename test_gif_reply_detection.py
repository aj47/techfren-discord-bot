from types import SimpleNamespace

from gif_utils import is_forward_reference, should_check_gif_reference


def test_text_reply_to_gif_ancestor_is_not_treated_as_gif():
    reply = SimpleNamespace(type=19, reference=SimpleNamespace(type=0))

    assert should_check_gif_reference(reply) is False


def test_native_forward_checks_referenced_message():
    forward = SimpleNamespace(type=0, reference=SimpleNamespace(type=1))

    assert is_forward_reference(forward) is True
    assert should_check_gif_reference(forward) is True


def test_non_reply_reference_does_not_walk_chain():
    reference = SimpleNamespace(type=0)
    non_reply = SimpleNamespace(type=0, reference=reference)

    assert should_check_gif_reference(non_reply) is False


def test_message_without_reference_does_not_check_chain():
    message = SimpleNamespace(type=0, reference=None)

    assert should_check_gif_reference(message) is False
