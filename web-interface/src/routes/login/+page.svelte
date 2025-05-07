<script lang="ts">
	import { Button } from '$lib/components/ui/button';
	import * as Card from '$lib/components/ui/card';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
</script>

<main class="flex h-screen w-screen items-center justify-center">
	<Card.Root class="m-4 w-96">
		<Card.Header>
			<Card.Title class="text-2xl">Login</Card.Title>
			<Card.Description>Enter your username below to log in</Card.Description>
		</Card.Header>
		<Card.Content>
			<div class="grid gap-4">
				<div class="grid gap-2">
					<Label for="username">Username</Label>
					<Input id="username" type="text" placeholder="SomeUser" required />
				</div>
				<div class="grid gap-2">
					<div class="flex items-center">
						<Label for="password">Password</Label>
					</div>
					<Input id="password" type="password" required />
				</div>
				<Button type="submit" class="w-full">Login</Button>
			</div>
		</Card.Content>
	</Card.Root>
</main>
