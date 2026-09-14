export type Mode = 'after-work' | 'weekend';

export type Venue = {
  id: string;
  name: string;
  borough: string;
  area?: string | null;
  operator?: string | null;
  access: string;
  booking_url?: string | null;
  courts_total?: number | null;
  indoor_courts?: number | null;
  floodlit_courts?: number | null;
  lighting: string;
  hours_text?: string | null;
  evening_assessment: string;
  evening_notes?: string | null;
  weekend_notes?: string | null;
  price_text?: string | null;
  advance_days?: number | null;
  release_time?: string | null;
  release_rule?: string | null;
  release_status: string;
  checked_on: string;
  sources: { url: string; supports: string }[];
  notes?: string | null;
};

export type Filters = {
  mode: Mode;
  borough: string;
  query: string;
  facility: 'any' | 'floodlit' | 'indoor';
  status: 'all' | 'ready' | 'seasonal' | 'checking';
  maxPrice: number | null;
};

export type Release = { date: string; time: string; open: boolean };

export function relevantHourlyPrice(venue: Venue, mode: Mode): number | null {
  const text = venue.price_text;
  if (!text) return null;
  const hourly = [...text.matchAll(/£(\d+(?:\.\d{1,2})?)(?=[^£]{0,24}(?:\/\s*(?:hour|hr|h)\b|per hour))/gi)];
  if (!hourly.length) return null;
  if (mode === 'after-work') {
    const lit = [...text.matchAll(/(?:floodlit|light(?:ing)?)[^£]{0,30}£(\d+(?:\.\d{1,2})?)(?=[^£]{0,24}(?:\/\s*(?:hour|hr|h)\b|per hour))/gi)].at(-1);
    if (lit) return Number(lit[1]);
  }
  return hourly.length === 1 ? Number(hourly[0][1]) : null;
}

export function matchesVenue(venue: Venue, filters: Filters): boolean {
  const query = filters.query.trim().toLowerCase();
  if (query && !`${venue.name} ${venue.borough} ${venue.area ?? ''}`.toLowerCase().includes(query)) return false;
  if (filters.borough && venue.borough !== filters.borough) return false;
  if (filters.facility === 'indoor' && !(venue.indoor_courts && venue.indoor_courts > 0)) return false;
  if (filters.facility === 'floodlit' && !['floodlit', 'mixed'].includes(venue.lighting)) return false;
  if (filters.status === 'ready' && venue.evening_assessment !== 'suitable') return false;
  if (filters.status === 'seasonal' && venue.evening_assessment !== 'seasonal') return false;
  if (filters.status === 'checking' && venue.evening_assessment !== 'unknown') return false;
  if (filters.maxPrice !== null) {
    const price = relevantHourlyPrice(venue, filters.mode);
    if (price === null || price > filters.maxPrice) return false;
  }
  return true;
}

function subtractDays(date: string, days: number): string {
  const [year, month, day] = date.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1, day - days)).toISOString().slice(0, 10);
}

function londonNow(now: Date): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Europe/London', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(now);
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? '';
  return `${get('year')}-${get('month')}-${get('day')}T${get('hour')}:${get('minute')}`;
}

export function releaseDetails(venue: Venue, playDate: string, now = new Date()): Release | null {
  if (venue.release_status !== 'published' || venue.advance_days == null || !venue.release_time) return null;
  const date = subtractDays(playDate, venue.advance_days);
  return { date, time: venue.release_time, open: londonNow(now) >= `${date}T${venue.release_time}` };
}

function icsEscape(value: string): string {
  return value.replace(/\\/g, '\\\\').replace(/\n/g, '\\n').replace(/,/g, '\\,').replace(/;/g, '\\;');
}

export function calendarText(venue: Venue, release: Release, playDate: string): string {
  const local = `${release.date.replaceAll('-', '')}T${release.time.replace(':', '')}00`;
  const booking = venue.booking_url ?? venue.sources[0]?.url ?? '';
  return [
    'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//London Court Ready//EN', 'BEGIN:VEVENT',
    `UID:${venue.id}-${playDate}@court-ready`,
    `DTSTART;TZID=Europe/London:${local}`,
    `DTEND;TZID=Europe/London:${local}`,
    `SUMMARY:${icsEscape(`Book ${venue.name} tennis`)}`,
    `DESCRIPTION:${icsEscape(`Booking opens for play on ${playDate}. ${booking}`)}`,
    'BEGIN:VALARM', 'ACTION:DISPLAY', 'DESCRIPTION:Booking opens in five minutes', 'TRIGGER:-PT5M',
    'END:VALARM', 'END:VEVENT', 'END:VCALENDAR', '',
  ].join('\r\n');
}
