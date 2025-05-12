import { pb } from '$lib/pocketbase.svelte';

import type { PageLoad } from './$types';
import type { Message } from '$lib/types';

export const load: PageLoad = async ({ fetch, params }) => {
	return {
		messages: (await pb.collection('messages').getFullList({
			filter: pb.filter('conversation = {:id}', { id: params.id }),
			sort: 'created',
			fetch: fetch
		})) as Message[]
	};
};
