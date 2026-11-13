"""Controlled government responses and time; no application internals are mocked."""
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"

ARCHIVE_URL = "https://repositorio.dados.gov.br/segrt/cargos%20vagos%20e%20vacancia/"
SEPTEMBER_URL = ARCHIVE_URL + "2026/CargosVagosVacancias_202609.ods"
SEPTEMBER = Path(__file__).parent.joinpath("fixtures/september-2026.ods").read_bytes()
CHECK_TIME = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def variant(edit):
    """Edit a copy of official source XML, never application/parser internals."""
    with ZipFile(BytesIO(SEPTEMBER)) as archive:
        root = ET.fromstring(archive.read("content.xml"))
    table = next(t for t in root.iter(TABLE + "table")
                 if t.get(TABLE + "name") == "por_Órgao_e_Cargo")
    header_row = table.find(TABLE + "table-row")
    header = ["".join(c.itertext()) for c in header_row][:20]
    edit(table, header)
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", "application/vnd.oasis.opendocument.spreadsheet")
        archive.writestr("content.xml", ET.tostring(root, encoding="utf-8"))
    return output.getvalue()


def pf_classes(table, header):
    return [row for row in table.findall(TABLE + "table-row")[1:]
            if "".join(row[header.index("ORGAO")].itertext()) == "20115"
            and "".join(row[header.index("CARGO")].itertext()) in ("901004", "901005", "901006", "901011")]


def set_cell(row, header, name, value):
    cell = row[header.index(name)]
    cell.attrib.clear()
    cell[:] = []
    cell.set(OFFICE + "value-type", "string")
    ET.SubElement(cell, TEXT + "p").text = str(value)


class ControlledArchive:
    def __init__(self, resources=None):
        self.resources = dict(resources if resources is not None else {SEPTEMBER_URL: SEPTEMBER})

    def archive_index(self):
        years = sorted({url.split("/")[-2] for url in self.resources})
        return "".join(f'<a href="{year}/">{year}/</a>' for year in years)

    def year_index(self, year):
        return "".join(
            f'<a href="{url.rsplit("/", 1)[1]}">ODS</a>'
            for url in self.resources if url.split("/")[-2] == year
        )

    def spreadsheet(self, url):
        return self.resources[url]
