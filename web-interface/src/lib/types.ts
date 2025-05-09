export type Role = 'user' | 'norbert';

export interface Message {
	id: string;
	conversation: string;
	text: string;
	role: Role;
	created: Date;
}

export interface Conversation {
	id: string;
	user: string;
	created: Date;
	updated: Date;
}
