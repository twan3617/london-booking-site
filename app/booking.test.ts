import test from 'node:test';
import assert from 'node:assert/strict';
import {
  calendarText,
  matchesVenue,
  releaseDetails,
  relevantHourlyPrice,
} from './booking.ts';

const venue = {
  id: 'hyde-park',
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

test('Any price keeps venues whose price is unknown', () => {
  assert.equal(matchesVenue({ ...venue, price_text: null }, {
    mode: 'after-work', borough: '', query: '', facility: 'any', status: 'all', maxPrice: null,
  }), true);
});

test('a price cap excludes venues without a verified relevant hourly price', () => {
  assert.equal(matchesVenue({ ...venue, price_text: null }, {
    mode: 'after-work', borough: '', query: '', facility: 'any', status: 'all', maxPrice: 20,
  }), false);
});

test('after-work Ready filter includes suitable courts and excludes seasonal courts', () => {
  const filters = { mode: 'after-work' as const, borough: '', query: '', facility: 'any' as const, status: 'ready' as const, maxPrice: null };
  assert.equal(matchesVenue(venue, filters), true);
  assert.equal(matchesVenue({ ...venue, evening_assessment: 'seasonal' }, filters), false);
});

test('evening price prefers an explicitly published floodlit tariff', () => {
  assert.equal(relevantHourlyPrice(venue, 'after-work'), 16);
});

test('a complete published rule gives the exact London release time', () => {
  assert.deepEqual(releaseDetails(venue, '2026-09-21', new Date('2026-09-13T00:00:00Z')), {
    date: '2026-09-14', time: '07:00', open: false,
  });
});

test('an ambiguous release rule does not invent an exact date', () => {
  assert.equal(releaseDetails({ ...venue, release_status: 'partial' }, '2026-09-21'), null);
});

test('calendar reminder uses Europe/London and links to booking', () => {
  const text = calendarText(venue, { date: '2026-09-14', time: '07:00', open: false }, '2026-09-21');
  assert.match(text, /DTSTART;TZID=Europe\/London:20260914T070000/);
  assert.match(text, /TRIGGER:-PT5M/);
  assert.match(text, /https:\/\/example.com\/book/);
});
