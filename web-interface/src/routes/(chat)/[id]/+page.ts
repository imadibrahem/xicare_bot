import { pb } from '$lib/pocketbase.svelte';

import type { PageLoad } from './$types';
import type { Message } from '$lib/types';

export const load: PageLoad = async ({ fetch, params }) => {
	try {
		return {
			messages: await pb.collection('messages').getFullList<Message>({
				filter: pb.filter('conversation = {:id}', { id: params.id }),
				sort: 'created',
				fetch: fetch
			})
		};
	} catch (error) {
		console.error('Error fetching messages:', error);
	}
	return { messages: [] };
};
