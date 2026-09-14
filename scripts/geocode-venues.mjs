import { existsSync, readFileSync, renameSync, writeFileSync } from 'node:fs';

const venues = JSON.parse(readFileSync(new URL('../data/venues.json', import.meta.url))).venues;
const output = new URL('../data/coordinates.json', import.meta.url);
const temporary = new URL('../data/coordinates.tmp.json', import.meta.url);
const coordinates = existsSync(output) ? JSON.parse(readFileSync(output)) : {};
const limit = Number(process.argv.find((arg) => arg.startsWith('--limit='))?.split('=')[1] ?? Infinity);
const retryMisses = process.argv.includes('--retry-misses');
let requested = 0;

for (const venue of venues) {
  if ((venue.id in coordinates && !(retryMisses && coordinates[venue.id] === null)) || requested >= limit) continue;
  const query = [...new Set(retryMisses ? [venue.name, venue.area, 'London', 'UK'] : [venue.name, venue.borough, 'London', 'UK'])].filter(Boolean).join(', ');
  const url = new URL('https://nominatim.openstreetmap.org/search');
  url.search = new URLSearchParams({
    q: query, format: 'jsonv2', addressdetails: '1', limit: '3',
    countrycodes: 'gb', viewbox: '-0.5103,51.6919,0.3340,51.2868', bounded: '1',
  }).toString();

  let response;
  try {
    response = await fetch(url, {
      headers: { 'User-Agent': 'CourtReadyLondon/0.1 (one-time venue coordinate collection)' },
      signal: AbortSignal.timeout(15_000),
    });
  } catch {
    console.warn(`Timed out: ${venue.name}`);
    requested += 1;
    await new Promise((resolve) => setTimeout(resolve, 1100));
    continue;
  }
  if (response.status === 429) throw new Error('Nominatim rate limit reached; stop and resume later.');
  if (!response.ok) throw new Error(`Nominatim returned HTTP ${response.status}.`);
  const match = (await response.json())[0];
  coordinates[venue.id] = match ? {
    latitude: Number(match.lat), longitude: Number(match.lon),
    display_name: match.display_name, query, checked_on: new Date().toISOString().slice(0, 10),
  } : null;
  writeFileSync(temporary, `${JSON.stringify(coordinates, null, 2)}\n`);
  renameSync(temporary, output);
  requested += 1;
  if (requested % 20 === 0 || requested === limit) console.log(`${Object.keys(coordinates).length}/${venues.length} checked`);
  await new Promise((resolve) => setTimeout(resolve, 1100));
}

console.log(`Saved ${Object.values(coordinates).filter(Boolean).length} coordinates from ${Object.keys(coordinates).length} checked venues.`);
