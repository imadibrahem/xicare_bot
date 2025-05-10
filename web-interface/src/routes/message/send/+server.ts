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
		await locals.pb.collection('messages').create<Message>({
			conversation: message.conversation,
			text: message.text,
			role: message.role
		});

		// Generate response and save it to database
		const response = {
			conversation: message.conversation,
			text: 'Donec et porttitor dui. Integer lacinia, dolor ac porta accumsan, nunc nibh auctor nulla, sit amet fermentum nisi nisi a lorem. Ut ac tortor erat. Praesent vel consequat arcu. Proin sodales malesuada turpis vitae accumsan. Aenean ut purus augue. Nullam vitae dui eros. Sed rhoncus enim ac enim tincidunt porttitor. Orci varius natoque penatibus et magnis dis parturient montes, nascetur ridiculus mus. Ut ultrices libero massa, semper efficitur nibh blandit ut. Nam elit felis, feugiat eget aliquam et, mattis a sapien.',
			role: 'norbert'
		};
		const { id, created } = await locals.pb.collection('messages').create<Message>(response);

		return json({ id, created, ...response });
	} catch (error) {
		return new Response(`Error generaring response: ${error}`, { status: 500 });
	}
};
