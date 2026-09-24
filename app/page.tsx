'use client';

import { useEffect, useMemo, useState } from 'react';
import catalogue from '../data/venues.json';
import coordinateData from '../data/coordinates.json';
import priceData from '../data/prices.json';
import { availabilityForVenue, availabilityGrid, bookingAccountRequired, bookingUrlsForSlots, bookingUrlFor, calendarText, directionsUrl, distanceMiles, freshAvailability, isAvailabilitySnapshot, matchesVenue, nextSaturday, osmEmbedUrl, parseCatalogue, prettyDate, releaseDetails, venueDisplay, venueWithAvailabilityMetadata, withinBookingWindow, type AvailabilitySnapshot, type Filters, type Mode, type Point, type PriceOption, type Sport, type Venue } from './booking';

const priceOptions = priceData as Record<string, PriceOption[] | null>;
const venues = parseCatalogue(catalogue as unknown as { venues: Venue[] }, priceOptions, coordinateData as Record<string, Point | null>);
const EMPTY_AVAILABILITY: AvailabilitySnapshot = { generated_at: '1970-01-01T00:00:00Z', coverage_start: '1970-01-01', coverage_end: '1970-01-01', venue_ids: [], booking_urls: {}, slots: [] };
const PROVIDER_NAMES: Record<string, string> = {
  'api.matchi.com': 'MATCHi',
  'better-admin.org.uk': 'Better',
  'fastapi-production-fargate.padelmates.io': 'Padel Mates',
  'playtomic.com': 'Playtomic',
  'www.lta.org.uk': 'LTA Play',
};
const londonDateTime = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/London' });

