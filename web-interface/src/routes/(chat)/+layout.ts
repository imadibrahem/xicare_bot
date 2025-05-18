import { pb } from '$lib/pocketbase.svelte';

import type { LayoutLoad } from './$types';
import type { Conversation } from '$lib/types';

export const load: LayoutLoad = async ({ fetch }) => {
	try {
		return {
			conversations: await pb.collection('conversations').getFullList<Conversation>({
				sort: '-updated',
				fetch: fetch
			})
		};
	} catch (error) {
		console.error('Error fetching conversations:', error);
	}
	return { conversations: [] };
};
