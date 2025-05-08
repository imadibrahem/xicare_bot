<script lang="ts">
	import * as Card from '$lib/components/ui/card';
	import { Input } from '$lib/components/ui/input';
	import * as Form from '$lib/components/ui/form/index';

	import { enhance } from '$app/forms';
	import { superForm } from 'sveltekit-superforms';
	import { zodClient } from 'sveltekit-superforms/adapters';
	import { formSchema } from './schema';

	import type { PageProps } from './$types.js';

	let { data, form }: PageProps = $props();

	const formValidation = superForm(data.formValidation, {
		validators: zodClient(formSchema)
	});
</script>

<main class="flex h-screen w-screen items-center justify-center">
	<Card.Root class="m-4 w-96">
		<Card.Header>
			<Card.Title class="text-2xl">Login</Card.Title>
			<Card.Description>Enter your username below to log in</Card.Description>
		</Card.Header>
		<Card.Content>
			<form class="grid" action="?/login" method="POST" use:enhance>
				<Form.Field form={formValidation} name="username">
					<Form.Control>
						{#snippet children({ props })}
							<Form.Label>Username</Form.Label>
							<Input type="text" {...props} />
						{/snippet}
					</Form.Control>
					<Form.Description />
					<Form.FieldErrors />
				</Form.Field>
				<Form.Field form={formValidation} name="password">
					<Form.Control>
						{#snippet children({ props })}
							<Form.Label>Password</Form.Label>
							<Input type="password" {...props} />
						{/snippet}
					</Form.Control>
					<Form.Description />
					<Form.FieldErrors />
				</Form.Field>
				<Form.Button class="mt-2 w-full">Login</Form.Button>
				{#if form && !form.success}
					<span class="mt-2 text-red-500">{form.message}</span>
				{/if}
			</form>
		</Card.Content>
	</Card.Root>
</main>
