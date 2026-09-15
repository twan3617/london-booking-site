'use client';

import { useEffect, useMemo, useState } from 'react';
import catalogue from '../data/venues.json';
import coordinateData from '../data/coordinates.json';
import priceData from '../data/prices.json';
import { bookingUrlFor, calendarText, directionsUrl, distanceMiles, matchesVenue, osmEmbedUrl, parseCatalogue, prettyDate, releaseDetails, venueDisplay, withinBookingWindow, type Filters, type Mode, type Point, type PriceOption, type Sport, type Venue } from './booking';

const priceOptions = priceData as Record<string, PriceOption[] | null>;
const venues = parseCatalogue(catalogue as unknown as { venues: Venue[] }, priceOptions, coordinateData as Record<string, Point | null>);

function nextSaturday() {
  const date = new Date();
  date.setDate(date.getDate() + ((6 - date.getDay() + 7) % 7 || 7));
  return date.toISOString().slice(0, 10);
}

export default function Home() {
  const [sport, setSport] = useState<Sport>('tennis');
  const [mode, setMode] = useState<Mode>('after-work');
  const [playDate, setPlayDate] = useState(nextSaturday);
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

  useEffect(() => {
    const timer = window.setTimeout(() => {
      try { setFavourites(JSON.parse(localStorage.getItem('court-ready-favourites') ?? '[]')); } catch { /* Ignore damaged local preferences. */ }
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const results = useMemo(() => {
    const filters: Filters = { sport, mode, borough, query, facility, status: mode === 'weekend' ? 'all' : status, maxPrice: sport !== 'tennis' || maxPrice === '' ? null : Number(maxPrice) };
    return venues
      .filter((venue) => matchesVenue(venue, filters) && withinBookingWindow(venue, playDate) && (!favouritesOnly || favourites.includes(venue.id)))
      .sort((a, b) => {
        if (sortOrder === 'distance' && userLocation) {
          const aDistance = a.coordinate ? distanceMiles(userLocation, a.coordinate) : Infinity;
          const bDistance = b.coordinate ? distanceMiles(userLocation, b.coordinate) : Infinity;
          return aDistance - bDistance || a.name.localeCompare(b.name);
        }
        return Number(favourites.includes(b.id)) - Number(favourites.includes(a.id)) || ['suitable', 'seasonal', 'unknown', 'unsuitable'].indexOf(a.evening_assessment) - ['suitable', 'seasonal', 'unknown', 'unsuitable'].indexOf(b.evening_assessment) || a.name.localeCompare(b.name);
      });
  }, [sport, mode, playDate, borough, query, facility, status, maxPrice, favourites, favouritesOnly, sortOrder, userLocation]);

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
      <div className="sport-tabs" role="group" aria-label="Sport">{(['tennis', 'squash', 'padel'] as const).map((item) => <button key={item} className={sport === item ? 'active' : ''} onClick={() => { setSport(item); setBorough(''); setFacility('any'); setLimit(24); }}>{item}</button>)}</div>
      <div className="mode-tabs" role="group" aria-label="When do you want to play?">
        <button className={mode === 'after-work' ? 'active' : ''} onClick={() => { setMode('after-work'); setStatus('ready'); }}>After work <small>19:00–21:00</small></button>
        <button className={mode === 'weekend' ? 'active' : ''} onClick={() => setMode('weekend')}>Weekend daytime <small>09:00–17:00</small></button>
      </div>
      <div className="filter-grid">
        <label>Playing date<input type="date" value={playDate} onChange={(event) => setPlayDate(event.target.value)} /></label>
        <label>Search<input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Court, area or borough" /></label>
        <label>Borough<select value={borough} onChange={(event) => setBorough(event.target.value)}><option value="">All London</option>{boroughs.map((item) => <option key={item}>{item}</option>)}</select></label>
        <label>Facility<select value={facility} onChange={(event) => setFacility(event.target.value as Filters['facility'])}><option value="any">Any facility</option><option value="floodlit">Floodlit outdoor</option><option value="indoor">Indoor</option></select></label>
        {mode === 'after-work' && <label>Evening status<select value={status} onChange={(event) => setStatus(event.target.value as Filters['status'])}><option value="ready">Ready after work</option><option value="seasonal">Seasonal daylight</option><option value="checking">Needs checking</option><option value="all">Every status</option></select></label>}
        {sport === 'tennis' && <label>Max £ / court / hour<input type="number" min="0" step="1" value={maxPrice} onChange={(event) => setMaxPrice(event.target.value)} placeholder="Any price" /></label>}
      </div>
    </section>

    <section className="results">
      <div className="results-head"><div><p className="eyebrow">{prettyDate(playDate)}</p><h2>{results.length} courts match</h2></div><div className="result-tools"><label>Sort<select value={sortOrder} onChange={(event) => chooseSort(event.target.value as 'recommended' | 'distance')}><option value="recommended">Recommended</option><option value="distance">Nearest to me</option></select></label><button className={`favourites-toggle ${favouritesOnly ? 'active' : ''}`} onClick={() => setFavouritesOnly(!favouritesOnly)}>★ Favourites {favourites.length || ''}</button></div></div>
      {locationMessage && <p className="location-message" role="status">{locationMessage}</p>}
      <div className="court-grid">{results.slice(0, limit).map((venue) => {
        const display = venueDisplay(venue, mode, playDate);
        const release = display.release;
        const bookingUrl = bookingUrlFor(venue, playDate);
        const coordinate = venue.coordinate;
        const distance = userLocation && coordinate ? distanceMiles(userLocation, coordinate) : null;
        return <article className="court-card" key={venue.id}>
          <div className="card-top"><span className={`status ${display.status.tone}`}>{display.status.label}</span><button className="star" aria-label={`${favourites.includes(venue.id) ? 'Remove' : 'Add'} ${venue.name} ${favourites.includes(venue.id) ? 'from' : 'to'} favourites`} onClick={() => toggleFavourite(venue.id)}>{favourites.includes(venue.id) ? '★' : '☆'}</button></div>
          <h3>{venue.name}</h3><p className="location">{venue.area ? `${venue.area} · ` : ''}{venue.borough}{distance !== null && <strong> · {distance.toFixed(1)} miles away</strong>}</p>
          <div className="facts"><div><span>COURTS</span><strong>{venue.courts_total ?? '—'}</strong></div><div><span>LIGHT</span><strong>{display.lighting}</strong></div><div><span>PRICE</span><strong>{display.price}</strong><small>{display.priceUnit}</small></div></div>
          {display.rates.length > 0 && <details className="price-panel"><summary>Published rates · check final price</summary>{display.rates.map((option) => <div key={`${option.label}-${option.duration_minutes}`}><span>{option.label}</span><strong>£{option.amount_gbp}/{option.duration_minutes} min</strong></div>)}</details>}
          <p className="suitability">{display.suitability}</p>
          <div className={`release ${release?.open ? 'open' : ''}`}><span>{display.releaseHeading}</span><strong>{display.releaseLabel}</strong><small>{display.releaseRule}</small></div>
          {coordinate && <details className="map-panel"><summary>View map</summary><iframe title={`Map showing ${venue.name}`} src={osmEmbedUrl(coordinate)} loading="lazy" referrerPolicy="strict-origin-when-cross-origin" /><div><a href={directionsUrl(venue)} target="_blank" rel="noreferrer">Directions from me ↗</a><a href={`https://www.openstreetmap.org/?mlat=${coordinate.latitude}&mlon=${coordinate.longitude}#map=16/${coordinate.latitude}/${coordinate.longitude}`} target="_blank" rel="noreferrer">Open larger map ↗</a></div><small>© OpenStreetMap contributors · Pin generated from venue name and borough</small></details>}
          <div className="actions">{bookingUrl && <a className="book" href={bookingUrl} target="_blank" rel="noreferrer">Check booking ↗</a>}<a href={directionsUrl(venue)} target="_blank" rel="noreferrer">Directions from me</a>{release && !release.open && <button onClick={() => downloadReminder(venue)}>Add reminder</button>}<a className="source" href={venue.sources[0]?.url} target="_blank" rel="noreferrer">Source</a></div>
        </article>;
      })}</div>
      {!results.length && <div className="empty"><h3>No matching courts</h3><p>Try showing every status or removing a price cap.</p></div>}
      {results.length > limit && <button className="show-more" onClick={() => setLimit(limit + 24)}>Show 24 more</button>}
    </section>
  </main>;
}
