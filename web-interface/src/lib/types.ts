export type Role = 'user' | 'norbert';

export interface Message {
	id: string | null;
	conversation: string | null;
	text: string;
	role: Role;
	created: string;
}

export interface Conversation {
	id: string;
	user: string;
	created: string;
	updated: string;
	awareness: boolean;
	politeness: boolean;
}
