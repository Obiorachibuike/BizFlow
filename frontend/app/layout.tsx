import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'BizFlow Africa — Run your business smarter', description: 'A practical business workspace for African businesses.' };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en"><body>{children}</body></html>; }
