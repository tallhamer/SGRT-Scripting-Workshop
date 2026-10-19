"""The repository as a whole: its size, and that nothing patient-derived is committed.

Shared by every workshop: Binder rebuilds the whole repository on every push, and a student clones
all of it whichever workshop they came for.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class TestRepositorySize:
    """Phase 5's gate. Binder rebuilds on every push and students clone on conference wifi."""

    BUDGET_MB = 25

    def committed_files(self):
        import fnmatch
        patterns = [line.strip() for line in (ROOT / ".gitignore").read_text().splitlines()
                    if line.strip() and not line.startswith("#")]

        def ignored(relative):
            # A bare name (".venv/") matches any one path component; a pattern with a slash in
            # it ("data/*/local/") is anchored at the root and matches that directory's contents.
            parts = Path(relative).parts
            prefixes = ["/".join(parts[:i]) for i in range(1, len(parts) + 1)]
            for pattern in (p.rstrip("/") for p in patterns):
                candidates = prefixes if "/" in pattern else parts
                if any(fnmatch.fnmatch(c, pattern) for c in candidates):
                    return True
            return False

        return [p for p in ROOT.rglob("*")
                if p.is_file() and not ignored(str(p.relative_to(ROOT)))]

    def test_the_repository_fits_the_budget(self):
        total = sum(p.stat().st_size for p in self.committed_files())
        assert total / 1e6 < self.BUDGET_MB, f"{total / 1e6:.1f} MB exceeds {self.BUDGET_MB} MB"

    def test_no_single_committed_file_is_huge(self):
        # The 19 MB real surface export is the thing this is watching for: patient-derived and
        # far too big. It belongs in data/MapRT/local/, which is git-ignored.
        for path in self.committed_files():
            size_mb = path.stat().st_size / 1e6
            assert size_mb < 5, f"{path.relative_to(ROOT)} is {size_mb:.1f} MB"

    def test_nothing_patient_derived_is_committed(self):
        # A blunt check for the directories the old project kept real data in.
        for path in self.committed_files():
            relative = str(path.relative_to(ROOT))
            assert not relative.startswith("_legacy"), relative
            # Every product's local/ overlay — data/MapRT/local today, data/AlignRT/local later.
            assert not re.match(r"data/[^/]+/local/", relative), relative
            assert path.suffix.lower() != ".pdf", f"{relative}: the spec PDF must not ship"
