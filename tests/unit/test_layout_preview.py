import pytest

from server.models import Seat
from server.services.core.data import get_layout_preview_from_text
from server.services.core.layout_preview import (
    CONDITION_GROUP,
    HANDEDNESS_GROUP,
    LAYOUT_GROUP,
    PLACEMENT_GROUP,
    SEAT_ATTRIBUTES,
    build_layout_preview,
    describe_attribute,
    is_broken,
    seat_attribute_vocabulary,
    seat_badge,
    seat_label,
)
from server.services.core.room import prepare_seat
from server.services.csv import parse_csv_str, sniff_delimiter

# The column vocabulary of the master room sheet, whose tabs are exported as
# CSV to get here. Rows are two seats of a row, a walkway gap and movable seats.
MASTER_SHEET_CSV = (
    "Row,Seat,X,Y,Reserved,Lefty,Righty,Aisle,Front,Back,Table,"
    "AlternateSeating1,AlternateSeating2,2/3 Seating,WalkingRow,Broken,Count\n"
) + """A,1,1,,,,TRUE,TRUE,TRUE,,,TRUE,,TRUE,,,
A,2,,,,,TRUE,,TRUE,,,,TRUE,TRUE,,,
A,3,,,,TRUE,TRUE,TRUE,TRUE,,,TRUE,,,,TRUE,
B,1,,,TRUE,,TRUE,TRUE,,,TRUE,,TRUE,,TRUE,,
,,,,,TRUE,,,,,,,,,,,4
"""

SAMPLE_CSV = """row,seat,x,y,lefty,righty,alt1,alt2,broken,dsp,count
A,1,0,0,TRUE,,TRUE,,,,
A,2,1,0,,TRUE,,TRUE,,,
A,3,2,0,TRUE,,TRUE,,TRUE,,
B,1,0,1,TRUE,,,TRUE,,TRUE,
B,2,1,1,,TRUE,TRUE,,,,
,,,,TRUE,,,,,,2
"""


def preview_from_csv(csv_str=SAMPLE_CSV):
    return get_layout_preview_from_text(csv_str)


def preview_without_columns(csv_str=SAMPLE_CSV):
    headers, rows = parse_csv_str(csv_str)
    return build_layout_preview(prepare_seat(headers, rows))


class TestDescribeAttribute:
    """
    The schema rule: a column is a seat attribute only if it is in the
    canonical vocabulary; everything else is a named layout.
    """

    def test_known_attribute_is_labelled_and_grouped(self):
        info = describe_attribute('lefty')
        assert info.label == 'Lefty'
        assert info.group == HANDEDNESS_GROUP
        assert info.badge == 'L'
        assert info.description
        assert not info.is_layout

    def test_attribute_is_normalized(self):
        assert describe_attribute('  DSP ').key == 'dsp'
        assert describe_attribute('  DSP ').group == PLACEMENT_GROUP

    def test_every_canonical_attribute_is_described(self):
        for key in SEAT_ATTRIBUTES:
            info = describe_attribute(key)
            assert not info.is_layout, key
            assert info.description.endswith('.'), key
            assert info.label and not info.label.islower(), key

    def test_columns_outside_the_vocabulary_are_layouts(self):
        # Alternating layouts, course-specific ones and room-name columns all
        # name a set of seats rather than a property of a chair.
        for key in ('alternateseating', 'alternateseating1', 'alternateseating2',
                    'alt-seating-columns', '2/3 seating', 'cs61c_sp26_alt3',
                    '2050vlsb', 'evans60', '150wheeler', 'temp'):
            assert describe_attribute(key).is_layout, key
            assert describe_attribute(key).group == LAYOUT_GROUP, key

    def test_a_layout_is_labelled_with_its_own_heading(self):
        assert describe_attribute('2050vlsb', '2050VLSB').label == '2050VLSB'
        assert describe_attribute('alternateseating1', 'AlternateSeating1').label == 'AlternateSeating1'

    def test_a_layout_without_a_heading_gets_a_readable_name(self):
        assert describe_attribute('alternateseating1').label == 'Alternate Seating 1'
        assert describe_attribute('walk_up').label == 'Walk Up'

    def test_broken_attributes_are_flagged(self):
        assert describe_attribute('broken').is_broken
        assert describe_attribute('broken').group == CONDITION_GROUP
        assert not describe_attribute('aisle').is_broken

    def test_vocabulary_carries_what_the_seat_editor_needs(self):
        vocabulary = {item['key']: item for item in seat_attribute_vocabulary()}
        assert set(vocabulary) == set(SEAT_ATTRIBUTES)
        assert vocabulary['lefty']['badge'] == 'L'
        assert vocabulary['broken']['broken'] is True
        # Only attributes that restrict who may sit there get a marker dot.
        assert vocabulary['dsp']['note'] is True
        assert vocabulary['reserved']['note'] is True
        assert vocabulary['aisle']['note'] is False
        assert vocabulary['lefty']['note'] is False


