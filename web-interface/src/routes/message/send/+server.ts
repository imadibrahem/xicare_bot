import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import type { Message } from '$lib/types';

export const POST: RequestHandler = async ({ locals, request }) => {
	// Get user message from request body
	try {
		const { message, settings } = (await request.json()) as {
			message: Message;
			settings: { id: string; value: string }[];
		};

		// If this is new chat, create a new conversation, add the messages and redirect
		if (!message.conversation) {
			const conversation = { user: locals.userId, ...settings };
			message.conversation = (await locals.pb.collection('conversations').create(conversation)).id;
		}

		// Save message to database
		// await locals.pb.collection('messages').create(message);

		// Generate response and save it to database

		return json({
			id: 'test',
			conversation: message.conversation,
			text: 'REPLY',
			role: 'norbert',
			created: ''
		});
	} catch (error) {
		return new Response(`Error generaring response: ${error}`, { status: 500 });
	}
};
