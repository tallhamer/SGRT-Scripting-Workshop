"""The committed data: the synthetic plan, the surfaces, and the repository's size budget.

These guard the things that break a workshop quietly — a plan referencing a patient the simulator
does not have, a surface that stopped parsing, a repo that grew until a conference-wifi clone
times out.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "data" / "plans" / "ANON001_plan.dcm"

pydicom = pytest.importorskip("pydicom")


@pytest.fixture(scope="module")
def plan():
    return pydicom.dcmread(PLAN)


class TestTheSyntheticPlan:
    def test_it_is_an_rt_plan(self, plan):
        assert plan.Modality == "RTPLAN"
        assert plan.SOPClassUID == "1.2.840.10008.5.1.4.1.1.481.5"

    def test_its_patient_exists_in_the_simulators_catalog(self, plan):
        # A plan naming a patient the simulator has never heard of makes the capstone notebook
        # fail on its second cell, which is a miserable way to start the exercise.
        import json
        patients = json.loads((ROOT / "data" / "patients.json").read_text(encoding="utf-8"))
        assert plan.PatientID in patients
        assert patients[plan.PatientID], "the plan's patient has no surfaces to map against"

    def test_its_machine_name_resolves_to_exactly_one_room(self, plan):
        # It must be a room whose machineName is *unique*, or the capstone's room lookup returns
        # DuplicateKey and the notebook teaches that lesson in the wrong place.
        import json
        rooms = json.loads((ROOT / "data" / "rooms.json").read_text(encoding="utf-8"))
        machine = plan.BeamSequence[0].TreatmentMachineName
        matches = [r for r in rooms if r["machineName"] == machine]
        assert len(matches) == 1, f"{machine} matches {len(matches)} rooms"

    def test_it_carries_the_patient_position(self, plan):
        # (0018,5100), which the GetMap body needs.
        assert plan.PatientSetupSequence[0].PatientPosition == "HFS"

    def test_every_beam_has_an_isocenter_couch_and_gantry(self, plan):
        for beam in plan.BeamSequence:
            first = beam.ControlPointSequence[0]
            assert len(first.IsocenterPosition) == 3
            assert first.PatientSupportAngle is not None
            assert first.GantryAngle is not None

    def test_it_contains_statics_an_arc_and_a_setup_field(self, plan):
        # The shapes that matter for collision work. A plan of only static beams would never
        # exercise the arc-sweep path the capstone is built around.
        delivery = {b.TreatmentDeliveryType for b in plan.BeamSequence}
        rotations = {b.ControlPointSequence[0].GantryRotationDirection for b in plan.BeamSequence}
        assert "SETUP" in delivery and "TREATMENT" in delivery
        assert rotations >= {"NONE", "CW", "CC"}

    def test_it_is_labelled_synthetic(self, plan):
        # Nobody should mistake this for a deliverable plan, least of all a planning system.
        assert "synthetic" in plan.ManufacturerModelName.lower()
        assert plan.ApprovalStatus == "UNAPPROVED"

    def test_it_reads_without_a_character_set_warning(self, recwarn):
        # An em-dash in a DICOM string makes pydicom fall back to replacement characters. Harmless
        # here, but a warning on the capstone's first cell is a bad look.
        pydicom.dcmread(PLAN)
        assert not [w for w in recwarn if "encode" in str(w.message)]


class TestTheSurfaces:
    def test_every_surface_in_the_catalog_parses(self):
        import json

        from maprt_workshop.obj import parse_obj
        patients = json.loads((ROOT / "data" / "patients.json").read_text(encoding="utf-8"))
        for surfaces in patients.values():
            for entry in surfaces:
                path = ROOT / "data" / "surfaces" / f"{entry['id']}.obj"
                vertices, faces, _normals = parse_obj(path.read_bytes())
                assert len(vertices) > 1000 and len(faces) > 1000

    def test_they_are_roughly_person_shaped(self):
        # A plot of a surface should look like someone on a couch. If the generator ever produces
        # a cube, the notebook's 3D view is confusing rather than reassuring.
        import json

        from maprt_workshop.obj import bounding_box, parse_obj
        patients = json.loads((ROOT / "data" / "patients.json").read_text(encoding="utf-8"))
        first = next(iter(patients.values()))[0]["id"]
        vertices, _faces, _normals = parse_obj(
            (ROOT / "data" / "surfaces" / f"{first}.obj").read_bytes())
        low, high = bounding_box(vertices)
        length, width, height = high - low
        assert 1400 < length < 2200, f"{length:.0f} mm long is not a person"
        assert 250 < width < 900
        assert 100 < height < 700
        assert length > width > height


class TestRepositorySize:
    """Phase 5's gate. Binder rebuilds on every push and students clone on conference wifi."""

    BUDGET_MB = 25

    def committed_files(self):
        import fnmatch
        patterns = [line.strip() for line in (ROOT / ".gitignore").read_text().splitlines()
                    if line.strip() and not line.startswith("#")]

        def ignored(relative):
            return any(fnmatch.fnmatch(part, pattern.rstrip("/"))
                       for pattern in patterns for part in Path(relative).parts)

        return [p for p in ROOT.rglob("*")
                if p.is_file() and not ignored(str(p.relative_to(ROOT)))]

    def test_the_repository_fits_the_budget(self):
        total = sum(p.stat().st_size for p in self.committed_files())
        assert total / 1e6 < self.BUDGET_MB, f"{total / 1e6:.1f} MB exceeds {self.BUDGET_MB} MB"

    def test_no_single_committed_file_is_huge(self):
        # The 19 MB real surface export is the thing this is watching for: patient-derived and
        # far too big. It belongs in data/local/, which is git-ignored.
        for path in self.committed_files():
            size_mb = path.stat().st_size / 1e6
            assert size_mb < 5, f"{path.relative_to(ROOT)} is {size_mb:.1f} MB"

    def test_nothing_patient_derived_is_committed(self):
        # A blunt check for the directories the old project kept real data in.
        for path in self.committed_files():
            relative = str(path.relative_to(ROOT))
            assert not relative.startswith("_legacy"), relative
            assert not relative.startswith("data/local"), relative
            assert path.suffix.lower() != ".pdf", f"{relative}: the spec PDF must not ship"
