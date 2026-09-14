'use client';

import { useEffect, useMemo, useState } from 'react';
import catalogue from '../data/venues.json';
import { calendarText, matchesVenue, releaseDetails, relevantHourlyPrice, type Filters, type Mode, type Venue } from './booking';

const venues = catalogue.venues as Venue[];
const boroughs = [...new Set(venues.map((venue) => venue.borough))].sort();

function nextSaturday() {
  const date = new Date();
  date.setDate(date.getDate() + ((6 - date.getDay() + 7) % 7 || 7));
  return date.toISOString().slice(0, 10);
}

function prettyDate(date: string) {
  return new Intl.DateTimeFormat('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${date}T12:00:00Z`));
}

function statusFor(venue: Venue, mode: Mode) {
  if (mode === 'weekend') return { label: 'Weekend details', tone: 'neutral' };
  if (venue.evening_assessment === 'suitable') return { label: 'Ready after work', tone: 'good' };
  if (venue.evening_assessment === 'seasonal') return { label: 'Seasonal daylight', tone: 'warn' };
  if (venue.evening_assessment === 'unsuitable') return { label: 'Closes too early', tone: 'bad' };
  return { label: 'Needs checking', tone: 'neutral' };
}

export default function Home() {
  const [mode, setMode] = useState<Mode>('after-work');
  const [playDate, setPlayDate] = useState(nextSaturday);
  const [query, setQuery] = useState('');
  const [borough, setBorough] = useState('');
  const [facility, setFacility] = useState<Filters['facility']>('any');
  const [status, setStatus] = useState<Filters['status']>('ready');
  const [maxPrice, setMaxPrice] = useState('');
  const [favourites, setFavourites] = useState<string[]>([]);
  const [favouritesOnly, setFavouritesOnly] = useState(false);
  const [limit, setLimit] = useState(24);

  useEffect(() => {
    try { setFavourites(JSON.parse(localStorage.getItem('court-ready-favourites') ?? '[]')); } catch { /* Ignore damaged local preferences. */ }
  }, []);

  const results = useMemo(() => {
    const filters: Filters = { mode, borough, query, facility, status: mode === 'weekend' ? 'all' : status, maxPrice: maxPrice === '' ? null : Number(maxPrice) };
    return venues
      .filter((venue) => matchesVenue(venue, filters) && (!favouritesOnly || favourites.includes(venue.id)))
      .sort((a, b) => Number(favourites.includes(b.id)) - Number(favourites.includes(a.id)) || ['suitable', 'seasonal', 'unknown', 'unsuitable'].indexOf(a.evening_assessment) - ['suitable', 'seasonal', 'unknown', 'unsuitable'].indexOf(b.evening_assessment) || a.name.localeCompare(b.name));
  }, [mode, borough, query, facility, status, maxPrice, favourites, favouritesOnly]);

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

  return <main>
    <header className="hero">
      <div className="nav"><span className="brand-mark">●</span><strong>Court Ready</strong><span className="data-note">London public tennis · checked {catalogue.checked_on}</span></div>
      <div className="hero-copy"><p className="eyebrow">Plan the booking. Then beat the rush.</p><h1>Know where to play<br />and when to book.</h1><p>Public courts across London, filtered for the hours you can actually play. Booking rules are published guidance, not live availability.</p></div>
    </header>

    <section className="planner" aria-label="Court filters">
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
        <label>Max £ / court / hour<input type="number" min="0" step="1" value={maxPrice} onChange={(event) => setMaxPrice(event.target.value)} placeholder="Any price" /></label>
      </div>
    </section>

    <section className="results">
      <div className="results-head"><div><p className="eyebrow">{prettyDate(playDate)}</p><h2>{results.length} courts match</h2></div><button className={`favourites-toggle ${favouritesOnly ? 'active' : ''}`} onClick={() => setFavouritesOnly(!favouritesOnly)}>★ Favourites {favourites.length || ''}</button></div>
      <div className="court-grid">{results.slice(0, limit).map((venue) => {
        const release = releaseDetails(venue, playDate);
        const courtStatus = statusFor(venue, mode);
        const price = relevantHourlyPrice(venue, mode);
        const bookingUrl = venue.booking_url ?? venue.sources[0]?.url;
        return <article className="court-card" key={venue.id}>
          <div className="card-top"><span className={`status ${courtStatus.tone}`}>{courtStatus.label}</span><button className="star" aria-label={`${favourites.includes(venue.id) ? 'Remove' : 'Add'} ${venue.name} ${favourites.includes(venue.id) ? 'from' : 'to'} favourites`} onClick={() => toggleFavourite(venue.id)}>{favourites.includes(venue.id) ? '★' : '☆'}</button></div>
          <h3>{venue.name}</h3><p className="location">{venue.area ? `${venue.area} · ` : ''}{venue.borough}</p>
          <div className="facts"><div><span>COURTS</span><strong>{venue.courts_total ?? '—'}</strong></div><div><span>LIGHT</span><strong>{venue.indoor_courts ? `${venue.indoor_courts} indoor` : venue.lighting}</strong></div><div><span>PRICE</span><strong>{price === null ? 'Check' : `£${price}/hr`}</strong></div></div>
          <p className="suitability">{mode === 'after-work' ? venue.evening_notes : venue.weekend_notes ?? venue.hours_text ?? 'Weekend court hours need checking.'}</p>
          <div className={`release ${release?.open ? 'open' : ''}`}><span>{release?.open ? 'BOOKING WINDOW' : 'BE READY TO BOOK'}</span><strong>{release ? (release.open ? 'Open — check slots now' : `${prettyDate(release.date)} · ${release.time}`) : 'Release time needs checking'}</strong><small>{venue.release_rule ?? 'No verified release rule.'}</small></div>
          <div className="actions">{bookingUrl && <a className="book" href={bookingUrl} target="_blank" rel="noreferrer">Check booking ↗</a>}{release && !release.open && <button onClick={() => downloadReminder(venue)}>Add reminder</button>}<a className="source" href={venue.sources[0]?.url} target="_blank" rel="noreferrer">Source</a></div>
        </article>;
      })}</div>
      {!results.length && <div className="empty"><h3>No matching courts</h3><p>Try showing every status or removing a price cap.</p></div>}
      {results.length > limit && <button className="show-more" onClick={() => setLimit(limit + 24)}>Show 24 more</button>}
    </section>
  </main>;
}
