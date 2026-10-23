"""Small helpers for Streamlit AppTest tests: open a page and find widgets by their visible label."""
import pathlib

from streamlit.testing.v1 import AppTest

MAIN_PY = pathlib.Path(__file__).resolve().parent.parent / "main.py"


def run_main():
    """Run main.py once without navigating or asserting (for start-up failure tests)."""
    return AppTest.from_file(str(MAIN_PY), default_timeout=30).run()


def open_app(section="Jobs"):
    """Run main.py headlessly (against the test database) and switch to the given sidebar section."""
    at = AppTest.from_file(str(MAIN_PY), default_timeout=30)
    at.run()
    if section != "Jobs":
        at.sidebar.radio[0].set_value(section).run()
    assert not at.exception, at.exception
    return at


def by_label(widgets, label):
    """Return the single widget in `widgets` whose label is exactly `label`."""
    matches = [w for w in widgets if w.label == label]
    assert len(matches) == 1, f"expected one widget labelled {label!r}, found {len(matches)}"
    return matches[0]


def click(at, button_label):
    """Click a button (including form submit buttons) and rerun the script."""
    by_label(at.button, button_label).click().run()
    assert not at.exception, at.exception
    return at


def texts(elements):
    """Values of a list of Streamlit elements (e.g. at.success, at.error, at.info, at.text)."""
    return [e.value for e in elements]


def contains(elements, fragment):
    return any(fragment in value for value in texts(elements))
