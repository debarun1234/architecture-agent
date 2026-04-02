import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'ArchReview AI — Enterprise Architecture Review',
  description:
    'AI-powered architecture review system. Upload PRD, HLD, or LLD documents and get instant grounded architectural insights, bottleneck detection, and improvement proposals backed by citations.',
  keywords: ['architecture review', 'AI', 'PRD', 'HLD', 'LLD', 'cloud architecture', 'Gemini', 'pgvector'],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="scroll-smooth">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="antialiased font-sans bg-white text-slate-900">{children}</body>
    </html>
  );
}
