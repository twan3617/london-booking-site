import { readFile } from 'node:fs/promises';
import { getStore } from '@netlify/blobs';
import { isAvailabilitySnapshot, mergeAvailabilityRefresh, withoutLtaAvailability } from '../app/booking.ts';

const settings = JSON.parse(await readFile(new URL('../config/site-settings.json', import.meta.url), 'utf8'));

const current = JSON.parse(await readFile(new URL('../data/availability.json', import.meta.url), 'utf8'));
if (!isAvailabilitySnapshot(current) || !current.providers || !Object.keys(current.providers).length) {
  throw new Error('Refusing to publish an invalid or empty availability snapshot');
}
const age = Date.now() - Date.parse(current.generated_at);
if (age < -5 * 60_000 || age > 60 * 60_000) throw new Error('Refusing to publish a snapshot outside the current hour');

const { NETLIFY_SITE_ID: siteID, NETLIFY_AUTH_TOKEN: token } = process.env;
if (!siteID || !token) throw new Error('NETLIFY_SITE_ID and NETLIFY_AUTH_TOKEN are required');
const store = getStore('court-availability', { siteID, token });
const previousText = await store.get('latest');
const previous = previousText === null ? undefined : JSON.parse(previousText);
const merged = mergeAvailabilityRefresh(current, isAvailabilitySnapshot(previous) ? previous : undefined);
const snapshot = settings.lta_enabled === true ? merged : withoutLtaAvailability(merged);
if (!snapshot.venue_ids.length || !snapshot.slots.length) throw new Error('Refusing to publish an empty availability snapshot');
await store.setJSON('latest', snapshot);
console.log(`Published ${snapshot.slots.length} slots checked at ${snapshot.generated_at}`);
