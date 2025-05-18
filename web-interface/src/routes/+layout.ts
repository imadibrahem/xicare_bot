import { currentUser, pb } from '$lib/pocketbase.svelte';
import { redirect } from '@sveltejs/kit';

import type { LayoutLoad } from './$types';

export const ssr = false;

export const load: LayoutLoad = async ({ url }) => {
	const publicRoutes = ['/login', '/about'];
	const isPublicRoute = publicRoutes.some((route) => url.pathname.startsWith(route));

	// Redirect to root if user is logged in but on login page
	if (currentUser.record && url.pathname.startsWith('/login')) {
		redirect(307, '/');
	}

	// Redirect to login if user is not logged in and trying to access protected route
	if (!currentUser.record && !isPublicRoute) {
		try {
			// Do an auth refresh on every page reload
			await pb.collection('users').authRefresh();
		} catch {
			pb.authStore.clear();
		}
		redirect(307, '/login');
	}
};