class TestSeatMarkings:
    def test_lefty_only_seats_are_labelled(self):
        assert seat_badge({'lefty'}) == 'L'
        assert seat_badge({'lefty', 'alt1', 'aisle'}) == 'L'

    def test_righty_seats_are_not_labelled(self):
        # Righty is the default desk in every room of the master sheet, so a
        # letter on all of them is noise rather than information.
        assert seat_badge({'righty'}) == ''
        assert seat_badge({'righty', 'aisle'}) == ''

    def test_desks_that_work_either_way_are_not_labelled(self):
        # Whole rooms are tagged both lefty and righty; those seats constrain
        # nobody, so a letter would say nothing.
        assert seat_badge({'lefty', 'righty'}) == ''

    def test_seats_without_handedness_get_no_letter(self):
        assert seat_badge(set()) == ''
        assert seat_badge({'alt1', 'dsp'}) == ''

    def test_broken_seats_are_not_labelled(self):
        # The slash is the marking that matters on a seat nobody can use.
        assert seat_badge({'lefty', 'broken'}) == ''
        assert seat_badge({'lefty', 'unusable'}) == ''

    def test_broken_detection(self):
        assert is_broken({'broken'})
        assert is_broken({'left', 'BROKEN'})
        assert not is_broken({'left'})

    def test_seat_label_lists_attributes(self):
        assert seat_label('A1', {'lefty', 'broken'}) == 'A1 — Lefty, Broken'
        assert seat_label('A1', set()) == 'A1'
        assert seat_label(None, {'lefty'}).startswith('Movable seat')

    def test_seat_label_leaves_out_layouts(self):
        # Hovering a seat should not read back the room or exam it belongs to.
        assert seat_label('A1', {'lefty', '2050vlsb', 'alternateseating1'}) == 'A1 — Lefty'


class TestBuildLayoutPreview:
    def test_counts_fixed_movable_and_broken_seats(self):
        preview = preview_from_csv()
        assert preview['counts'] == {'total': 7, 'fixed': 5, 'movable': 2, 'broken': 1}

    def test_fixed_seats_are_grouped_into_display_rows(self):
        preview = preview_from_csv()
        rows = [[seat['name'] for seat in row] for row in preview['grid_rows']]
        assert rows == [['A1', 'A2', 'A3'], ['B1', 'B2']]

    def test_bounds_cover_every_fixed_seat(self):
        preview = preview_from_csv()
        assert preview['bounds'] == {'x_min': 0, 'x_max': 2, 'y_min': 0, 'y_max': 1}

    def test_movable_seats_are_grouped_by_attribute_set(self):
        preview = preview_from_csv()
        assert len(preview['movable_groups']) == 1
        group = preview['movable_groups'][0]
        assert group['attributes'] == ['lefty']
        assert group['label'] == 'Lefty'
        assert len(group['seats']) == 2

    def test_seats_carry_their_display_markings(self):
        preview = preview_from_csv()
        by_name = {seat['name']: seat for seat in preview['fixed_seats']}
        assert by_name['A1']['badge'] == 'L'
        assert by_name['A2']['badge'] == ''  # righty is the unlabelled default
        assert by_name['A3']['broken'] is True
        assert by_name['B1']['notes'] == ['DSP']
        assert by_name['B2']['notes'] == []

    def test_positional_attributes_do_not_get_a_marker(self):
        # Whole rooms are tagged aisle/front/table; a dot on every seat is noise.
        preview = preview_from_csv('row,seat,righty,aisle,front,table\nA,1,TRUE,TRUE,TRUE,TRUE\n')
        assert preview['seats'][0]['notes'] == []
        assert preview['seats'][0]['attribute_labels'] == ['Righty', 'Aisle', 'Front', 'Table']

    def test_highlight_options_are_grouped_and_counted(self):
        preview = preview_from_csv()
        options = {group['group']: {o['key']: o['count'] for o in group['options']}
                   for group in preview['highlight_options']}
        assert options[LAYOUT_GROUP] == {'alt1': 3, 'alt2': 2}
        assert options[HANDEDNESS_GROUP] == {'lefty': 5, 'righty': 2}
        assert options[CONDITION_GROUP] == {'broken': 1}
        assert options[PLACEMENT_GROUP] == {'dsp': 1}

    def test_layouts_are_offered_before_seat_attributes(self):
        preview = preview_from_csv()
        assert [group['group'] for group in preview['highlight_options']] == [
            LAYOUT_GROUP, HANDEDNESS_GROUP, CONDITION_GROUP, PLACEMENT_GROUP]

    def test_legend_splits_layouts_from_seat_attributes(self):
        preview = preview_from_csv()
        assert [entry['label'] for entry in preview['legend_layouts']] == ['alt1', 'alt2']
        entries = {entry['label']: entry
                   for group in preview['legend_attributes'] for entry in group['entries']}
        assert set(entries) == {'Lefty', 'Righty', 'Broken', 'DSP'}
        assert entries['Broken']['broken'] is True
        assert entries['Lefty']['badge'] == 'L'
        assert entries['DSP']['count'] == 1
        assert all(entry['description'] for entry in entries.values())

    def test_layout_without_fixed_seats_has_no_bounds(self):
        preview = preview_from_csv('row,seat,lefty,count\n,,TRUE,3\n')
        assert preview['bounds'] is None
        assert preview['grid_rows'] == []
        assert preview['counts']['movable'] == 3

    def test_seats_without_attributes_are_still_described(self):
        preview = preview_from_csv('row,seat\nA,1\n')
        seat = preview['seats'][0]
        assert seat['label'] == 'A1'
        assert seat['badge'] == ''
        assert seat['broken'] is False
        assert preview['highlight_options'] == []
        assert preview['legend_layouts'] == []
        assert preview['legend_attributes'] == []

    def test_movable_seats_keep_their_id_but_no_coordinates(self):
        preview = preview_from_csv()
        movable = preview['movable_seats'][0]
        assert movable['x'] is None and movable['y'] is None
        assert movable['id']
        assert movable['fixed'] is False

    def test_preview_does_not_persist_seats(self, db):
        preview_from_csv()
        assert Seat.query.count() == 0


