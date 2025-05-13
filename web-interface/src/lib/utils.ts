import { type ClassValue, clsx } from 'clsx';
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

	navigator.clipboard.writeText(messagesString);
};
