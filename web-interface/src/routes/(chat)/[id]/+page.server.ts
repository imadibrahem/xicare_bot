import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ params, locals }) => {
	return {
		messages: await locals.pb.collection('messages').getFullList({
			filter: `conversation="${params.id}"`,
			sort: '-created'
		})
	};
};
