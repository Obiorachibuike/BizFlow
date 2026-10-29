import type { NextConfig } from 'next';
const api = process.env.BIZFLOW_API_URL || 'http://127.0.0.1:8000';
const nextConfig: NextConfig = { async rewrites() { return [{ source: '/api/:path*', destination: `${api}/api/:path*` }, { source: '/health', destination: `${api}/health` }]; } };
export default nextConfig;
