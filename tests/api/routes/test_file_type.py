from src.api.routes.file_type import FileCategory, get_file_category


def test_cad_files_are_treated_as_documents() -> None:
    assert get_file_category("site-plan.dxf") == FileCategory.DOCUMENT
    assert get_file_category("site-plan.dwg") == FileCategory.DOCUMENT


def test_visio_files_are_treated_as_documents() -> None:
    assert get_file_category("flowchart.vsdx") == FileCategory.DOCUMENT
    assert get_file_category("flowchart.vsd") == FileCategory.DOCUMENT
    assert get_file_category("flowchart.vsdm") == FileCategory.DOCUMENT


def test_tiff_files_are_treated_as_images() -> None:
    assert get_file_category("scan.tiff") == FileCategory.IMAGE
    assert get_file_category("scan.tif") == FileCategory.IMAGE
