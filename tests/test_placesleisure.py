import html
import json
import unittest
from datetime import datetime, time, timezone

from ingestion.models import MetadataField, Venue
from ingestion.providers.placesleisure import parse_timetable


SOURCE_URL = "https://www.placesleisure.org/centres/tooting-leisure-centre/centre-activities/sports/"
VENUE = Venue(
    id="squash-wandsworth-tooting",
    name="Tooting Leisure Centre",
    sport="squash",
    provider="html",
    booking_url=SOURCE_URL,
    metadata_sources=(SOURCE_URL,),
)


class PlacesLeisureMetadataTests(unittest.TestCase):
    def test_embedded_timetable_normalizes_squash_duration_and_hours(self):
        windows = [
            ("2026-09-28T06:00:00Z", "2026-09-28T20:59:59Z"),
            ("2026-09-29T06:00:00Z", "2026-09-29T20:59:59Z"),
            ("2026-09-30T06:00:00Z", "2026-09-30T20:59:59Z"),
            ("2026-10-01T06:00:00Z", "2026-10-01T20:59:59Z"),
            ("2026-10-02T06:00:00Z", "2026-10-02T20:59:59Z"),
            ("2026-10-03T06:30:00Z", "2026-10-03T18:29:59Z"),
            ("2026-10-04T07:00:00Z", "2026-10-04T20:29:59Z"),
        ]
        sessions = []
        for start, final_end in windows:
            current = datetime.fromisoformat(start.replace("Z", "+00:00"))
            end = datetime.fromisoformat(final_end.replace("Z", "+00:00"))
            while current < end:
                session_end = current.timestamp() + 45 * 60 - 1
                sessions.append({
                    "s": current.isoformat().replace("+00:00", "Z"),
                    "e": datetime.fromtimestamp(session_end, timezone.utc).isoformat().replace("+00:00", "Z"),
                    "aId": "015A000005",
                    "ag": "SQUASH",
                })
                current = datetime.fromtimestamp(session_end + 1, timezone.utc)
        payload = {
            "centreName": "Tooting Leisure Centre - Gladstone",
            "timetables": [{
                "id": 62,
                "name": "Sports",
                "activities": [{"id": "015A000005", "name": "Squash", "webBookable": True}],
                "sessions": sessions,
                "locations": [],
            }],
        }
        page = f'<input id="timetable-data" value="{html.escape(json.dumps(payload), quote=True)}">'

        patch = parse_timetable(VENUE, page, SOURCE_URL, datetime(2026, 9, 25, tzinfo=timezone.utc))

        self.assertEqual(patch.values[MetadataField.SLOT_DURATION_MINUTES], 45)
        self.assertEqual(patch.values[MetadataField.OPENING_HOURS], {
            "monday": ((time(7), time(22)),),
            "tuesday": ((time(7), time(22)),),
            "wednesday": ((time(7), time(22)),),
            "thursday": ((time(7), time(22)),),
            "friday": ((time(7), time(22)),),
            "saturday": ((time(7, 30), time(19, 30)),),
            "sunday": ((time(8), time(21, 30)),),
        })


if __name__ == "__main__":
    unittest.main()
