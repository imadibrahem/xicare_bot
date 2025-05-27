<script lang="ts">
	import Message from '$lib/components/message.svelte';
	import ChatInput from '$lib/components/chat-input.svelte';
	import Generating from '$lib/components/generating.svelte';

	import { onDestroy, onMount } from 'svelte';
	import { page } from '$app/state';
	import { toast } from 'svelte-sonner';
	import { pb } from '$lib/pocketbase.svelte';
	import { initialMessage } from '$lib/message.svelte';
	import { PUBLIC_GEN_URL } from '$env/static/public';

	import type { Message as MessageType } from '$lib/types';
	import type { PageProps } from './$types';
	import { afterNavigate } from '$app/navigation';
	import { currentUser } from '$lib/pocketbase.svelte';

	let { data }: PageProps = $props();
	let messages = $state(data.messages);

	let text = $state('');
	let generating = $state(false);

	const generateResponse = async (message?: string) => {
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
			// Refresh token before sending request
			await pb.collection('users').authRefresh();

			const response = await fetch(`${PUBLIC_GEN_URL}/generation/generate`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${pb.authStore.token}`
				},
				body: JSON.stringify({ conversationId: page.params.id, message: messageText })
			});
			if (response.status !== 200) {
				toast.error('Fehler beim Generieren der Nachricht');
			}
		} catch (error) {
			toast.error('Fehler beim Senden der Nachricht');
			console.error('Error sending message:', error);
		} finally {
			generating = false;
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
							created: record.created,
							rating: record.rating,
							comment: record.comment
						});
					} else if (action === 'delete') {
						messages = messages.filter((message) => message.id !== record.id);
					} else if (action === 'update') {
						const index = messages.findIndex((message) => message.id === record.id);
						messages[index] = {
							id: record.id,
							conversation: record.conversation,
							text: record.text,
							role: record.role,
							created: record.created,
							rating: record.rating,
							comment: record.comment
						};
					}
				});
		} catch (error) {
			toast.error('Fehler beim Abbonnieren neuer Nachrichten');
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

	// Function to get accurate document height
	function getDocumentHeight() {
		return Math.max(
			document.body.scrollHeight,
			document.documentElement.scrollHeight,
			document.body.offsetHeight,
			document.documentElement.offsetHeight
		);
	}

	// Autoscroll to the bottom when new message comes in
	const scrollToBottom = () => {
		setTimeout(() => {
			const height = getDocumentHeight();
			window.scrollTo({
				top: height
			});
		}, 0);
	};
	let isAtBottom = false;
	$effect.pre(() => {
		// Check if user is at bottom of chat
		isAtBottom = windowHeight + windowScrollY >= getDocumentHeight() - 20;
	});
	// Watch for message changes and scroll if needed
	$effect(() => {
		// Track message changes
		messages.length;

		// Wait for DOM to update with new messages
		setTimeout(() => {
			if (isAtBottom) scrollToBottom();
		}, 0);
	});

	// Scroll after navigation
	afterNavigate(() => {
		// Give DOM time to fully render
		// setTimeout(scrollToBottom, 100);
		scrollToBottom();
	});
</script>

<svelte:window bind:scrollY={windowScrollY} bind:innerHeight={windowHeight} />

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
		disabled={messages.at(-1)?.role === 'user' || generating}
		onclick={() => {
			if (text) generateResponse();
		}}
	/>
</div>
