import { readFile } from 'node:fs/promises';
import { getStore } from '@netlify/blobs';
import { isAvailabilitySnapshot } from '../app/booking.ts';

const snapshot = JSON.parse(await readFile(new URL('../data/availability.json', import.meta.url), 'utf8'));
if (!isAvailabilitySnapshot(snapshot) || !snapshot.venue_ids.length || !snapshot.slots.length) {
  throw new Error('Refusing to publish an invalid or empty availability snapshot');
}
const age = Date.now() - Date.parse(snapshot.generated_at);
if (age < -5 * 60_000 || age > 60 * 60_000) throw new Error('Refusing to publish a snapshot outside the current hour');

const { NETLIFY_SITE_ID: siteID, NETLIFY_AUTH_TOKEN: token } = process.env;
if (!siteID || !token) throw new Error('NETLIFY_SITE_ID and NETLIFY_AUTH_TOKEN are required');
await getStore('court-availability', { siteID, token }).setJSON('latest', snapshot);
console.log(`Published ${snapshot.slots.length} slots checked at ${snapshot.generated_at}`);
