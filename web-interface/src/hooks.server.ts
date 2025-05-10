import PocketBase from 'pocketbase';
import { redirect } from '@sveltejs/kit';
import type { Handle } from '@sveltejs/kit';

export const handle: Handle = async ({ event, resolve }) => {
	event.locals.pb = new PocketBase('http://127.0.0.1:8090');

	// load the store data from the request cookie string
	event.locals.pb.authStore.loadFromCookie(event.request.headers.get('cookie') || '');

	try {
		// get an up-to-date auth store state by verifying and refreshing the loaded auth model (if any)
		if (event.locals.pb.authStore.isValid) {
			await event.locals.pb.collection('users').authRefresh();

			event.locals.userId = event.locals.pb.authStore.record?.id;
		}
	} catch {
		// clear the auth store on failed refresh
		event.locals.pb.authStore.clear();
		event.locals.userId = undefined;
	}

	// Check if user is authenticated and redirect if needed
	const publicRoutes = ['/login']; // Add any public routes here
	const isPublicRoute = publicRoutes.some((route) => event.url.pathname.startsWith(route));

	if (!event.locals.pb.authStore.isValid && !isPublicRoute) {
		return redirect(303, '/login');
	}

	const response = await resolve(event);

	// send back the default 'pb_auth' cookie to the client with the latest store state
	response.headers.append('set-cookie', event.locals.pb.authStore.exportToCookie());

	return response;
};