class TestDelimiters:
    """A room can arrive as a downloaded CSV or as rows pasted from a sheet."""

    def test_a_comma_separated_header_is_read_as_csv(self):
        assert sniff_delimiter('row,seat,lefty\nA,1,TRUE\n') == ','

    def test_a_tab_separated_header_is_read_as_tsv(self):
        assert sniff_delimiter('Row\tSeat\tLefty\nA\t1\tTRUE\n') == '\t'

    def test_a_heading_containing_a_comma_does_not_beat_the_tabs(self):
        # "2/3 Seating" is a real column, and pasted rows are tab separated.
        assert sniff_delimiter('Row\tSeat\t2/3 Seating, alt\nA\t1\tTRUE\n') == '\t'

    def test_a_single_column_falls_back_to_csv(self):
        assert sniff_delimiter('row\nA\n') == ','

    def test_a_byte_order_mark_is_ignored(self):
        assert sniff_delimiter('\ufeffRow\tSeat\nA\t1\n') == '\t'

    def test_pasted_rows_give_the_same_layout_as_the_csv(self):
        as_csv = preview_from_csv(MASTER_SHEET_CSV)
        as_tsv = preview_from_csv(MASTER_SHEET_CSV.replace(',', '\t'))
        assert as_tsv['counts'] == as_csv['counts']
        assert [s['label'] for s in as_tsv['seats']] == [s['label'] for s in as_csv['seats']]

    def test_a_pasted_google_sheets_range_is_understood(self):
        # Tab separated, TRUE/FALSE in every cell, blank x/y - exactly what a
        # copied range out of the master room sheet looks like.
        pasted = (
            "Row\tSeat\tX\tY\tReserved\tLefty\tRighty\tAisle\tFront\tBack\tTable\t"
            "AlternateSeating1\t2/3 Seating\tWalkingRow\tBroken\t150Wheeler\n"
            "A\t3\t\t\tTRUE\tFALSE\tTRUE\tFALSE\tTRUE\tFALSE\tFALSE\tTRUE\tFALSE\tFALSE\t\tTRUE\n"
            "A\t9\t\t\tTRUE\tTRUE\tFALSE\tTRUE\tTRUE\tFALSE\tFALSE\tTRUE\tFALSE\tFALSE\t\tTRUE\n"
            "C\t2\t\t\tFALSE\tFALSE\tTRUE\tFALSE\tFALSE\tFALSE\tFALSE\tTRUE\tTRUE\tTRUE\t\tTRUE\n"
        )
        preview = preview_from_csv(pasted)
        assert preview['counts'] == {'total': 3, 'fixed': 3, 'movable': 0, 'broken': 0}
        by_name = {seat['name']: seat for seat in preview['fixed_seats']}
        assert by_name['A9']['badge'] == 'L'
        assert by_name['A3']['badge'] == ''
        # FALSE cells stay off, and layouts keep the sheet's own spelling.
        assert by_name['A3']['attributes'] == ['150wheeler', 'alternateseating1', 'front',
                                               'reserved', 'righty']
        layouts = [entry['label'] for entry in preview['legend_layouts']]
        assert layouts == ['150Wheeler', '2/3 Seating', 'AlternateSeating1']


