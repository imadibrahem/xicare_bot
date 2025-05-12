import { pb } from '$lib/pocketbase.svelte';

import type { LayoutLoad } from './$types';
import type { Conversation } from '$lib/types';

export const load: LayoutLoad = async ({ fetch }) => {
	return {
		conversations: (await pb.collection('conversations').getFullList({
			sort: '-updated',
			fetch: fetch
		})) as Conversation[]
	};
};
