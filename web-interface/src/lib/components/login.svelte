<script lang="ts">
	import * as Card from '$lib/components/ui/card';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Button } from '$lib/components/ui/button';

	import { toast } from 'svelte-sonner';
	import { pb } from '$lib/pocketbase.svelte';

	let { onlogin }: { onlogin?: () => void } = $props();

	let username = $state('');
	let password = $state('');
	const login = async () => {
		if (!username || !password) {
			toast.error('Username and password must be given');
			return;
		}

		try {
			await pb.collection('users').authWithPassword(username, password);
		} catch {
			toast.error('Wrong username or password');
		}
		username = '';
		password = '';
		if (onlogin) onlogin();
	};
</script>

<main class="flex h-screen w-screen items-center justify-center">
	<Card.Root class="m-4 w-96">
		<Card.Header>
			<Card.Title class="text-2xl">Login</Card.Title>
			<Card.Description>Enter your email below to login to your account</Card.Description>
		</Card.Header>
		<Card.Content>
			<form
				class="grid gap-4"
				onsubmit={(e) => {
					e.preventDefault();
				}}
			>
				<div class="grid gap-2">
					<Label for="username">Username</Label>
					<Input id="username" bind:value={username} />
				</div>
				<div class="grid gap-2">
					<Label for="password">Password</Label>
					<Input id="password" type="password" bind:value={password} />
				</div>
				<Button type="submit" class="w-full" onclick={login}>Login</Button>
			</form>
		</Card.Content>
	</Card.Root>
</main>
