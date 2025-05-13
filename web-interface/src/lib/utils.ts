import { type ClassValue, clsx } from 'clsx';
import { toast } from 'svelte-sonner';
import { twMerge } from 'tailwind-merge';

import type { Message } from '$lib/types';

export function cn(...inputs: ClassValue[]) {
	return twMerge(clsx(inputs));
}

export const copyMessagesToClipboard = (messages: Message[]) => {
	const messagesString = messages.reduce(
		(s, message) =>
			s +
			`${message.role} [${new Date(message.created).toLocaleTimeString('en-US')}]: ${message.text}\n\n`,
		''
	);
	try {
		navigator.clipboard.writeText(messagesString);
		toast('Copied to clipboard');
	} catch (error) {
		console.error('Failed to copy messages to clipboard:', error);
	}
};
