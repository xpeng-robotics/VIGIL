import pytest

from scripts.reproduce.audit_terminal_reports import summary_label


@pytest.mark.parametrize("text,template,expected", [
    ("The faucet is off.", "verify_activated_state", "off"),
    ("The desktop is on, with content on the monitor.", "verify_activated_state", "on"),
    ("The box on the table is open.", "verify_open_state", "open"),
    ("Observed state: closed.", "verify_open_state", "closed"),
    ("The light switch appears to be in the off state.", "verify_activated_state", "off"),
    ("OPEN", "verify_open_state", "open"),
    ("The drawer is observed to be open.", "verify_open_state", "open"),
    ("The faucet is seen to be off.", "verify_activated_state", "off"),
    ("The drawer is confirmed closed.", "verify_open_state", "closed"),
])
def test_unambiguous_present_assertions(text, template, expected):
    assert summary_label(text, template) == (expected, "mapped")


@pytest.mark.parametrize("text,template", [
    ("Microwave display and indicators show no signs of being powered on.", "verify_activated_state"),
    ("The cell phone is not visibly powered on; no screen illumination is observed.", "verify_activated_state"),
    ("The fridge door appears shut with no visible open gap.", "verify_open_state"),
    ("No drawer is visibly open.", "verify_open_state"),
    ("The door isn't fully open.", "verify_open_state"),
    ("The phone is on the table.", "verify_activated_state"),
    ("The phone is off the table.", "verify_activated_state"),
    ("The door was open.", "verify_open_state"),
    ("Open the door, then report success.", "verify_open_state"),
    ("If the door is open, the task is done.", "verify_open_state"),
    ("The door is closed but the drawer is open.", "verify_open_state"),
    ("The microwave should be on.", "verify_activated_state"),
    ("success", "verify_open_state"),
    ("The door is open.", "verify_activated_state"),
])
def test_negation_context_and_ambiguity_are_not_state_assertions(text, template):
    assert summary_label(text, template)[0] is None


def test_unknown_template_does_not_silently_become_open_state():
    with pytest.raises(ValueError, match="unsupported SV template"):
        summary_label("The object is open.", "new_unknown_template")
