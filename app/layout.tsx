import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import './globals.css';

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
});

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

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
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
