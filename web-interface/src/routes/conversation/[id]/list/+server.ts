import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import type { Message } from '$lib/types';

export const GET: RequestHandler = async ({ locals, params }) => {
	// Get all messages in the conversation
	try {
		const messages = (await locals.pb.collection('messages').getFullList({
			filter: locals.pb.filter('conversation = {:id}', { id: params.id }),
			sort: 'created'
		})) as Message[];

		return json(
			messages.map(({ role, text, created }) => {
				return { role, text, created };
			})
		);
	} catch (error) {
		return new Response(`Error reading database: ${error}`, { status: 500 });
	}
};
