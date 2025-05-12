import { currentUser } from '$lib/pocketbase.svelte';
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
		redirect(307, '/login');
	}
};
