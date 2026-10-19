"""Write a synthetic DICOM RT Plan — no patient data involved.

The capstone notebook reads a plan the way a real QA script would: patient id, isocenter, patient
position, and each beam's gantry and couch angles. That needs a real RT Plan file, because the
point of the exercise is practising `pydicom` against the tag layout a planning system actually
emits — not against a dictionary someone typed out.

So this writes a genuine, parseable RT Plan whose *contents* are invented: a made-up patient id
matching the simulator's catalog, a plausible isocenter, and a beam list with the shapes that
matter for collision work — static beams, an arc, and a setup field.

    uv run python scripts/make_synthetic_plan.py data/MapRT/plans/ANON001_plan.dcm

Only the tags a clearance workflow reads are populated. It is not a deliverable plan and no
planning system should be asked to open it.
"""

import argparse
import datetime as dt
from pathlib import Path

from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

# (beam number, name, type, couch, gantry start, gantry stop, rotation direction)
# A spread chosen so the capstone's pass/fail table has both outcomes against the simulator's
# clearance model: anterior and posterior clear, a kicked-couch lateral that does not.
BEAMS = [
    (1, "SETUP AP", "SETUP", 0.0, 0.0, None, "NONE"),
    (2, "AP", "STATIC", 0.0, 0.0, None, "NONE"),
    (3, "LAO", "STATIC", 0.0, 45.0, None, "NONE"),
    (4, "LT LAT", "STATIC", 0.0, 90.0, None, "NONE"),
    (5, "PA", "STATIC", 0.0, 180.0, None, "NONE"),
    (6, "RT LAT KICK", "STATIC", 90.0, 270.0, None, "NONE"),
    (7, "VMAT CW", "DYNAMIC", 0.0, 181.0, 179.0, "CW"),
    (8, "VMAT CC KICK", "DYNAMIC", 45.0, 179.0, 181.0, "CC"),
]

ISOCENTER = [0.0, 0.0, 0.0]


def control_point(index, gantry, couch, rotation, isocenter):
    """One ControlPointSequence item.

    A planning system writes the full geometry on control point 0 and only what *changes* on the
    rest — which is why a reader has to carry values forward rather than expecting every field on
    every point. The capstone notebook meets exactly that.
    """
    cp = Dataset()
    cp.ControlPointIndex = index
    cp.CumulativeMetersetWeight = float(index)
    if index == 0:
        cp.GantryAngle = gantry
        cp.GantryRotationDirection = rotation
        cp.PatientSupportAngle = couch
        cp.IsocenterPosition = [str(v) for v in isocenter]
        cp.NominalBeamEnergy = 6.0
    else:
        cp.GantryAngle = gantry
        cp.GantryRotationDirection = "NONE"
    return cp


def build_plan(patient_id, patient_name, isocenter=ISOCENTER, position="HFS"):
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.481.5"   # RT Plan Storage
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.ImplementationVersionName = "MAPRT_WORKSHOP"

    ds = FileDataset(None, {}, file_meta=file_meta, preamble=b"\0" * 128)
    now = dt.datetime(2026, 4, 24, 16, 57, 35)

    ds.SOPClassUID = file_meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    ds.Modality = "RTPLAN"
    ds.Manufacturer = "MapRT Scripting Workshop"
    # Plain ASCII: DICOM's default character set is ISO-IR 6, and a stray em-dash here makes
    # pydicom fall back to replacement characters with a warning. Not worth a SpecificCharacterSet
    # just to get a nicer dash into a field nobody reads.
    ds.ManufacturerModelName = "synthetic - not a deliverable plan"
    ds.StudyInstanceUID = generate_uid()
    ds.SeriesInstanceUID = generate_uid()
    ds.StudyDate = now.strftime("%Y%m%d")
    ds.StudyTime = now.strftime("%H%M%S")

    ds.PatientName = patient_name
    ds.PatientID = patient_id
    ds.PatientBirthDate = ""
    ds.PatientSex = ""

    ds.RTPlanLabel = "WORKSHOP"
    ds.RTPlanName = "Synthetic workshop plan"
    ds.RTPlanDate = ds.StudyDate
    ds.RTPlanTime = ds.StudyTime
    ds.RTPlanGeometry = "PATIENT"
    ds.ApprovalStatus = "UNAPPROVED"

    # PatientSetupSequence carries the patient position (0018,5100) the GetMap body needs.
    setup = Dataset()
    setup.PatientSetupNumber = 1
    setup.PatientPosition = position
    ds.PatientSetupSequence = [setup]

    ds.FractionGroupSequence = [_fraction_group()]
    ds.BeamSequence = [_beam(entry, isocenter) for entry in BEAMS]
    return ds


def _fraction_group():
    group = Dataset()
    group.FractionGroupNumber = 1
    group.NumberOfFractionsPlanned = 25
    group.NumberOfBeams = len(BEAMS)
    group.NumberOfBrachyApplicationSetups = 0
    references = []
    for number, *_rest in BEAMS:
        reference = Dataset()
        reference.ReferencedBeamNumber = number
        reference.BeamMeterset = 100.0
        references.append(reference)
    group.ReferencedBeamSequence = references
    return group


def _beam(entry, isocenter):
    number, name, beam_type, couch, gantry_start, gantry_stop, rotation = entry

    beam = Dataset()
    beam.BeamNumber = number
    beam.BeamName = name
    beam.BeamDescription = name
    # DICOM's BeamType is STATIC or DYNAMIC; the treatment/setup distinction is TreatmentDeliveryType.
    beam.BeamType = "DYNAMIC" if rotation != "NONE" else "STATIC"
    beam.TreatmentDeliveryType = "TREATMENT" if beam_type != "SETUP" else "SETUP"
    beam.RadiationType = "PHOTON"
    beam.TreatmentMachineName = "TrueBeam2"
    beam.SourceAxisDistance = 1000.0
    beam.PrimaryDosimeterUnit = "MU"
    beam.NumberOfWedges = 0
    beam.NumberOfCompensators = 0
    beam.NumberOfBoli = 0
    beam.NumberOfBlocks = 0
    beam.FinalCumulativeMetersetWeight = 1.0

    stop = gantry_start if gantry_stop is None else gantry_stop
    beam.NumberOfControlPoints = 2
    beam.ControlPointSequence = [
        control_point(0, gantry_start, couch, rotation, isocenter),
        control_point(1, stop, couch, rotation, isocenter),
    ]
    return beam


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("output", help="where to write the .dcm")
    parser.add_argument("--patient-id", default="ANON001",
                        help="must match a patient in the simulator's data/MapRT/patients.json")
    parser.add_argument("--patient-name", default="WORKSHOP^SYNTHETIC")
    parser.add_argument("--position", default="HFS")
    args = parser.parse_args(argv)

    ds = build_plan(args.patient_id, args.patient_name, position=args.position)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    ds.save_as(path, enforce_file_format=True)
    print(f"{path}: {len(ds.BeamSequence)} beams, patient {ds.PatientID}, "
          f"{path.stat().st_size / 1024:,.1f} KB")


if __name__ == "__main__":
    main()
