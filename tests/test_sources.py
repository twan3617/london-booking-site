import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from ingestion.sources import RequestPacer


class RequestPacerTests(unittest.TestCase):
    def test_requests_are_spaced_by_the_provider_interval(self):
        async def run():
            pacer = RequestPacer(1)
            await pacer.run(lambda: "first")
            await pacer.run(lambda: "second")

        with patch("ingestion.sources.monotonic", side_effect=[10, 10, 10.25, 11]), patch(
            "ingestion.sources.asyncio.sleep", new_callable=AsyncMock
        ) as sleep:
            asyncio.run(run())

        sleep.assert_awaited_once_with(0.75)

    def test_request_limit_stops_before_an_extra_call(self):
        calls = []

        async def run():
            pacer = RequestPacer(0, max_requests=2)
            await pacer.run(calls.append, "first")
            await pacer.run(calls.append, "second")
            await pacer.run(calls.append, "third")

        with self.assertRaisesRegex(RuntimeError, "request limit of 2"):
            asyncio.run(run())

        self.assertEqual(calls, ["first", "second"])


if __name__ == "__main__":
    unittest.main()
