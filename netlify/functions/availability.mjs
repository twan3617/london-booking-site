import { getStore } from '@netlify/blobs';

const availabilityHandler = async () => {
  try {
    const snapshot = await getStore('court-availability').get('latest');
    if (snapshot === null) return new Response('Availability has not been checked yet.', { status: 503 });
    return new Response(snapshot, { headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'public, max-age=1800' } });
  } catch (error) {
    console.error('Could not read court availability', error);
    return new Response('Availability is temporarily unavailable.', { status: 503 });
  }
};

export default availabilityHandler;
export const config = { method: 'GET' };
