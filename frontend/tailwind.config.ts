import type { Config } from 'tailwindcss';
const config: Config = { content: ['./app/**/*.{js,ts,jsx,tsx}', './components/**/*.{js,ts,jsx,tsx}'], theme: { extend: { colors: { ink: '#182b25', forest: '#176b4a', mint: '#e9f5ee', paper: '#f5f7f5' } } }, plugins: [] };
export default config;
