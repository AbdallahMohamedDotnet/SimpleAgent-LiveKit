import '@livekit/components-styles';
import './globals.css';
import type { Metadata, Viewport } from 'next';

export const metadata: Metadata = {
  title: 'Interview Agent',
  description: 'Talk to a voice interview agent over LiveKit',
};

// `themeColor` follows the palette in globals.css so mobile browser chrome matches the page
// instead of framing a dark app in a white bar.
export const viewport: Viewport = {
  themeColor: [
    { media: '(prefers-color-scheme: dark)', color: '#08090d' },
    { media: '(prefers-color-scheme: light)', color: '#f6f7f9' },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
