import { superValidate } from 'sveltekit-superforms';
import { redirect } from '@sveltejs/kit';
import { formSchema } from './schema';
import { zod } from 'sveltekit-superforms/adapters';

import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	return {
		formValidation: await superValidate(zod(formSchema))
	};
};

export const actions: Actions = {
	login: async (event) => {
		const form = await superValidate(event, zod(formSchema));

		if (!form.valid) {
			return { success: false, message: 'Failed form validation' };
		}

		const data = form.data;

		try {
			await event.locals.pb.collection('users').authWithPassword(data.username, data.password);
		} catch (error) {
			console.error('Authentication error:', error);

			// Return the form with an error
			return { success: false, message: 'Invalid username or password' };
		}
		// Redirect user to home page
		return redirect(303, '/');
	}
};
