"""Every registered workshop has every folder.

A product is registered in ``sgrt_workshop.products`` and then needs a subfolder in each top-level
folder. Missing one does not fail anywhere obvious — ``<product>-workshop`` falls back to opening
Jupyter in the working directory, which looks like it worked. So a half-added product fails here.
"""

import importlib
from pathlib import Path

import pytest

from sgrt_workshop.products import PRODUCTS

ROOT = Path(__file__).resolve().parents[2]

PRODUCT_LIST = list(PRODUCTS.values())


@pytest.mark.parametrize("product", PRODUCT_LIST, ids=lambda p: p.name)
class TestEveryProductIsComplete:
    def test_it_has_notebooks_starting_with_an_index(self, product):
        assert (ROOT / "notebooks" / product.folder / "00_start_here.ipynb").is_file()

    def test_it_has_their_source(self, product):
        assert (ROOT / "scripts" / product.folder / "notebook_content" / "__init__.py").is_file()

    def test_it_has_data_with_a_readme(self, product):
        assert (ROOT / "data" / product.folder / "README.md").is_file()

    def test_it_has_docs(self, product):
        assert any((ROOT / "docs" / product.folder).glob("*.md"))

    def test_it_has_tests(self, product):
        assert any((ROOT / "tests" / product.folder).glob("test_*.py"))

    def test_its_emulator_can_report_its_address(self, product):
        if product.emulator is None:
            pytest.skip(f"{product.name} has no API, so no emulator")
        cli = importlib.import_module(f"{product.emulator}.cli")
        host, port = cli.address(["--port", "8123"])
        assert (host, port) == ("127.0.0.1", 8123)

    def test_the_docs_index_and_readme_list_it(self, product):
        assert f"]({product.folder}/" in (ROOT / "docs" / "README.md").read_text()
        assert f"`{product.command}`" in (ROOT / "README.md").read_text()
