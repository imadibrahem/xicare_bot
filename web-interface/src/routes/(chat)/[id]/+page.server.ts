import type { PageServerLoad } from './$types';
import type { Message } from '$lib/types';

export const load: PageServerLoad = async ({ params, locals }) => {
	return {
		messages: (await locals.pb.collection('messages').getFullList({
			filter: locals.pb.filter('conversation = {:id}', { id: params.id }),
			sort: '-created'
		})) as Message[]
	};
};
