export type Mode = 'after-work' | 'weekend';
export type Sport = 'tennis' | 'squash' | 'padel';
export type PriceOption = { label?: string; customer?: 'nonmember' | 'adult_standard'; time_band?: 'peak' | 'off_peak' | 'anytime'; amount_gbp: number; duration_minutes: number; modes: Mode[]; lighting: 'included' | 'unlit' };

export type Venue = {
  id: string;
  sport: Sport;
  name: string;
  borough: string;
  area?: string | null;
  operator?: string | null;
  access: 'pay_and_play' | 'public_access_unconfirmed' | 'free_walk_on' | 'public_pass';
  booking_url?: string | null;
  courts_total?: number | null;
  indoor_courts?: number | null;
  floodlit_courts?: number | null;
  lighting: 'unknown' | 'unlit' | 'floodlit' | 'indoor' | 'mixed';
  hours_text?: string | null;
  evening_assessment: 'suitable' | 'seasonal' | 'unsuitable' | 'unknown';
  evening_notes?: string | null;
  weekend_notes?: string | null;
  price_text?: string | null;
  price_options?: PriceOption[];
  coordinate?: Point | null;
  slot_minutes?: number | null;
  advance_days?: number | null;
  release_time?: string | null;
  release_rule?: string | null;
  release_status: 'published' | 'partial' | 'unknown';
  checked_on: string;
  sources: { url: string; supports: string }[];
  notes?: string | null;
};

export type Filters = {
  sport: Sport;
  mode: Mode;
  borough: string;
  query: string;
  facility: 'any' | 'floodlit' | 'indoor';
  status: 'all' | 'ready' | 'seasonal' | 'checking';
  maxPrice: number | null;
};

export type Release = { date: string; time: string; open: boolean };
export type Point = { latitude: number; longitude: number };
export type AvailabilitySlot = { venue_id: string; court_id: string | null; start_time: string; end_time: string; available: boolean; price_pence: number | null; booking_url: string; detected_at: string; booking_opens_at?: string | null };
export type ProviderAvailabilitySnapshot = { generated_at: string; coverage_start: string; coverage_end: string; venue_ids: string[]; booking_urls: Record<string, string>; slots: AvailabilitySlot[] };
export type AvailabilitySnapshot = ProviderAvailabilitySnapshot & { providers?: Record<string, ProviderAvailabilitySnapshot>; failed_providers?: string[] };

function isProviderAvailabilitySnapshot(value: unknown): value is ProviderAvailabilitySnapshot {
  if (!value || typeof value !== 'object') return false;
  const snapshot = value as Record<string, unknown>;
  if (typeof snapshot.generated_at !== 'string' || !Number.isFinite(Date.parse(snapshot.generated_at))) return false;
  if (typeof snapshot.coverage_start !== 'string' || typeof snapshot.coverage_end !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(snapshot.coverage_start) || !/^\d{4}-\d{2}-\d{2}$/.test(snapshot.coverage_end) || !Number.isFinite(Date.parse(`${snapshot.coverage_start}T12:00:00Z`)) || !Number.isFinite(Date.parse(`${snapshot.coverage_end}T12:00:00Z`)) || snapshot.coverage_start > snapshot.coverage_end) return false;
  if (!Array.isArray(snapshot.venue_ids) || !snapshot.venue_ids.every((id) => typeof id === 'string') || !snapshot.booking_urls || typeof snapshot.booking_urls !== 'object' || Array.isArray(snapshot.booking_urls)) return false;
  if (!Object.values(snapshot.booking_urls).every((url) => typeof url === 'string' && URL.canParse(url) && /^https?:/.test(url))) return false;
  if (!Array.isArray(snapshot.slots)) return false;
  return snapshot.slots.every((slot) => slot && typeof slot === 'object' && typeof slot.venue_id === 'string' && typeof slot.start_time === 'string' && typeof slot.end_time === 'string' && typeof slot.available === 'boolean' && (slot.price_pence === null || Number.isInteger(slot.price_pence)) && typeof slot.booking_url === 'string' && typeof slot.detected_at === 'string');
}

