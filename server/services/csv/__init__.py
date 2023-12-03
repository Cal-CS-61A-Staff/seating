import csv
import io


class LowerCaseDictReader(csv.DictReader):
    """
    Custom CSV DictReader that converts all headers to lowercase first.
    """

    def __init__(self, *args, **kwargs):
        super(LowerCaseDictReader, self).__init__(*args, **kwargs)
        self.fieldnames = [field.lower() for field in self.fieldnames]


def parse_csv(file):
    """
    Parse a CSV file and return a list of headers and rows.
    """
    reader = LowerCaseDictReader(io.StringIO(file.read().decode('utf-8')))
    headers = list(reader.fieldnames)
    rows = [row for row in reader]
    return headers, rows


def to_csv_str(headers, rows) -> str:
    """
    Convert a list of headers and rows to a CSV string.
    """
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return output.getvalue()
