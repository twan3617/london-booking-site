import { existsSync, readFileSync, renameSync, writeFileSync } from 'node:fs';

const venues = JSON.parse(readFileSync(new URL('../data/venues.json', import.meta.url))).venues;
const output = new URL('../data/coordinates.json', import.meta.url);
const temporary = new URL('../data/coordinates.tmp.json', import.meta.url);
const coordinates = existsSync(output) ? JSON.parse(readFileSync(output)) : {};
const limit = Number(process.argv.find((arg) => arg.startsWith('--limit='))?.split('=')[1] ?? Infinity);
const retryMisses = process.argv.includes('--retry-misses');
const sport = process.argv.find((arg) => arg.startsWith('--sport='))?.split('=')[1];
let requested = 0;

for (const venue of venues) {
  if (sport && venue.sport !== sport) continue;
  if ((venue.id in coordinates && !(retryMisses && coordinates[venue.id] === null)) || requested >= limit) continue;
  const query = venue.geo_query ?? [...new Set(retryMisses ? [venue.name, venue.area, 'London', 'UK'] : [venue.name, venue.borough, 'London', 'UK'])].filter(Boolean).join(', ');
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
  let match = (await response.json())[0];
  let resolvedQuery = query;
  const postcode = venue.geo_query?.match(/\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b/i)?.[0];
  if (!match && postcode) {
    await new Promise((resolve) => setTimeout(resolve, 1100));
    url.searchParams.set('q', postcode);
    const postcodeResponse = await fetch(url, {
      headers: { 'User-Agent': 'CourtReadyLondon/0.1 (one-time venue coordinate collection)' },
      signal: AbortSignal.timeout(15_000),
    });
    if (postcodeResponse.status === 429) throw new Error('Nominatim rate limit reached; stop and resume later.');
    if (!postcodeResponse.ok) throw new Error(`Nominatim returned HTTP ${postcodeResponse.status}.`);
    match = (await postcodeResponse.json())[0];
    if (match) resolvedQuery = postcode;
  }
  coordinates[venue.id] = match ? {
    latitude: Number(match.lat), longitude: Number(match.lon),
    display_name: match.display_name, query: resolvedQuery, checked_on: new Date().toISOString().slice(0, 10),
  } : null;
  writeFileSync(temporary, `${JSON.stringify(coordinates, null, 2)}\n`);
  renameSync(temporary, output);
  requested += 1;
  if (requested % 20 === 0 || requested === limit) console.log(`${Object.keys(coordinates).length}/${venues.length} checked`);
  await new Promise((resolve) => setTimeout(resolve, 1100));
}

console.log(`Saved ${Object.values(coordinates).filter(Boolean).length} coordinates from ${Object.keys(coordinates).length} checked venues.`);
