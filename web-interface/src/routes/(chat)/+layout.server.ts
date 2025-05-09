import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = async ({ locals }) => {
	return {
		conversations: await locals.pb.collection('conversations').getFullList({
			sort: '-updated'
		})
	};
};
