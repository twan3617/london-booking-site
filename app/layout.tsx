import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  metadataBase: new URL(process.env.URL ?? 'http://localhost:3000'),
  title: 'Public Courts Across London',
  description: 'Browse London tennis, squash and padel courts, or find slots in the latest availability check for supported venues.',
  openGraph: {
    title: 'Public Courts Across London',
    description: 'London public racquet court booking planner',
    images: ['/og.png'],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Public Courts Across London',
    description: 'London public racquet court booking planner',
    images: ['/og.png'],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">
        {children}
      </body>
    </html>
  );
}