export default function Home() {
  const [view, setView] = useState<'locations' | 'time'>('locations');
  const [sport, setSport] = useState<Sport>('tennis');
  const [mode, setMode] = useState<Mode>('after-work');
  const [playDate, setPlayDate] = useState('');
  const [startTime, setStartTime] = useState('19:00');
  const [durationMinutes, setDurationMinutes] = useState(60);
  const [query, setQuery] = useState('');
  const [borough, setBorough] = useState('');
  const [facility, setFacility] = useState<Filters['facility']>('any');
  const [status, setStatus] = useState<Filters['status']>('all');
  const [maxPrice, setMaxPrice] = useState('');
  const [favourites, setFavourites] = useState<string[]>([]);
  const [favouritesOnly, setFavouritesOnly] = useState(false);
  const [limit, setLimit] = useState(24);
  const [sortOrder, setSortOrder] = useState<'recommended' | 'distance'>('recommended');
  const [userLocation, setUserLocation] = useState<Point | null>(null);
  const [locationMessage, setLocationMessage] = useState('');
  const [currentTime, setCurrentTime] = useState<number | null>(null);
  const [snapshot, setSnapshot] = useState<AvailabilitySnapshot | null>(null);
  const [availabilityError, setAvailabilityError] = useState(false);
  const availability = useMemo(() => snapshot && currentTime !== null ? freshAvailability(snapshot, currentTime) : snapshot ?? EMPTY_AVAILABILITY, [snapshot, currentTime]);
  const currentVenues = useMemo(() => venues.map((venue) => venueWithAvailabilityMetadata(venue, availability)), [availability]);
  const sportVenueIds = useMemo(() => new Set(currentVenues.filter((venue) => venue.sport === sport).map((venue) => venue.id)), [sport, currentVenues]);
  const relevantProviders = useMemo(() => Object.entries(snapshot?.providers ?? {}).filter(([, provider]) => provider.venue_ids.some((id) => sportVenueIds.has(id))), [snapshot, sportVenueIds]);
  const providerChecks = relevantProviders.map(([host, provider]) => `${PROVIDER_NAMES[host] ?? host} ${londonDateTime.format(new Date(provider.generated_at))}${snapshot?.failed_providers?.includes(host) ? ' (using previous)' : currentTime !== null && currentTime - Date.parse(provider.generated_at) > 2 * 60 * 60_000 ? ' (stale)' : ''}`).join(' · ');
  const checkedAt = snapshot ? londonDateTime.format(new Date(snapshot.generated_at)) : '';
  const boroughs = useMemo(() => [...new Set(currentVenues.filter((venue) => venue.sport === sport).map((venue) => venue.borough))].sort(), [sport, currentVenues]);
  const checkedVenueIds = useMemo(() => new Set(currentVenues.filter((venue) => venue.sport === sport && availability.venue_ids.includes(venue.id)).map((venue) => venue.id)), [sport, availability, currentVenues]);
  const checkedDurations = useMemo(() => [...new Set(availability.slots.filter((slot) => checkedVenueIds.has(slot.venue_id)).map((slot) => (Date.parse(slot.end_time) - Date.parse(slot.start_time)) / 60_000))].sort((a, b) => a - b), [checkedVenueIds, availability]);
  const shownDuration = checkedDurations.includes(durationMinutes) ? durationMinutes : checkedDurations[0] ?? durationMinutes;
  const checkedVenues = checkedVenueIds.size;
  const snapshotOld = currentTime !== null && currentTime - Date.parse(availability.generated_at) > 60 * 60_000;
  const snapshotTooOld = currentTime !== null && (snapshot?.providers ? relevantProviders.length > 0 && relevantProviders.every(([, provider]) => currentTime - Date.parse(provider.generated_at) > 2 * 60 * 60_000) : currentTime - Date.parse(availability.generated_at) > 2 * 60 * 60_000);
  const londonToday = currentTime === null ? '' : new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/London', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(currentTime));
  const snapshotExpired = londonToday > availability.coverage_end;
  const durationChecked = checkedDurations.includes(shownDuration);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      try { setFavourites(JSON.parse(localStorage.getItem('court-ready-favourites') ?? '[]')); } catch { /* Ignore damaged local preferences. */ }
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    const update = () => setCurrentTime(Date.now());
    const first = window.setTimeout(() => { update(); setPlayDate(nextSaturday(new Date())); }, 0);
    const interval = window.setInterval(update, 60_000);
    return () => { window.clearTimeout(first); window.clearInterval(interval); };
  }, []);

  useEffect(() => {
    let active = true;
    let pending = false;
    async function refresh() {
      if (pending) return;
      pending = true;
      try {
        const response = await fetch('/.netlify/functions/availability', { cache: 'no-store' });
        if (!response.ok) throw new Error('Availability request failed');
        const candidate: unknown = await response.json();
        if (!isAvailabilitySnapshot(candidate)) throw new Error('Invalid availability snapshot');
        if (active) { setSnapshot(candidate); setAvailabilityError(false); }
      } catch {
        if (active) setAvailabilityError(true);
      } finally {
        pending = false;
      }
    }
    void refresh();
    const interval = window.setInterval(() => { if (document.visibilityState === 'visible') void refresh(); }, 5 * 60_000);
    const onVisible = () => { if (document.visibilityState === 'visible') void refresh(); };
    document.addEventListener('visibilitychange', onVisible);
    return () => { active = false; window.clearInterval(interval); document.removeEventListener('visibilitychange', onVisible); };
  }, []);

  const results = useMemo(() => {
    const filters: Filters = { sport, mode, borough, query, facility, status: view === 'time' || mode === 'weekend' ? 'all' : status, maxPrice: view === 'time' || sport !== 'tennis' || maxPrice === '' ? null : Number(maxPrice) };
    return currentVenues
      .filter((venue) => matchesVenue(venue, filters) && (view === 'time' || withinBookingWindow(venue, playDate)) && (!favouritesOnly || favourites.includes(venue.id)))
      .sort((a, b) => {
        if (sortOrder === 'distance' && userLocation) {
          const aDistance = a.coordinate ? distanceMiles(userLocation, a.coordinate) : Infinity;
          const bDistance = b.coordinate ? distanceMiles(userLocation, b.coordinate) : Infinity;
          return aDistance - bDistance || a.name.localeCompare(b.name);
        }
        return Number(favourites.includes(b.id)) - Number(favourites.includes(a.id)) || ['suitable', 'seasonal', 'unknown', 'unsuitable'].indexOf(a.evening_assessment) - ['suitable', 'seasonal', 'unknown', 'unsuitable'].indexOf(b.evening_assessment) || a.name.localeCompare(b.name);
      });
  }, [view, sport, mode, playDate, borough, query, facility, status, maxPrice, favourites, favouritesOnly, sortOrder, userLocation, currentVenues]);
  const grid = useMemo(() => availabilityGrid(availability, results.map((venue) => venue.id), shownDuration), [availability, results, shownDuration]);
  const selectedCell = grid.cells[`${playDate}|${startTime}`];
  const selectedVenues = results.filter((venue) => selectedCell?.venueIds.includes(venue.id));

  function toggleFavourite(id: string) {
    const next = favourites.includes(id) ? favourites.filter((item) => item !== id) : [...favourites, id];
    setFavourites(next);
    localStorage.setItem('court-ready-favourites', JSON.stringify(next));
  }

  function downloadReminder(venue: Venue) {
    const release = releaseDetails(venue, playDate);
    if (!release) return;
    const url = URL.createObjectURL(new Blob([calendarText(venue, release, playDate)], { type: 'text/calendar' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `book-${venue.id}-${playDate}.ics`;
    link.click();
    URL.revokeObjectURL(url);
  }

  function chooseSort(value: 'recommended' | 'distance') {
    if (value === 'recommended') { setSortOrder(value); setLocationMessage(''); return; }
    if (!navigator.geolocation) { setLocationMessage('Location is unavailable in this browser.'); return; }
    setLocationMessage('Finding your location…');
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => { setUserLocation({ latitude: coords.latitude, longitude: coords.longitude }); setSortOrder('distance'); setLocationMessage(''); },
      () => setLocationMessage('Allow location access to sort by distance.'),
      { enableHighAccuracy: false, maximumAge: 300_000, timeout: 10_000 },
    );
  }

  return <main>
    <header className="hero">
      <h1>Public Courts Across London</h1>
    </header>

    <section className="planner" aria-label="Court filters">
      <div className="browse-tabs" role="group" aria-label="Browse by">
        <button type="button" className={view === 'locations' ? 'active' : ''} aria-pressed={view === 'locations'} onClick={() => { setView('locations'); setLimit(24); }}>Browse locations</button>
        <button type="button" className={view === 'time' ? 'active' : ''} aria-pressed={view === 'time'} onClick={() => { setView('time'); setLimit(24); }}>Find a time</button>
      </div>
      <div className="sport-tabs" role="group" aria-label="Sport">{(['tennis', 'squash', 'padel'] as const).map((item) => <button key={item} className={sport === item ? 'active' : ''} onClick={() => { setSport(item); setBorough(''); setFacility('any'); setLimit(24); }}>{item}</button>)}</div>
      {view === 'locations' && <div className="mode-tabs" role="group" aria-label="When do you want to play?">
        <button className={mode === 'after-work' ? 'active' : ''} onClick={() => { setMode('after-work'); setStatus('ready'); }}>After work <small>19:00–21:00</small></button>
        <button className={mode === 'weekend' ? 'active' : ''} onClick={() => setMode('weekend')}>Weekend daytime <small>09:00–17:00</small></button>
      </div>}
      <div className={`filter-grid ${view === 'time' ? 'time-filters' : ''}`}>
        {view === 'locations' && <label>Playing date<input type="date" value={playDate} onChange={(event) => { if (event.target.value) setPlayDate(event.target.value); }} /></label>}
        {view === 'time' && checkedDurations.length > 0 && <label>Duration<select value={shownDuration} onChange={(event) => setDurationMinutes(Number(event.target.value))}>{checkedDurations.map((minutes) => <option key={minutes} value={minutes}>{minutes} minutes</option>)}</select></label>}
        <label>Search<input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Court, area or borough" /></label>
        <label>Borough<select value={borough} onChange={(event) => setBorough(event.target.value)}><option value="">All London</option>{boroughs.map((item) => <option key={item}>{item}</option>)}</select></label>
        <label>Facility<select value={facility} onChange={(event) => setFacility(event.target.value as Filters['facility'])}><option value="any">Any facility</option><option value="floodlit">Floodlit outdoor</option><option value="indoor">Indoor</option></select></label>
        {view === 'locations' && mode === 'after-work' && <label>Evening status<select value={status} onChange={(event) => setStatus(event.target.value as Filters['status'])}><option value="ready">Ready after work</option><option value="seasonal">Seasonal daylight</option><option value="checking">Needs checking</option><option value="all">Every status</option></select></label>}
        {view === 'locations' && sport === 'tennis' && <label>Max £ / court / hour<input type="number" min="0" step="1" value={maxPrice} onChange={(event) => setMaxPrice(event.target.value)} placeholder="Any price" /></label>}
      </div>
    </section>

    <section className="results">
      <div className="results-head"><div><p className="eyebrow">{view === 'time' ? snapshot ? `${prettyDate(availability.coverage_start)}–${prettyDate(availability.coverage_end)} · ${shownDuration} min` : 'Latest availability' : prettyDate(playDate)}</p><h2>{view === 'time' ? 'Availability by time' : `${results.length} courts match`}</h2></div><div className="result-tools"><label>Sort<select value={sortOrder} onChange={(event) => chooseSort(event.target.value as 'recommended' | 'distance')}><option value="recommended">Recommended</option><option value="distance">Nearest to me</option></select></label><button className={`favourites-toggle ${favouritesOnly ? 'active' : ''}`} onClick={() => setFavouritesOnly(!favouritesOnly)}>★ Favourites {favourites.length || ''}</button></div></div>
      {view === 'time' && snapshot && <p className="availability-note" role="status">{providerChecks ? `Provider checks: ${providerChecks}. ` : `Last checked ${checkedAt} London time. `}{checkedVenues} of {currentVenues.filter((venue) => venue.sport === sport).length} {sport} locations checked for {availability.coverage_start}–{availability.coverage_end}. {availabilityError ? 'The latest refresh could not be loaded. ' : ''}{snapshotExpired ? 'This snapshot has expired. ' : snapshotTooOld ? 'All provider snapshots are over two hours old. ' : snapshotOld && !snapshot.providers ? 'This snapshot is over one hour old. ' : ''}{!durationChecked && checkedVenues ? `No ${sport} durations were returned. ` : ''}Slots can change; confirm on the booking site.</p>}
      {locationMessage && <p className="location-message" role="status">{locationMessage}</p>}
      {view === 'time' && !snapshot && <div className="empty" role="status"><h3>{availabilityError ? 'Availability unavailable' : 'Checking availability…'}</h3><p>{availabilityError ? 'Could not load the latest check. Try again shortly or browse locations.' : 'Loading the latest court check.'}</p></div>}
      {view === 'time' && snapshot && (snapshotExpired || snapshotTooOld || !grid.times.length ? <div className="empty"><h3>{!checkedVenues ? 'Availability not checked yet' : snapshotExpired || snapshotTooOld ? 'Availability snapshot expired' : !durationChecked ? 'Duration not checked' : 'No checked times match'}</h3><p>{!checkedVenues ? `No ${sport} locations have an availability feed in this pilot.` : snapshotExpired || snapshotTooOld ? 'Browse locations and check directly with the booking provider until a new snapshot is published.' : !durationChecked ? 'The provider returned no booking durations.' : 'Try removing a filter or choosing another sport.'}</p></div> : <>
        <p className="grid-legend">Each cell counts locations seen free at the last check. A dash means none seen among the checked venues.</p>
        <div className="time-grid-scroll" role="region" aria-label="Court availability by day and time" tabIndex={0}>
          <table className="time-grid">
            <thead><tr><th scope="col">Start</th>{grid.days.map((day) => <th scope="col" key={day}>{prettyDate(day).replace(/ \d{4}$/, '')}</th>)}</tr></thead>
            <tbody>{grid.times.map((time) => <tr key={time}><th scope="row">{time}</th>{grid.days.map((day) => {
              const cell = grid.cells[`${day}|${time}`];
              const count = cell?.venueIds.length ?? 0;
              return <td key={day}><button type="button" className={`time-cell ${count ? 'has-slots' : ''} ${playDate === day && startTime === time ? 'selected' : ''}`} aria-label={`${prettyDate(day)} at ${time}: ${count} locations, ${cell?.courtCount ?? 0} courts seen free`} aria-pressed={playDate === day && startTime === time} onClick={() => { setPlayDate(day); setStartTime(time); setLimit(24); requestAnimationFrame(() => document.getElementById('selected-time-locations')?.scrollIntoView({ behavior: 'smooth', block: 'start' })); }}><strong>{count || '—'}</strong>{count > 0 && <small>{cell.courtCount} {cell.courtCount === 1 ? 'court' : 'courts'}</small>}</button></td>;
            })}</tr>)}</tbody>
          </table>
        </div>
        {grid.days.includes(playDate) && grid.times.includes(startTime) ? <section id="selected-time-locations" className="time-selection" aria-label="Locations at selected time" aria-live="polite">
          <div className="time-selection-head"><div><p className="eyebrow">SELECTED TIME</p><h3>{prettyDate(playDate)} · {startTime}</h3></div><p>{selectedVenues.length} {selectedVenues.length === 1 ? 'location' : 'locations'} · {selectedCell?.courtCount ?? 0} {selectedCell?.courtCount === 1 ? 'court' : 'courts'} seen free</p></div>
          {selectedVenues.length ? <div className="time-location-list">{selectedVenues.slice(0, limit).map((venue) => {
            const slots = availabilityForVenue(availability, venue.id, playDate, startTime, shownDuration).slots;
            const prices = slots.flatMap((slot) => slot.price_pence === null ? [] : [slot.price_pence]);
            const bookingUrls = bookingUrlsForSlots(slots);
            const distance = userLocation && venue.coordinate ? distanceMiles(userLocation, venue.coordinate) : null;
            return <article className="time-location" key={venue.id}><div><h4>{venue.name}</h4><p>{venue.area ? `${venue.area} · ` : ''}{venue.borough} · {slots.length} {slots.length === 1 ? 'court' : 'courts'} seen free{prices.length ? ` · From £${(Math.min(...prices) / 100).toFixed(2)} for ${shownDuration} min` : ''}{distance !== null ? ` · ${distance.toFixed(1)} miles away` : ''}</p>{bookingAccountRequired(availability, venue.id) && <small>Account required to book.</small>}</div><div className="time-location-actions"><button className="star" aria-label={`${favourites.includes(venue.id) ? 'Remove' : 'Add'} ${venue.name} ${favourites.includes(venue.id) ? 'from' : 'to'} favourites`} onClick={() => toggleFavourite(venue.id)}>{favourites.includes(venue.id) ? '★' : '☆'}</button>{bookingUrls.map((url, index) => <a key={url} href={url} target="_blank" rel="noreferrer">Check booking{bookingUrls.length > 1 ? ` ${index + 1}` : ''} ↗</a>)}</div></article>;
          })}</div> : <p className="no-time-locations">No free courts seen among checked locations at this time. Try another cell.</p>}
          {selectedVenues.length > limit && <button className="show-more" onClick={() => setLimit(limit + 24)}>Show 24 more</button>}
        </section> : <p className="no-time-locations">Choose a cell to see available locations.</p>}
      </>)}
      {view === 'locations' && <div className="court-grid">{results.slice(0, limit).map((venue) => {
        const display = venueDisplay(venue, mode, playDate);
        const release = display.release;
        const bookingUrl = bookingUrlFor(venue, playDate);
        const coordinate = venue.coordinate;
        const distance = userLocation && coordinate ? distanceMiles(userLocation, coordinate) : null;
        return <article className="court-card" key={venue.id}>
          <div className="card-top"><span className={`status ${display.status.tone}`}>{display.status.label}</span><button className="star" aria-label={`${favourites.includes(venue.id) ? 'Remove' : 'Add'} ${venue.name} ${favourites.includes(venue.id) ? 'from' : 'to'} favourites`} onClick={() => toggleFavourite(venue.id)}>{favourites.includes(venue.id) ? '★' : '☆'}</button></div>
          <h3>{venue.name}</h3><p className="location">{venue.area ? `${venue.area} · ` : ''}{venue.borough}{distance !== null && <strong> · {distance.toFixed(1)} miles away</strong>}</p>
          <div className="facts"><div><span>COURTS</span><strong>{venue.courts_total ?? '—'}</strong></div><div><span>LIGHT</span><strong>{display.lighting}</strong></div><div><span>PRICE</span><strong>{display.price}</strong><small>{display.priceUnit}</small></div></div>
          {display.rates.length > 0 && <details className="price-panel"><summary>Rates · check final price</summary>{display.rates.map((option) => <div key={`${option.label}-${option.duration_minutes}-${option.amount_gbp}`}><span>{option.label}</span><strong>£{option.amount_gbp}/{option.duration_minutes} min</strong></div>)}</details>}
          <p className="suitability">{display.suitability}</p>
          <div className={`release ${release?.open ? 'open' : ''}`}><span>{display.releaseHeading}</span><strong>{display.releaseLabel}</strong><small>{display.releaseRule}</small></div>
          {coordinate && <details className="map-panel"><summary>View map</summary><iframe title={`Map showing ${venue.name}`} src={osmEmbedUrl(coordinate)} loading="lazy" referrerPolicy="strict-origin-when-cross-origin" /><div><a href={directionsUrl(venue)} target="_blank" rel="noreferrer">Directions from me ↗</a><a href={`https://www.openstreetmap.org/?mlat=${coordinate.latitude}&mlon=${coordinate.longitude}#map=16/${coordinate.latitude}/${coordinate.longitude}`} target="_blank" rel="noreferrer">Open larger map ↗</a></div><small>© OpenStreetMap contributors · Pin generated from venue name and borough</small></details>}
          <div className="actions">{bookingUrl && <a className="book" href={bookingUrl} target="_blank" rel="noreferrer">Check booking ↗</a>}<a href={directionsUrl(venue)} target="_blank" rel="noreferrer">Directions from me</a>{release && !release.open && <button onClick={() => downloadReminder(venue)}>Add reminder</button>}<a className="source" href={venue.sources[0]?.url} target="_blank" rel="noreferrer">Source</a></div>
        </article>;
      })}</div>}
      {view === 'locations' && !results.length && <div className="empty"><h3>No matching courts</h3><p>Try showing every status or removing a price cap.</p></div>}
      {view === 'locations' && results.length > limit && <button className="show-more" onClick={() => setLimit(limit + 24)}>Show 24 more</button>}
    </section>
  </main>;
}