class TestMasterSheetLayout:
    """The columns a room tab of the master room sheet actually uses."""

    def setup_method(self):
        self.preview = preview_from_csv(MASTER_SHEET_CSV)

    def test_every_seat_is_read(self):
        assert self.preview['counts'] == {'total': 8, 'fixed': 4, 'movable': 4, 'broken': 1}

    def test_layout_columns_are_separated_from_seat_attributes(self):
        groups = {group['group']: [o['key'] for o in group['options']]
                  for group in self.preview['highlight_options']}
        assert groups[LAYOUT_GROUP] == ['2/3 seating', 'alternateseating1', 'alternateseating2']
        assert groups[HANDEDNESS_GROUP] == ['lefty', 'righty']
        assert groups[CONDITION_GROUP] == ['broken']
        assert groups[PLACEMENT_GROUP] == ['aisle', 'front', 'reserved', 'table', 'walkingrow']

    def test_only_lefty_only_seats_are_labelled(self):
        by_name = {seat['name']: seat for seat in self.preview['fixed_seats']}
        assert by_name['A1']['badge'] == ''  # righty
        assert by_name['A3']['badge'] == ''  # both ways, and broken
        assert by_name['A3']['broken'] is True

    def test_hovering_a_seat_does_not_name_its_layouts(self):
        by_name = {seat['name']: seat for seat in self.preview['fixed_seats']}
        assert by_name['A1']['attribute_labels'] == ['Righty', 'Aisle', 'Front']

    def test_movable_seats_collapse_into_one_group(self):
        assert len(self.preview['movable_groups']) == 1
        assert self.preview['movable_groups'][0]['label'] == 'Lefty'
        assert len(self.preview['movable_groups'][0]['seats']) == 4


@pytest.fixture()
def authed_client(seeded_db, login_as):
    """A test client logged in as the seeded staff user."""
    return login_as(1)


@pytest.mark.app_config(WTF_CSRF_ENABLED=False)
class TestPreviewLayoutPage:
    def test_page_requires_login(self, client):
        response = client.get('/layouts/preview/')
        assert response.status_code == 302

    def test_page_offers_an_upload_form(self, authed_client):
        response = authed_client.get('/layouts/preview/')
        assert response.status_code == 200
        assert b'Seating Layout Preview' in response.data
        assert b'upload_csv_file' in response.data
        assert b'layout-csv-text' in response.data

    def test_pasted_csv_renders_every_seat(self, authed_client):
        response = authed_client.post('/layouts/preview/', data={'text': SAMPLE_CSV})
        assert response.status_code == 200
        assert response.data.count(b'class="layout-seat"') == 7
        assert b'alt1 (3)' in response.data  # a layout keeps its own heading

    def test_uploaded_csv_renders_every_seat(self, authed_client):
        import io
        data = {'file': (io.BytesIO(SAMPLE_CSV.encode()), 'room.csv')}
        response = authed_client.post('/layouts/preview/', data=data,
                                      content_type='multipart/form-data')
        assert response.status_code == 200
        assert response.data.count(b'class="layout-seat"') == 7

    def test_uploaded_tsv_renders_every_seat(self, authed_client):
        import io
        data = {'file': (io.BytesIO(SAMPLE_CSV.replace(',', '\t').encode()), 'room.tsv')}
        response = authed_client.post('/layouts/preview/', data=data,
                                      content_type='multipart/form-data')
        assert response.status_code == 200
        assert response.data.count(b'class="layout-seat"') == 7

    def test_an_upload_with_a_byte_order_mark_is_read(self, authed_client):
        import io
        data = {'file': (io.BytesIO(SAMPLE_CSV.encode('utf-8-sig')), 'room.csv')}
        response = authed_client.post('/layouts/preview/', data=data,
                                      content_type='multipart/form-data')
        assert response.status_code == 200
        assert response.data.count(b'class="layout-seat"') == 7

    def test_pasted_rows_render_every_seat(self, authed_client):
        response = authed_client.post('/layouts/preview/',
                                      data={'text': SAMPLE_CSV.replace(',', '\t')})
        assert response.status_code == 200
        assert response.data.count(b'class="layout-seat"') == 7

    def test_empty_submission_is_rejected(self, authed_client):
        response = authed_client.post('/layouts/preview/', data={'text': '  '})
        assert response.status_code == 200
        assert b'Upload a file, or paste the rows from a spreadsheet.' in response.data
        assert b'class="layout-seat"' not in response.data

    def test_csv_without_required_columns_is_reported(self, authed_client):
        response = authed_client.post('/layouts/preview/', data={'text': 'name\nA1\n'})
        assert response.status_code == 200
        assert b'Failed to preview layout' in response.data
        assert b'class="layout-seat"' not in response.data