export function isAvailabilitySnapshot(value: unknown): value is AvailabilitySnapshot {
  if (!isProviderAvailabilitySnapshot(value)) return false;
  const snapshot = value as AvailabilitySnapshot;
  if (snapshot.providers && (typeof snapshot.providers !== 'object' || Array.isArray(snapshot.providers) || !Object.values(snapshot.providers).every(isProviderAvailabilitySnapshot))) return false;
  return snapshot.failed_providers === undefined || (Array.isArray(snapshot.failed_providers) && snapshot.failed_providers.every((provider) => typeof provider === 'string'));
}

function combineAvailabilityProviders(providers: Record<string, ProviderAvailabilitySnapshot>, failed_providers: string[] = []): AvailabilitySnapshot {
  const snapshots = Object.values(providers);
  const coverage_start = snapshots.map((snapshot) => snapshot.coverage_start).sort().at(-1);
  const coverage_end = snapshots.map((snapshot) => snapshot.coverage_end).sort()[0];
  if (!coverage_start || !coverage_end || coverage_start > coverage_end) throw new Error('Provider availability windows do not overlap');
  return {
    generated_at: snapshots.map((snapshot) => snapshot.generated_at).sort()[0],
    coverage_start,
    coverage_end,
    venue_ids: [...new Set(snapshots.flatMap((snapshot) => snapshot.venue_ids))],
    booking_urls: Object.assign({}, ...snapshots.map((snapshot) => snapshot.booking_urls)),
    slots: snapshots.flatMap((snapshot) => snapshot.slots).filter((slot) => slot.start_time.slice(0, 10) >= coverage_start && slot.start_time.slice(0, 10) <= coverage_end),
    providers,
    failed_providers,
  };
}

export function mergeAvailabilityRefresh(current: AvailabilitySnapshot, previous?: AvailabilitySnapshot): AvailabilitySnapshot {
  if (!current.providers) return current;
  if (previous && !previous.providers && current.failed_providers?.length) throw new Error('A complete provider refresh is required to replace a legacy snapshot');
  const providers = { ...(previous?.providers ?? {}), ...current.providers };
  for (const [provider, snapshot] of Object.entries(providers)) {
    if (snapshot.coverage_end < current.coverage_start || snapshot.coverage_start > current.coverage_end) delete providers[provider];
  }
  return combineAvailabilityProviders(providers, current.failed_providers);
}

export function freshAvailability(snapshot: AvailabilitySnapshot, now: number, maxAgeMs = 2 * 60 * 60_000): AvailabilitySnapshot {
  if (!snapshot.providers) return now - Date.parse(snapshot.generated_at) <= maxAgeMs ? snapshot : { ...snapshot, slots: [] };
  const providers = Object.fromEntries(Object.entries(snapshot.providers).filter(([, provider]) => now - Date.parse(provider.generated_at) <= maxAgeMs));
  return Object.keys(providers).length ? combineAvailabilityProviders(providers, snapshot.failed_providers) : { ...snapshot, slots: [] };
}

export function availabilityBookingUrl(snapshot: AvailabilitySnapshot, venueId: string, date: string): string | null {
  const base = snapshot.booking_urls[venueId];
  if (base && new URL(base).hostname === 'clubspark.lta.org.uk') {
    const url = new URL(base);
    url.pathname = `${url.pathname.replace(/\/Booking\/BookByDate\/?$/, '').replace(/\/$/, '')}/Booking/BookByDate`;
    url.hash = `?date=${date}`;
    return url.toString();
  }
  if (base && new URL(base).hostname === 'www.lta.org.uk') {
    const url = new URL(base);
    url.searchParams.set('date', date);
    return url.toString();
  }
  if (base && ['www.matchi.se', 'padelmates.se'].includes(new URL(base).hostname)) return base;
  return base ? `${base}/${date}/by-time` : null;
}

