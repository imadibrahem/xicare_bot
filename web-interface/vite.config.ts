import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import dotenv from 'dotenv';
import path from 'path';

// Load the .env file from monorepo root
dotenv.config({ path: path.resolve(__dirname, '../.env') });

export default defineConfig({
	plugins: [sveltekit()]
});
