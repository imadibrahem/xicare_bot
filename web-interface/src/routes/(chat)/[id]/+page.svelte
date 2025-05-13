<script lang="ts">
	import Message from '$lib/components/message.svelte';
	import ChatInput from '$lib/components/chat-input.svelte';
	import Generating from '$lib/components/generating.svelte';

	import { onDestroy, onMount, untrack } from 'svelte';
	import { page } from '$app/state';
	import { toast } from 'svelte-sonner';
	import { pb } from '$lib/pocketbase.svelte';
	import { initialMessage } from '$lib/message.svelte';
	import { PUBLIC_GEN_URL } from '$env/static/public';

	import type { Message as MessageType } from '$lib/types';
	import type { PageProps } from './$types';
	import { afterNavigate, goto } from '$app/navigation';
	import { currentUser } from '$lib/pocketbase.svelte';

	let { data }: PageProps = $props();
	let messages = $state(data.messages);

	let text = $state('');
	let generating = $state(false);

	const generateResponse = async (message: string | null = null) => {
		let messageText = '';
		if (message) messageText = message;
		// Get user message and reset the textarea
		else {
			messageText = text;
			text = '';
		}

		// Send message to generation endpoint with JWT
		generating = true;
		try {
			const response = await fetch(`${PUBLIC_GEN_URL}/generate`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${currentUser.token}`
				},
				body: JSON.stringify({ conversationId: page.params.id, message: messageText })
			});
			if (response.status !== 200) {
				toast.error('Error generating message');
			}
			generating = false;
			const token = response.headers.get('Authorization');
			if (token) {
				pb.authStore.save(token.slice('Bearer '.length));
				pb.collection('users').authRefresh();
			}
		} catch (error) {
			toast.error('Error sending message');
			console.error('Error sending message:', error);
		}
	};

	// Update messages when data changes (during navigation)
	$effect(() => {
		messages = data.messages;
	});

	let unsubscribe: () => void;
	onMount(async () => {
		// Add pocketbase subscriber for messages
		try {
			unsubscribe = await pb
				.collection('messages')
				.subscribe<MessageType>('*', async ({ action, record }) => {
					if (action === 'create') {
						messages.push({
							id: record.id,
							conversation: record.conversation,
							text: record.text,
							role: record.role,
							created: record.created
						});
					} else if (action === 'delete') {
						messages = messages.filter((message) => message.id !== record.id);
					}
				});
		} catch (error) {
			toast.error('Error subscribing to messages');
			console.error('Error subscribing to messages:', error);
		}

		// If page get's initialized with a message, send that one off
		const message = initialMessage.text;
		if (message) {
			initialMessage.text = '';
			generateResponse(message);
		}
	});
	// Unsubscribe on dismounting component
	onDestroy(() => {
		unsubscribe();
	});

	let windowScrollY = $state(0);
	let windowHeight = $state(0);
	// svelte-ignore non_reactive_update
	let documentHeight = 0;
	// Check scroll position before update (enable autoscrolling, if is at the bottom)
	let autoscroll = $derived(windowHeight + windowScrollY >= documentHeight - 20);
	// Autoscroll to the bottom when new message comes in
	const scrollToBottom = () => {
		window.scrollTo(0, documentHeight);
	};
	$effect(() => {
		messages.length;
		if (autoscroll) scrollToBottom();
	});
	afterNavigate(scrollToBottom);
</script>

<svelte:window bind:scrollY={windowScrollY} bind:innerHeight={windowHeight} />
<svelte:body bind:offsetHeight={documentHeight} />

<div class="container flex h-full flex-col px-0">
	<div class="flex-1">
		<div
			class="mx-4 flex h-full flex-col justify-end gap-y-4 pb-8 pt-4 md:mx-10 md:gap-y-8 md:pb-10 md:pt-0"
		>
			{#each messages as message (message.id)}
				<Message {...message} />
			{/each}
			{#if generating}
				<Generating />
			{/if}
		</div>
	</div>
	<ChatInput
		bind:text
		onclick={() => {
			generateResponse();
		}}
	/>
</div>
