"""The workshop materials, checked against the thing they describe.

Documentation that has drifted is worse than none: someone follows it, it does not work, and now
they distrust everything else too. The handout in particular is what attendees will have in front
of them while the room is busy, so a wrong endpoint there costs real time.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
NOTEBOOK_DIR = ROOT / "notebooks"

HANDOUT = DOCS / "handout.md"
RUN_SHEET = DOCS / "run-sheet.md"
SLIDES = DOCS / "slides-outline.md"


@pytest.fixture(scope="module")
def api_paths():
    """Every path the emulator actually serves, from its own OpenAPI document."""
    from maprt_emulator.app import create_app
    from maprt_emulator.settings import EmulatorSettings
    return set(create_app(EmulatorSettings(token="t")).openapi()["paths"])


def documented_endpoints(text):
    """The `/integration/...` paths a document mentions, normalised to the OpenAPI spelling."""
    found = set()
    for raw in re.findall(r"/integration/[A-Za-z{}/_]+", text):
        path = raw.rstrip("/`.,")
        # The docs use the wire's parameter names; OpenAPI uses the handler's.
        path = path.replace("{patientId}", "{patient_id}")
        path = path.replace("{surfaceId}", "{surface_id}")
        path = path.replace("{machineName}", "{machine_name}")
        found.add(path)
    return found


class TestTheFilesExist:
    @pytest.mark.parametrize("path", [HANDOUT, RUN_SHEET, SLIDES], ids=lambda p: p.name)
    def test_present_and_not_empty(self, path):
        assert path.is_file() and path.stat().st_size > 1000


class TestTheHandoutMatchesTheAPI:
    def test_every_endpoint_it_lists_exists(self, api_paths):
        """A handout naming an endpoint the appliance does not serve wastes someone's morning."""
        for path in documented_endpoints(HANDOUT.read_text()):
            assert path in api_paths, f"the handout documents {path}, which is not served"

    def test_it_lists_all_seven(self, api_paths):
        documented = documented_endpoints(HANDOUT.read_text())
        official = {p for p in api_paths
                    if p.startswith("/integration") and "BeamTransitions" not in p}
        missing = official - documented
        assert not missing, f"the handout omits: {sorted(missing)}"

    def test_it_does_not_present_the_unofficial_route_as_real(self):
        # GetMapAndBeamTransitions has no documented REST route. Putting it on a one-page
        # reference beside the seven real ones would be actively misleading.
        assert "GetMapAndBeamTransitions" not in HANDOUT.read_text()

    def test_it_does_not_document_the_emulator_only_routes(self):
        # /emulator is this project's invention; nothing there transfers to an appliance.
        assert "/emulator/" not in HANDOUT.read_text()

    def test_the_envelope_keys_match_what_the_code_emits(self):
        from maprt_emulator import envelope
        for key in envelope.ok("x"):
            assert key in HANDOUT.read_text(), f"the envelope key {key!r} is not on the handout"

    def test_it_states_the_units(self):
        # Out by a factor of ten is the most likely mistake anyone makes.
        text = HANDOUT.read_text()
        assert "MILLIMETRES" in text or "millimetres" in text.lower()

    def test_it_carries_the_not_a_medical_device_notice(self):
        assert "not a medical device" in HANDOUT.read_text().lower()

    def test_it_names_the_error_code_types_the_code_uses(self):
        from maprt_emulator import envelope
        text = HANDOUT.read_text()
        for error_type in (envelope.AUTH, envelope.LICENSE):
            assert error_type in text

    def test_it_does_not_quote_an_invented_error_code_as_real(self):
        # Codes this project made up to fill gaps in the specification must not appear on a
        # reference card people will match on in production.
        from maprt_emulator import envelope
        text = HANDOUT.read_text()
        for code in envelope.INVENTED_CODES:
            assert code not in text, f"{code} is the emulator's invention, not MapRT's"


class TestTheRunSheet:
    def test_every_notebook_it_refers_to_exists(self):
        numbers = set(re.findall(r"(?m)^\| (\d\d) \|", RUN_SHEET.read_text()))
        available = {p.name[:2] for p in NOTEBOOK_DIR.glob("*.ipynb")}
        assert numbers <= available, f"refers to notebooks that do not exist: {numbers - available}"

    def test_the_timings_add_up_to_the_session_it_claims(self):
        text = RUN_SHEET.read_text()
        minutes = [int(m) for m in re.findall(r"\| (\d+) \| \d:\d\d \|", text)]
        assert sum(minutes) == 195, f"the schedule totals {sum(minutes)} minutes"
        assert "3 h 15 m" in text or "3:15" in text

    def test_it_names_the_failures_the_code_actually_produces(self):
        # Each row of the "where people get stuck" table should match a real message.
        text = RUN_SHEET.read_text()
        for symptom in ("Address already in use", "EmulatorNotRunning",
                        "nodename nor servname provided", "NO_PROXY"):
            assert symptom in text, f"the run-sheet does not cover {symptom!r}"

    def test_it_tells_the_facilitator_to_pre_warm_binder(self):
        # The single most impactful thing on the list; a cold build eats the first 15 minutes.
        text = RUN_SHEET.read_text()
        assert "the day before" in text.lower()
        assert "5–15 minutes" in text or "5-15 minutes" in text


class TestTheSlides:
    def test_the_endpoint_table_matches_the_api(self, api_paths):
        for path in documented_endpoints(SLIDES.read_text()):
            assert path in api_paths, f"the slides show {path}, which is not served"

    def test_the_geometry_slide_matches_the_model(self):
        # If mapgen's geometry ever changes, this slide becomes a confident lie delivered to a
        # room of physicists.
        from maprt_emulator import mapgen
        slide = SLIDES.read_text()
        source = Path(mapgen.__file__).read_text()

        # The slide claims three expressions; the model had better compute them.
        assert "sin(gantry) · sin(couch)" in slide
        assert "sin(gantry) · cos(couch)" in slide
        assert "R · cos(gantry)" in slide
        assert "distance * sin_g * np.sin(c)" in source
        assert "distance * sin_g * np.cos(c)" in source
        assert "distance * np.cos(g)" in source

    def test_it_ends_on_the_teaching_emulator_caveat(self):
        assert "teaching emulator" in SLIDES.read_text().lower()


class TestCrossLinks:
    @pytest.mark.parametrize("doc", [HANDOUT, RUN_SHEET, SLIDES], ids=lambda p: p.name)
    def test_every_relative_link_resolves(self, doc):
        for target in re.findall(r"\]\((?!https?://)([^)#]+)\)", doc.read_text()):
            assert (doc.parent / target).exists(), f"{doc.name} links to a missing {target}"

    def test_the_readme_points_at_the_materials(self):
        readme = (ROOT / "README.md").read_text()
        for doc in (HANDOUT, RUN_SHEET, SLIDES):
            assert f"docs/{doc.name}" in readme, f"the README does not link {doc.name}"

    def test_every_document_names_the_same_repository(self):
        """One stale URL on a handout sends a room to a 404."""
        urls = set()
        for doc in (HANDOUT, RUN_SHEET, SLIDES, ROOT / "README.md"):
            urls.update(re.findall(r"github\.com/[\w.-]+/[\w.-]+", doc.read_text()))
        assert len(urls) == 1, f"the documents disagree about the repository: {sorted(urls)}"
        assert "REPLACE-ME" not in str(urls)
