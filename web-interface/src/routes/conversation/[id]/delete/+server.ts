import type { RequestHandler } from './$types';

export const DELETE: RequestHandler = async ({ locals, params }) => {
	// Delete a conversation by the id
	if (await locals.pb.collection('conversations').delete(params.id)) {
		return new Response(null, { status: 204 });
	}
	return new Response('Conversation not found', { status: 404 });
};
