import type { LayoutServerLoad } from './$types';
import type { Conversation } from '$lib/types';

export const load: LayoutServerLoad = async ({ locals }) => {
	return {
		conversations: (await locals.pb.collection('conversations').getFullList({
			sort: '-updated'
		})) as Conversation[]
	};
};
