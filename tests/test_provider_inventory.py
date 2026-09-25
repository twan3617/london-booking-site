import unittest

from ingestion.models import Venue
from scripts.provider_inventory import build_inventory, source_kind


class ProviderInventoryTests(unittest.TestCase):
    def test_booking_host_and_metadata_source_are_separate(self):
        venue = Venue(
            id="example",
            name="Example",
            sport="tennis",
            provider="html",
            booking_url="https://operator.example/book",
            metadata_sources=("https://clubspark.lta.org.uk/Example",),
        )

        item = build_inventory((venue,))[0]

        self.assertEqual(item["metadata_source_family"], "html")
        self.assertEqual(item["booking_host"], "operator.example")
        self.assertEqual(item["metadata_sources"][0]["detected_kind"], "clubspark")

    def test_pdf_source_is_not_reported_as_html(self):
        self.assertEqual(source_kind("https://council.example/courts.pdf?version=2"), "pdf")

    def test_everyone_active_api_is_reported_as_structured(self):
        self.assertEqual(
            source_kind("https://api.everyoneactive.com/v1.0/centres/0153/timetable"),
            "everyoneactive",
        )

    def test_places_leisure_timetable_page_is_reported_as_structured(self):
        self.assertEqual(
            source_kind("https://www.placesleisure.org/centres/tooting-leisure-centre/centre-activities/sports/"),
            "placesleisure",
        )


if __name__ == "__main__":
    unittest.main()
