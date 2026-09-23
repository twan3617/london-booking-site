import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  calendarText,
  bookingUrlFor,
  directionsUrl,
  distanceMiles,
  availabilityForVenue,
  availabilityBookingUrl,
  bookingAccountRequired,
  osmEmbedUrl,
  matchesVenue,
  publishedPriceRange,
  parseCatalogue,
  venueDisplay,
  releaseDetails,
  relevantHourlyPrice,
  withinBookingWindow,
  type Venue,
  type AvailabilitySnapshot,
} from './booking.ts';

const venue: Venue = {
  id: 'hyde-park',
  sport: 'tennis' as const,
  name: 'Hyde Park',
  borough: 'Westminster',
  access: 'pay_and_play',
  booking_url: 'https://example.com/book',
  indoor_courts: 0,
  lighting: 'floodlit',
  evening_assessment: 'suitable',
  price_text: 'Peak £12/hour; floodlit tariff £16/hour.',
  advance_days: 7,
  release_time: '07:00',
  release_status: 'published',
  release_rule: 'Seven days ahead at 07:00.',
  checked_on: '2026-09-14',
  sources: [{ url: 'https://example.com/source', supports: 'Details' }],
};

const availability: AvailabilitySnapshot = {
  generated_at: '2026-09-23T20:00:00Z',
  coverage_start: '2026-09-23',
  coverage_end: '2026-09-29',
  venue_ids: ['hyde-park'],
  booking_urls: { 'hyde-park': 'https://example.com/book' },
  slots: [
    { venue_id: 'hyde-park', court_id: '1', start_time: '2026-09-26T19:00:00+01:00', end_time: '2026-09-26T20:00:00+01:00', available: true, price_pence: 1200, booking_url: 'https://example.com/26', detected_at: '2026-09-23T20:00:00Z' },
    { venue_id: 'hyde-park', court_id: '2', start_time: '2026-09-26T19:00:00+01:00', end_time: '2026-09-26T20:00:00+01:00', available: false, price_pence: 1200, booking_url: 'https://example.com/26', detected_at: '2026-09-23T20:00:00Z' },
  ],
};

test('time-first search returns only bookable slots at the exact start and duration', () => {
  assert.deepEqual(availabilityForVenue(availability, 'hyde-park', '2026-09-26', '19:00', 60), {
    status: 'available', slots: [availability.slots[0]],
  });
  assert.deepEqual(availabilityForVenue(availability, 'hyde-park', '2026-09-26', '18:00', 60), { status: 'none', slots: [] });
  assert.deepEqual(availabilityForVenue(availability, 'hyde-park', '2026-09-26', '19:00', 90), { status: 'none', slots: [] });
});

test('time-first search separates no slots, unsupported venues and dates outside coverage', () => {
  assert.deepEqual(availabilityForVenue(availability, 'hyde-park', '2026-09-26', '10:00', 60), { status: 'none', slots: [] });
  assert.deepEqual(availabilityForVenue(availability, 'another-venue', '2026-09-26', '19:00', 60), { status: 'unsupported', slots: [] });
  assert.deepEqual(availabilityForVenue(availability, 'hyde-park', '2026-09-30', '19:00', 60), { status: 'outside', slots: [] });
});

test('time-first search reports booking that had not opened at the last check', () => {
  const unreleased = { ...availability.slots[1], booking_opens_at: '2026-09-24T21:00:00Z' };
  const snapshot = { ...availability, slots: [unreleased] };
  assert.deepEqual(availabilityForVenue(snapshot, 'hyde-park', '2026-09-26', '19:00', 60), {
    status: 'unreleased', slots: [unreleased],
  });
});

test('time-first booking link reaches the dated provider page without a free slot', () => {
  assert.equal(availabilityBookingUrl(availability, 'hyde-park', '2026-09-26'), 'https://example.com/book/2026-09-26/by-time');
  assert.equal(availabilityBookingUrl(availability, 'another-venue', '2026-09-26'), null);
});

test('ClubSpark opens the selected booking-sheet date and requires an account', () => {
  const snapshot = {
    ...availability,
    booking_urls: { 'hyde-park': 'https://clubspark.lta.org.uk/BarkingPark' },
    slots: [{ ...availability.slots[0], venue_id: 'hyde-park', court_id: 'court-1', start_time: '2026-09-26T07:00:00+01:00', end_time: '2026-09-26T08:00:00+01:00', available: true }],
  };
  assert.equal(availabilityBookingUrl(snapshot, 'hyde-park', '2026-09-26'), 'https://clubspark.lta.org.uk/BarkingPark/Booking/BookByDate#?date=2026-09-26');
  assert.equal(availabilityForVenue(snapshot, 'hyde-park', '2026-09-26', '07:00', 60).status, 'available');
  assert.equal(availabilityBookingUrl({ ...snapshot, booking_urls: { 'hyde-park': 'https://clubspark.lta.org.uk/BarkingPark/Booking/BookByDate' } }, 'hyde-park', '2026-09-26'), 'https://clubspark.lta.org.uk/BarkingPark/Booking/BookByDate#?date=2026-09-26');
  assert.equal(bookingAccountRequired(snapshot, 'hyde-park'), true);
  assert.equal(bookingAccountRequired(availability, 'hyde-park'), false);
});

