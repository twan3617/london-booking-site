// Local-only integration check: synthetic slots, temporary storage, no cloud credentials.
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createServer } from 'node:http';
import { createInterface } from 'node:readline';
import next from 'next';
import { BlobsServer } from '@netlify/blobs/server';
import { getStore, setEnvironmentContext } from '@netlify/blobs';
import availabilityHandler from '../netlify/functions/availability.mjs';
import { isAvailabilitySnapshot, nextSaturday } from '../app/booking.ts';

const directory = await mkdtemp(join(tmpdir(), 'court-availability-preview-'));
const blobs = new BlobsServer({ directory, token: 'local-preview-only' });
const { address } = await blobs.start();
setEnvironmentContext({ siteID: 'local-preview', token: 'local-preview-only', edgeURL: address, apiURL: address });
const store = getStore('court-availability');
const venueId = 'greenwich-charlton-lido-and-lifestyle-club-hornfair-park';
const day = nextSaturday(new Date());
const bookingUrl = 'https://bookings.better.org.uk/location/charlton-lido/tennis-court-outdoor';

async function publish(scenario) {
  if (scenario === 'missing') return store.delete('latest');
  if (scenario === 'invalid') return store.setJSON('latest', { slots: 'invalid demo response' });
  assert.ok(['fresh', 'changed', 'stale'].includes(scenario), 'Use fresh, changed, stale, missing, invalid, or quit');
  const generatedAt = new Date(Date.now() - (scenario === 'stale' ? 3 * 60 * 60_000 : 0)).toISOString();
  const snapshot = {
    generated_at: generatedAt, coverage_start: day, coverage_end: day,
    venue_ids: [venueId], booking_urls: { [venueId]: bookingUrl },
    slots: [1, 2].map((court) => ({
      venue_id: venueId, court_id: `demo-${court}`,
      start_time: `${day}T19:00:00Z`, end_time: `${day}T20:00:00Z`,
      available: scenario !== 'changed' || court === 1,
      price_pence: 600, booking_url: bookingUrl, detected_at: generatedAt,
    })),
  };
  assert.ok(isAvailabilitySnapshot(snapshot));
  await store.setJSON('latest', snapshot);
}

// Check the real function against the SDK's local Blob server before opening the preview.
await publish('missing');
assert.equal((await availabilityHandler()).status, 503);
await publish('fresh');
const response = await availabilityHandler();
assert.equal(response.status, 200);
assert.equal(response.headers.get('cache-control'), 'no-store');
assert.equal((await response.json()).slots.filter((slot) => slot.available).length, 2);
await publish('changed');
assert.equal((await (await availabilityHandler()).json()).slots.filter((slot) => slot.available).length, 1);
await publish('fresh');

const app = next({ dev: false, hostname: '127.0.0.1', port: 3100 });
await app.prepare();
const handle = app.getRequestHandler();
const server = createServer(async (req, res) => {
  if (req.url !== '/.netlify/functions/availability') return handle(req, res);
  const result = req.method === 'GET' ? await availabilityHandler() : new Response(null, { status: 405 });
  res.writeHead(result.status, Object.fromEntries(result.headers));
  res.end(await result.text());
  console.log(`Availability read: ${result.status} at ${new Date().toISOString()}`);
});
server.listen(3100, '127.0.0.1');
console.log('Storage/function checks passed. SYNTHETIC DATA ONLY: http://127.0.0.1:3100');
console.log('Type fresh, changed, stale, missing, invalid, or quit. The page fetches on opening Find a time, tab return, and every five minutes.');
const input = createInterface({ input: process.stdin });
try {
  for await (const line of input) {
    const scenario = line.trim();
    if (scenario === 'quit') break;
    try { await publish(scenario); console.log(`Demo snapshot: ${scenario}`); }
    catch (error) { console.error(error.message); }
  }
} finally {
  input.close();
  process.stdin.pause();
  server.closeAllConnections();
  await new Promise((resolve) => server.close(resolve));
  await app.close();
  await blobs.stop();
  await rm(directory, { recursive: true, force: true });
}
