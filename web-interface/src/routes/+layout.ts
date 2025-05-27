import { currentUser, pb } from '$lib/pocketbase.svelte';
import { redirect } from '@sveltejs/kit';

import type { LayoutLoad } from './$types';

export const ssr = false;

export const load: LayoutLoad = async ({ url, fetch }) => {
	const publicRoutes = ['/login'];
	const isPublicRoute = publicRoutes.some((route) => url.pathname.startsWith(route));

	// For non-public routes, try to refresh auth first before any redirects
	if (!isPublicRoute) {
		if (pb.authStore.isValid) {
			try {
				await pb.collection('users').authRefresh({ fetch: fetch });
			} catch {
				pb.authStore.clear();
				redirect(307, '/login');
			}
		} else {
			pb.authStore.clear();
			redirect(307, '/login');
		}
	}

	// Redirect logged-in users away from login page
	if (currentUser.store.record && url.pathname.startsWith('/login')) {
		redirect(307, '/');
	}
};
