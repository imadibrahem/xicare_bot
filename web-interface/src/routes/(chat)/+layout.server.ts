import type { LayoutServerLoad } from './$types';
import type { Conversation } from '$lib/types';

export const load: LayoutServerLoad = async ({ locals }) => {
	// get all conversations for the sidebar
	try {
		return {
			conversations: (await locals.pb.collection('conversations').getFullList({
				sort: '-updated'
			})) as Conversation[]
		};
	} catch (error) {
		return { conversations: [] as Conversation[], error };
	}
};
