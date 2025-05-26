export type Role = 'user' | 'model';

export interface Message {
	id: string | null;
	conversation: string | null;
	text: string;
	role: Role;
	created: string;
	rating: number;
	comment: string;
}

export interface Conversation {
	id: string;
	user: string;
	created: string;
	updated: string;
	// setting1: boolean;
	configuration: string;
}

export interface Configuration {
	id: string;
	default: boolean;
}