export function bookingAccountRequired(snapshot: AvailabilitySnapshot, venueId: string): boolean {
  const base = snapshot.booking_urls[venueId];
  return !!base && ['clubspark.lta.org.uk', 'www.lta.org.uk', 'www.matchi.se', 'padelmates.se'].includes(new URL(base).hostname);
}

export function bookingUrlsForSlots(slots: AvailabilitySlot[]): string[] {
  return [...new Set(slots.map((slot) => slot.booking_url))];
}

export function availabilityForVenue(snapshot: AvailabilitySnapshot, venueId: string, date: string, start: string, durationMinutes: number): { status: 'available' | 'unreleased' | 'none' | 'unsupported' | 'outside'; slots: AvailabilitySlot[] } {
  if (!snapshot.venue_ids.includes(venueId)) return { status: 'unsupported', slots: [] };
  if (date < snapshot.coverage_start || date > snapshot.coverage_end) return { status: 'outside', slots: [] };
  const matching = snapshot.slots.filter((slot) => slot.venue_id === venueId && slot.start_time.slice(0, 10) === date && slot.start_time.slice(11, 16) === start && (Date.parse(slot.end_time) - Date.parse(slot.start_time)) / 60_000 === durationMinutes);
  const available = matching.filter((slot) => slot.available);
  if (available.length) return { status: 'available', slots: available };
  const unreleased = matching.filter((slot) => slot.booking_opens_at && Date.parse(slot.booking_opens_at) > Date.parse(slot.detected_at));
  return unreleased.length ? { status: 'unreleased', slots: unreleased } : { status: 'none', slots: [] };
}

export function availabilityGrid(snapshot: AvailabilitySnapshot, venueIds: string[], durationMinutes: number) {
  const days: string[] = [];
  for (const day = new Date(`${snapshot.coverage_start}T00:00:00Z`); day.toISOString().slice(0, 10) <= snapshot.coverage_end; day.setUTCDate(day.getUTCDate() + 1)) {
    days.push(day.toISOString().slice(0, 10));
  }
  const allowed = new Set(venueIds);
  const times = new Set<string>();
  const cells: Record<string, { venueIds: string[]; courtCount: number }> = {};
  for (const slot of snapshot.slots) {
    const date = slot.start_time.slice(0, 10);
    if (!allowed.has(slot.venue_id) || date < snapshot.coverage_start || date > snapshot.coverage_end || (Date.parse(slot.end_time) - Date.parse(slot.start_time)) / 60_000 !== durationMinutes) continue;
    const time = slot.start_time.slice(11, 16);
    times.add(time);
    if (!slot.available) continue;
    const cell = cells[`${date}|${time}`] ??= { venueIds: [], courtCount: 0 };
    if (!cell.venueIds.includes(slot.venue_id)) cell.venueIds.push(slot.venue_id);
    cell.courtCount++;
  }
  return { days, times: [...times].sort(), cells };
}

export function parseCatalogue(catalogue: { venues: Venue[] }, prices: Record<string, PriceOption[] | null>, coordinates: Record<string, Point | null>): Venue[] {
  const ids = new Set(catalogue.venues.map((venue) => venue.id));
  if (ids.size !== catalogue.venues.length) throw new Error('Duplicate venue IDs');
  for (const id of Object.keys(prices)) if (!ids.has(id)) throw new Error(`Unknown price venue: ${id}`);
  for (const id of Object.keys(coordinates)) if (!ids.has(id)) throw new Error(`Unknown coordinate venue: ${id}`);
  return catalogue.venues.map((venue) => {
    if (!['tennis', 'squash', 'padel'].includes(venue.sport) || !['suitable', 'seasonal', 'unsuitable', 'unknown'].includes(venue.evening_assessment) || !['published', 'partial', 'unknown'].includes(venue.release_status)) throw new Error(`Invalid venue config: ${venue.id}`);
    if (!(venue.id in prices)) throw new Error(`Missing price entry: ${venue.id}`);
    if (!(venue.id in coordinates)) throw new Error(`Missing coordinate entry: ${venue.id}`);
    const rates = prices[venue.id] ?? [];
    if (!Array.isArray(rates) || rates.some((rate) => !Number.isFinite(rate.amount_gbp) || rate.amount_gbp < 0 || !Number.isInteger(rate.duration_minutes) || rate.duration_minutes <= 0)) throw new Error(`Invalid prices: ${venue.id}`);
    return { ...venue, price_options: rates, coordinate: coordinates[venue.id] };
  });
}

