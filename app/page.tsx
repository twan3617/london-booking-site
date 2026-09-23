'use client';

import { useEffect, useMemo, useState } from 'react';
import catalogue from '../data/venues.json';
import coordinateData from '../data/coordinates.json';
import priceData from '../data/prices.json';
import availabilityData from '../data/availability.json';
import { availabilityForVenue, bookingUrlFor, calendarText, directionsUrl, distanceMiles, matchesVenue, osmEmbedUrl, parseCatalogue, prettyDate, releaseDetails, venueDisplay, withinBookingWindow, type AvailabilitySnapshot, type Filters, type Mode, type Point, type PriceOption, type Sport, type Venue } from './booking';

const priceOptions = priceData as Record<string, PriceOption[] | null>;
const venues = parseCatalogue(catalogue as unknown as { venues: Venue[] }, priceOptions, coordinateData as Record<string, Point | null>);
const availability = availabilityData as AvailabilitySnapshot;
const checkedAt = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/London' }).format(new Date(availability.generated_at));

function nextSaturday() {
  const date = new Date();
  date.setDate(date.getDate() + ((6 - date.getDay() + 7) % 7 || 7));
  return date.toISOString().slice(0, 10);
}

export default function Home() {
  const [view, setView] = useState<'locations' | 'time'>('locations');
  const [sport, setSport] = useState<Sport>('tennis');
  const [mode, setMode] = useState<Mode>('after-work');
  const [playDate, setPlayDate] = useState(nextSaturday);
  const [startTime, setStartTime] = useState('19:00');
  const [durationMinutes, setDurationMinutes] = useState(60);
  const [availableOnly, setAvailableOnly] = useState(true);
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
  const boroughs = useMemo(() => [...new Set(venues.filter((venue) => venue.sport === sport).map((venue) => venue.borough))].sort(), [sport]);
  const checkedVenues = venues.filter((venue) => venue.sport === sport && availability.venue_ids.includes(venue.id)).length;
  const dateCovered = playDate >= availability.coverage_start && playDate <= availability.coverage_end;
  const snapshotOld = Date.now() - Date.parse(availability.generated_at) > 30 * 60_000;
  const emptyTitle = view === 'locations' ? 'No matching courts' : favouritesOnly ? 'No favourites match' : !dateCovered ? 'Date not checked' : !checkedVenues ? 'Availability not checked yet' : availableOnly ? 'No checked free slots match' : 'No locations match';
  const emptyHint = view === 'locations' ? 'Try showing every status or removing a price cap.' : favouritesOnly ? 'Turn off Favourites to see other locations.' : !dateCovered ? 'Choose a date inside the checked range.' : !checkedVenues ? `No ${sport} venues have an availability feed in this pilot.` : availableOnly ? 'Try another time or turn off Available only to browse locations.' : 'Try changing the search or filters.';

  useEffect(() => {
    const timer = window.setTimeout(() => {
      try { setFavourites(JSON.parse(localStorage.getItem('court-ready-favourites') ?? '[]')); } catch { /* Ignore damaged local preferences. */ }
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const results = useMemo(() => {
    const filters: Filters = { sport, mode, borough, query, facility, status: view === 'time' || mode === 'weekend' ? 'all' : status, maxPrice: view === 'time' || sport !== 'tennis' || maxPrice === '' ? null : Number(maxPrice) };
    return venues
      .filter((venue) => matchesVenue(venue, filters) && (view === 'time' ? (!availableOnly || availabilityForVenue(availability, venue.id, playDate, startTime, durationMinutes).status === 'available') : withinBookingWindow(venue, playDate)) && (!favouritesOnly || favourites.includes(venue.id)))
      .sort((a, b) => {
        if (sortOrder === 'distance' && userLocation) {
          const aDistance = a.coordinate ? distanceMiles(userLocation, a.coordinate) : Infinity;
          const bDistance = b.coordinate ? distanceMiles(userLocation, b.coordinate) : Infinity;
          return aDistance - bDistance || a.name.localeCompare(b.name);
        }
        return Number(favourites.includes(b.id)) - Number(favourites.includes(a.id)) || ['suitable', 'seasonal', 'unknown', 'unsuitable'].indexOf(a.evening_assessment) - ['suitable', 'seasonal', 'unknown', 'unsuitable'].indexOf(b.evening_assessment) || a.name.localeCompare(b.name);
      });
  }, [view, sport, mode, playDate, startTime, durationMinutes, availableOnly, borough, query, facility, status, maxPrice, favourites, favouritesOnly, sortOrder, userLocation]);

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
        <label>Playing date<input type="date" value={playDate} onChange={(event) => { if (event.target.value) setPlayDate(event.target.value); }} /></label>
        {view === 'time' && <label>Start time<input type="time" step="1800" value={startTime} onChange={(event) => setStartTime(event.target.value)} /></label>}
        {view === 'time' && <label>Duration<select value={durationMinutes} onChange={(event) => setDurationMinutes(Number(event.target.value))}><option value={30}>30 minutes</option><option value={45}>45 minutes</option><option value={60}>60 minutes</option><option value={90}>90 minutes</option></select></label>}
        <label>Search<input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Court, area or borough" /></label>
        <label>Borough<select value={borough} onChange={(event) => setBorough(event.target.value)}><option value="">All London</option>{boroughs.map((item) => <option key={item}>{item}</option>)}</select></label>
        <label>Facility<select value={facility} onChange={(event) => setFacility(event.target.value as Filters['facility'])}><option value="any">Any facility</option><option value="floodlit">Floodlit outdoor</option><option value="indoor">Indoor</option></select></label>
        {view === 'locations' && mode === 'after-work' && <label>Evening status<select value={status} onChange={(event) => setStatus(event.target.value as Filters['status'])}><option value="ready">Ready after work</option><option value="seasonal">Seasonal daylight</option><option value="checking">Needs checking</option><option value="all">Every status</option></select></label>}
        {view === 'locations' && sport === 'tennis' && <label>Max £ / court / hour<input type="number" min="0" step="1" value={maxPrice} onChange={(event) => setMaxPrice(event.target.value)} placeholder="Any price" /></label>}
      </div>
    </section>

    <section className="results">
      <div className="results-head"><div><p className="eyebrow">{prettyDate(playDate)}{view === 'time' ? ` · ${startTime} · ${durationMinutes} min` : ''}</p><h2>{view === 'time' ? `${results.length} locations match` : `${results.length} courts match`}</h2></div><div className="result-tools"><label>Sort<select value={sortOrder} onChange={(event) => chooseSort(event.target.value as 'recommended' | 'distance')}><option value="recommended">Recommended</option><option value="distance">Nearest to me</option></select></label>{view === 'time' && <button type="button" className={`favourites-toggle ${availableOnly ? 'active' : ''}`} aria-pressed={availableOnly} onClick={() => setAvailableOnly(!availableOnly)}>Available only</button>}<button className={`favourites-toggle ${favouritesOnly ? 'active' : ''}`} onClick={() => setFavouritesOnly(!favouritesOnly)}>★ Favourites {favourites.length || ''}</button></div></div>
      {view === 'time' && <p className="availability-note" role="status">Last checked {checkedAt} London time. {checkedVenues} of {venues.filter((venue) => venue.sport === sport).length} {sport} locations checked for {availability.coverage_start}–{availability.coverage_end}. {snapshotOld ? 'This snapshot is over 30 minutes old. ' : ''}Slots can change; confirm on the booking site.</p>}
      {locationMessage && <p className="location-message" role="status">{locationMessage}</p>}
      <div className="court-grid">{results.slice(0, limit).map((venue) => {
        const display = venueDisplay(venue, mode, playDate);
        const release = display.release;
        const slotResult = view === 'time' ? availabilityForVenue(availability, venue.id, playDate, startTime, durationMinutes) : null;
        const slotPrices = slotResult?.slots.flatMap((slot) => slot.price_pence === null ? [] : [slot.price_pence]) ?? [];
        const bookingUrl = slotResult?.slots[0]?.booking_url ?? bookingUrlFor(venue, playDate);
        const coordinate = venue.coordinate;
        const distance = userLocation && coordinate ? distanceMiles(userLocation, coordinate) : null;
        return <article className="court-card" key={venue.id}>
          <div className="card-top"><span className={`status ${slotResult ? slotResult.status === 'available' ? 'good' : slotResult.status === 'none' ? 'bad' : 'neutral' : display.status.tone}`}>{slotResult ? ({ available: 'Seen free at last check', none: 'No free slot found', unsupported: 'Availability not checked', outside: 'Date not checked' } as const)[slotResult.status] : display.status.label}</span><button className="star" aria-label={`${favourites.includes(venue.id) ? 'Remove' : 'Add'} ${venue.name} ${favourites.includes(venue.id) ? 'from' : 'to'} favourites`} onClick={() => toggleFavourite(venue.id)}>{favourites.includes(venue.id) ? '★' : '☆'}</button></div>
          <h3>{venue.name}</h3><p className="location">{venue.area ? `${venue.area} · ` : ''}{venue.borough}{distance !== null && <strong> · {distance.toFixed(1)} miles away</strong>}</p>
          <div className="facts"><div><span>COURTS</span><strong>{venue.courts_total ?? '—'}</strong></div><div><span>LIGHT</span><strong>{display.lighting}</strong></div><div><span>PRICE</span><strong>{display.price}</strong><small>{display.priceUnit}</small></div></div>
          {display.rates.length > 0 && <details className="price-panel"><summary>Published rates · check final price</summary>{display.rates.map((option) => <div key={`${option.label}-${option.duration_minutes}`}><span>{option.label}</span><strong>£{option.amount_gbp}/{option.duration_minutes} min</strong></div>)}</details>}
          <p className="suitability">{display.suitability}</p>
          {slotResult ? <div className={`release ${slotResult.status === 'available' ? 'open' : ''}`}><span>SELECTED TIME</span><strong>{slotResult.status === 'available' ? `${slotResult.slots.length} ${slotResult.slots.length === 1 ? 'court' : 'courts'} seen free at ${startTime}` : slotResult.status === 'none' ? `No ${durationMinutes}-minute slot at ${startTime}` : slotResult.status === 'outside' ? 'Date outside checked range' : 'Availability not checked here'}</strong><small>{slotResult.status === 'available' && slotPrices.length ? `From £${(Math.min(...slotPrices) / 100).toFixed(2)} for ${durationMinutes} minutes · ` : ''}Checked {checkedAt}; confirm before booking.</small></div> : <div className={`release ${release?.open ? 'open' : ''}`}><span>{display.releaseHeading}</span><strong>{display.releaseLabel}</strong><small>{display.releaseRule}</small></div>}
          {coordinate && <details className="map-panel"><summary>View map</summary><iframe title={`Map showing ${venue.name}`} src={osmEmbedUrl(coordinate)} loading="lazy" referrerPolicy="strict-origin-when-cross-origin" /><div><a href={directionsUrl(venue)} target="_blank" rel="noreferrer">Directions from me ↗</a><a href={`https://www.openstreetmap.org/?mlat=${coordinate.latitude}&mlon=${coordinate.longitude}#map=16/${coordinate.latitude}/${coordinate.longitude}`} target="_blank" rel="noreferrer">Open larger map ↗</a></div><small>© OpenStreetMap contributors · Pin generated from venue name and borough</small></details>}
          <div className="actions">{bookingUrl && <a className="book" href={bookingUrl} target="_blank" rel="noreferrer">Check booking ↗</a>}<a href={directionsUrl(venue)} target="_blank" rel="noreferrer">Directions from me</a>{view === 'locations' && release && !release.open && <button onClick={() => downloadReminder(venue)}>Add reminder</button>}<a className="source" href={venue.sources[0]?.url} target="_blank" rel="noreferrer">Source</a></div>
        </article>;
      })}</div>
      {!results.length && <div className="empty"><h3>{emptyTitle}</h3><p>{emptyHint}</p></div>}
      {results.length > limit && <button className="show-more" onClick={() => setLimit(limit + 24)}>Show 24 more</button>}
    </section>
  </main>;
}