test('Any price keeps venues whose price is unknown', () => {
  assert.equal(matchesVenue({ ...venue, price_text: null }, {
    sport: 'tennis', mode: 'after-work', borough: '', query: '', facility: 'any', status: 'all', maxPrice: null,
  }), true);
});

test('a price cap excludes venues without a verified relevant hourly price', () => {
  assert.equal(matchesVenue({ ...venue, price_text: null }, {
    sport: 'tennis', mode: 'after-work', borough: '', query: '', facility: 'any', status: 'all', maxPrice: 20,
  }), false);
});

test('after-work Ready filter includes suitable courts and excludes seasonal courts', () => {
  const filters = { sport: 'tennis' as const, mode: 'after-work' as const, borough: '', query: '', facility: 'any' as const, status: 'ready' as const, maxPrice: null };
  assert.equal(matchesVenue(venue, filters), true);
  assert.equal(matchesVenue({ ...venue, evening_assessment: 'seasonal' }, filters), false);
});

test('evening price prefers an explicitly published floodlit tariff', () => {
  assert.equal(relevantHourlyPrice(venue, 'after-work'), 16);
});

test('sport filter keeps squash and padel separate', () => {
  const filters = { sport: 'squash' as const, mode: 'weekend' as const, borough: '', query: '', facility: 'any' as const, status: 'all' as const, maxPrice: null };
  assert.equal(matchesVenue(venue, filters), false);
  assert.equal(matchesVenue({ ...venue, sport: 'squash' }, filters), true);
});

test('published public rates form an indicative range', () => {
  assert.deepEqual(publishedPriceRange({ ...venue, price_options: [
    { label: 'Daylight', amount_gbp: 8, duration_minutes: 60, modes: ['weekend'], lighting: 'unlit' },
    { label: 'Floodlit', amount_gbp: 12, duration_minutes: 60, modes: ['after-work', 'weekend'], lighting: 'included' },
  ] }, 'weekend'), { min: 8, max: 12, duration_minutes: 60 });
});

test('after-work range excludes daylight-only rates', () => {
  assert.deepEqual(publishedPriceRange({ ...venue, price_options: [
    { label: 'Daylight', amount_gbp: 8, duration_minutes: 60, modes: ['weekend'], lighting: 'unlit' },
    { label: 'Floodlit', amount_gbp: 12, duration_minutes: 60, modes: ['after-work', 'weekend'], lighting: 'included' },
  ] }, 'after-work'), { min: 12, max: 12, duration_minutes: 60 });
});

test('price cap ignores indicative ranges with more than one possible rate', () => {
  const varied: Venue = { ...venue, price_options: [
    { label: 'Peak', amount_gbp: 26, duration_minutes: 60, modes: ['after-work'], lighting: 'included' },
    { label: 'Off-peak', amount_gbp: 33, duration_minutes: 60, modes: ['after-work'], lighting: 'included' },
  ] };
  assert.equal(relevantHourlyPrice(varied, 'after-work'), null);
});

test('a 40-minute squash price stays a booking price rather than an hourly price', () => {
  const squash: Venue = { ...venue, sport: 'squash', slot_minutes: 40, price_options: [
    { label: 'Nonmember peak', amount_gbp: 12.85, duration_minutes: 40, modes: ['after-work', 'weekend'], lighting: 'included' },
  ] };
  assert.deepEqual(publishedPriceRange(squash, 'after-work'), { min: 12.85, max: 12.85, duration_minutes: 40 });
  assert.equal(relevantHourlyPrice(squash, 'after-work'), null);
});

test('a headline range never combines 60- and 90-minute padel bookings', () => {
  const padel: Venue = { ...venue, sport: 'padel', slot_minutes: 60, price_options: [
    { label: '60 minutes', amount_gbp: 58.68, duration_minutes: 60, modes: ['weekend'], lighting: 'included' },
    { label: '90 minutes', amount_gbp: 88, duration_minutes: 90, modes: ['weekend'], lighting: 'included' },
  ] };
  assert.deepEqual(publishedPriceRange(padel, 'weekend'), { min: 58.68, max: 58.68, duration_minutes: 60 });
});