export function priceOptionLabel(option: PriceOption): string {
  if (option.label) return option.label;
  if (!option.customer || !option.time_band) return 'Published rate';
  const customer = option.customer === 'adult_standard' ? 'Adult standard' : 'Nonmember';
  const band = option.time_band === 'off_peak' ? 'off-peak' : option.time_band === 'peak' ? 'peak' : 'anytime';
  return `${customer} · ${band}`;
}

export function prettyDate(date: string): string {
  if (!date) return 'Choose a playing date';
  return new Intl.DateTimeFormat('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${date}T12:00:00Z`));
}

export function venueDisplay(venue: Venue, mode: Mode, playDate: string) {
  const status = mode === 'weekend' ? { label: 'Weekend details', tone: 'neutral' } : ({
    suitable: { label: 'Ready after work', tone: 'good' },
    seasonal: { label: 'Seasonal daylight', tone: 'warn' },
    unsuitable: { label: 'Closes too early', tone: 'bad' },
    unknown: { label: 'Needs checking', tone: 'neutral' },
  } as const)[venue.evening_assessment];
  const price = publishedPriceRange(venue, mode);
  const release = releaseDetails(venue, playDate);
  const releaseRule = venue.release_rule ?? (venue.advance_days != null
    ? `Up to ${venue.advance_days} days ahead; ${venue.release_status === 'published' && venue.release_time ? `opens at ${venue.release_time} London time` : 'release time unknown'}.`
    : 'Booking window needs checking.');
  return {
    status,
    lighting: venue.indoor_courts ? `${venue.indoor_courts} indoor` : venue.lighting,
    price: price === null ? 'Check' : price.min === price.max ? `£${price.min}` : `£${price.min}–£${price.max}`,
    priceUnit: price ? (price.duration_minutes === 60 ? 'per hour' : `per ${price.duration_minutes} min`) : venue.slot_minutes ? `for ${venue.slot_minutes} min` : '',
    rates: (venue.price_options ?? []).filter((option) => option.modes.includes(mode)).map((option) => ({ ...option, label: priceOptionLabel(option) })),
    suitability: mode === 'after-work' ? venue.evening_notes : venue.weekend_notes ?? venue.hours_text ?? 'Weekend court hours need checking.',
    release,
    releaseHeading: release?.open ? 'BOOKING WINDOW' : 'BE READY TO BOOK',
    releaseLabel: release ? (release.open ? 'Open — check slots now' : `${prettyDate(release.date)} · ${release.time}`) : 'Release time needs checking',
    releaseRule,
  };
}

export function distanceMiles(from: Point, to: Point): number {
  const radians = (degrees: number) => degrees * Math.PI / 180;
  const latitude = radians(to.latitude - from.latitude);
  const longitude = radians(to.longitude - from.longitude);
  const a = Math.sin(latitude / 2) ** 2 + Math.cos(radians(from.latitude)) * Math.cos(radians(to.latitude)) * Math.sin(longitude / 2) ** 2;
  return 3958.8 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

export function osmEmbedUrl(point: Point): string {
  const padding = 0.008;
  const url = new URL('https://www.openstreetmap.org/export/embed.html');
  url.searchParams.set('bbox', [point.longitude - padding, point.latitude - padding, point.longitude + padding, point.latitude + padding].map((value) => value.toFixed(5)).join(','));
  url.searchParams.set('marker', `${point.latitude.toFixed(5)},${point.longitude.toFixed(5)}`);
  url.searchParams.set('layer', 'mapnik');
  return url.toString();
}

export function relevantHourlyPrice(venue: Venue, mode: Mode): number | null {
  if (venue.price_options?.length) {
    const options = venue.price_options.filter((option) => option.modes.includes(mode));
    return options.length === 1 && options[0].duration_minutes === 60 ? options[0].amount_gbp : null;
  }
  if (venue.sport !== 'tennis') return null;
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

export function publishedPriceRange(venue: Venue, mode: Mode): { min: number; max: number; duration_minutes: number } | null {
  const options = venue.price_options?.filter((option) => option.modes.includes(mode)) ?? [];
  if (options.length) {
    const duration = venue.slot_minutes ?? options[0].duration_minutes;
    const rates = options.filter((option) => option.duration_minutes === duration).map((option) => option.amount_gbp);
    return rates.length ? { min: Math.min(...rates), max: Math.max(...rates), duration_minutes: duration } : null;
  }
  const price = relevantHourlyPrice(venue, mode);
  return price === null ? null : { min: price, max: price, duration_minutes: 60 };
}

export function matchesVenue(venue: Venue, filters: Filters): boolean {
  if (venue.sport !== filters.sport) return false;
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

export function nextSaturday(now: Date): string {
  const date = new Date(`${londonNow(now).slice(0, 10)}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + ((6 - date.getUTCDay() + 7) % 7 || 7));
  return date.toISOString().slice(0, 10);
}

export function releaseDetails(venue: Venue, playDate: string, now = new Date()): Release | null {
  if (!playDate || venue.release_status !== 'published' || venue.advance_days == null || !venue.release_time) return null;
  const date = subtractDays(playDate, venue.advance_days);
  return { date, time: venue.release_time, open: londonNow(now) >= `${date}T${venue.release_time}` };
}

export function withinBookingWindow(venue: Venue, playDate: string, today = londonNow(new Date()).slice(0, 10)): boolean {
  if (!playDate || venue.advance_days == null) return true;
  const daysAhead = (Date.parse(`${playDate}T00:00:00Z`) - Date.parse(`${today}T00:00:00Z`)) / 86_400_000;
  return daysAhead <= venue.advance_days;
}

export function venueDestination(venue: Venue): string {
  return [...new Set([venue.name, venue.area, venue.borough, 'London', 'UK'].filter(Boolean))].join(', ');
}

export function bookingUrlFor(venue: Venue, playDate: string): string | null {
  if (!playDate) return null;
  const booking = venue.booking_url ?? venue.sources[0]?.url;
  return booking?.replace(/\d{4}-\d{2}-\d{2}(?=\/by-time)/, playDate) ?? null;
}

export function directionsUrl(venue: Venue): string {
  const url = new URL('https://www.google.com/maps/dir/');
  url.searchParams.set('api', '1');
  url.searchParams.set('destination', venueDestination(venue));
  return url.toString();
}

function icsEscape(value: string): string {
  return value.replace(/\\/g, '\\\\').replace(/\n/g, '\\n').replace(/,/g, '\\,').replace(/;/g, '\\;');
}

export function calendarText(venue: Venue, release: Release, playDate: string): string {
  const local = `${release.date.replaceAll('-', '')}T${release.time.replace(':', '')}00`;
  const booking = bookingUrlFor(venue, playDate) ?? '';
  return [
    'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//London Court Ready//EN', 'BEGIN:VEVENT',
    `UID:${venue.id}-${playDate}@court-ready`,
    `DTSTART;TZID=Europe/London:${local}`,
    `DTEND;TZID=Europe/London:${local}`,
    `SUMMARY:${icsEscape(`Book ${venue.name} ${venue.sport}`)}`,
    `DESCRIPTION:${icsEscape(`Booking opens for play on ${playDate}. ${booking}`)}`,
    'BEGIN:VALARM', 'ACTION:DISPLAY', 'DESCRIPTION:Booking opens in five minutes', 'TRIGGER:-PT5M',
    'END:VALARM', 'END:VEVENT', 'END:VCALENDAR', '',
  ].join('\r\n');
}
