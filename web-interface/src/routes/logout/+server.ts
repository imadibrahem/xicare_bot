import { redirect } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = ({ locals }) => {
	locals.pb.authStore.clear();
	locals.userId = undefined;

	return redirect(303, '/login');
};