test('dated booking links follow the selected playing date', () => {
  assert.equal(bookingUrlFor({ ...venue, booking_url: 'https://example.com/tennis/2026-09-19/by-time' }, '2026-09-26'), 'https://example.com/tennis/2026-09-26/by-time');
});

test('a complete published rule gives the exact London release time', () => {
  assert.deepEqual(releaseDetails(venue, '2026-09-21', new Date('2026-09-13T00:00:00Z')), {
    date: '2026-09-14', time: '07:00', open: false,
  });
});

test('an ambiguous release rule does not invent an exact date', () => {
  assert.equal(releaseDetails({ ...venue, release_status: 'partial' }, '2026-09-21'), null);
});

test('catalogue parser keeps structured facts and renders booking labels', () => {
  const parsed = parseCatalogue({ venues: [{ ...venue, release_status: 'partial', advance_days: 6, release_time: null, release_rule: null }] }, {
    'hyde-park': [{ customer: 'nonmember', time_band: 'peak', amount_gbp: 12.25, duration_minutes: 40, modes: ['after-work'], lighting: 'included' }],
  }, { 'hyde-park': null });
  assert.equal(parsed[0].advance_days, 6);
  assert.equal(parsed[0].coordinate, null);
  assert.equal(venueDisplay(parsed[0], 'after-work', '2026-09-21').releaseRule, 'Up to 6 days ahead; release time unknown.');
  assert.equal(venueDisplay(parsed[0], 'after-work', '2026-09-21').rates[0].label, 'Nonmember · peak');
});

test('static data joins have matching venue IDs and explicit empty rates', () => {
  const load = (name: string) => JSON.parse(readFileSync(new URL(`../data/${name}.json`, import.meta.url), 'utf8'));
  const venues = parseCatalogue(load('venues'), load('prices'), load('coordinates'));
  assert.ok(venues.length > 0);
  assert.ok(venues.every((item) => Array.isArray(item.price_options) && item.coordinate !== undefined));
  assert.throws(() => parseCatalogue({ venues: [venue] }, { orphan: [] }, { 'hyde-park': null }), /Unknown price venue/);
  assert.throws(() => parseCatalogue({ venues: [venue] }, {}, { 'hyde-park': null }), /Missing price entry/);
  assert.throws(() => parseCatalogue({ venues: [venue] }, { 'hyde-park': null }, {}), /Missing coordinate entry/);
});

test('calendar reminder uses Europe/London and links to booking', () => {
  const text = calendarText(venue, { date: '2026-09-14', time: '07:00', open: false }, '2026-09-21');
  assert.match(text, /DTSTART;TZID=Europe\/London:20260914T070000/);
  assert.match(text, /TRIGGER:-PT5M/);
  assert.match(text, /https:\/\/example.com\/book/);
});

test('a seven-day venue remains visible for the seventh day', () => {
  assert.equal(withinBookingWindow(venue, '2026-09-21', '2026-09-14'), true);
});

test('a seven-day venue is hidden for the eighth day', () => {
  assert.equal(withinBookingWindow(venue, '2026-09-22', '2026-09-14'), false);
});

test('venues with an unknown advance window remain visible', () => {
  assert.equal(withinBookingWindow({ ...venue, advance_days: null }, '2026-10-01', '2026-09-14'), true);
});

test('directions leave the origin open for the device current location', () => {
  const url = new URL(directionsUrl({ ...venue, area: 'Hyde Park' }));
  assert.equal(url.origin + url.pathname, 'https://www.google.com/maps/dir/');
  assert.equal(url.searchParams.get('api'), '1');
  assert.equal(url.searchParams.get('origin'), null);
  assert.equal(url.searchParams.get('destination'), 'Hyde Park, Westminster, London, UK');
});

test('distance uses great-circle miles', () => {
  assert.equal(distanceMiles({ latitude: 51.5, longitude: -0.1 }, { latitude: 51.6, longitude: -0.1 }).toFixed(1), '6.9');
});

test('distance from a point to itself is zero', () => {
  assert.equal(distanceMiles({ latitude: 51.5, longitude: -0.1 }, { latitude: 51.5, longitude: -0.1 }), 0);
});

test('map embed centres an OpenStreetMap marker on the court', () => {
  const url = new URL(osmEmbedUrl({ latitude: 51.5, longitude: -0.1 }));
  assert.equal(url.origin + url.pathname, 'https://www.openstreetmap.org/export/embed.html');
  assert.equal(url.searchParams.get('marker'), '51.50000,-0.10000');
  assert.equal(url.searchParams.get('bbox'), '-0.10800,51.49200,-0.09200,51.50800');
});
