<script lang="ts">
	import Message from '$lib/components/message.svelte';
	import ChatInput from '$lib/components/chat-input.svelte';
	import Generating from '$lib/components/generating.svelte';

	import { page } from '$app/state';
	import type { Message as MessageType } from '$lib/types';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	let messages = $state(data.messages);

	let text = $state('');
	let generating = $state(false);

	// Update messages when data changes (during navigation)
	$effect(() => {
		messages = data.messages;
	});
</script>

<div class="container flex h-full flex-col px-0">
	<div class="flex-1">
		<div
			class="mx-4 flex h-full flex-col justify-end gap-y-4 pb-8 pt-4 md:mx-10 md:gap-y-8 md:pb-10 md:pt-0"
		>
			{#if data.error}
				<div class="flex h-full items-center justify-center">
					<span class="text-lg text-red-800"
						><strong>Error loading messages:</strong> {data.error}</span
					>
				</div>
			{:else}
				{#each messages as message (message.id)}
					<Message {...message} />
				{/each}
				{#if generating}
					<Generating />
				{/if}
			{/if}
		</div>
	</div>
	<ChatInput
		bind:text
		onclick={async () => {
			// Add user message to messages and reset the textarea
			const query = {
				conversation: page.params.id,
				text: text,
				role: 'user',
				created: String(new Date())
			} as MessageType;
			messages.push({ ...query, id: self.crypto.randomUUID() });
			text = '';

			// Get the response and add it to the messages
			generating = true;
			const response = await fetch('/message/send', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ message: query, settings: [] })
			});
			const reply = (await response.json()) as MessageType;
			generating = false;
			messages.push(reply);
		}}
	/>
</div>
