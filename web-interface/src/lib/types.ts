export type Role = 'user' | 'norbert';

export interface Message {
	text: string;
	time: Date;
	role: Role;
}
