<script lang="ts">
	import Message from '$lib/components/message.svelte';
	import ChatInput from '$lib/components/chat-input.svelte';

	import type { Message as MessageType } from '$lib/types';

	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const messages = <MessageType[]>$derived([...data.messages]);
</script>

<div class="container flex h-full flex-col px-0">
	<div class="flex-1 overflow-y-auto">
		<div class="mx-4 flex h-full flex-col justify-end gap-y-4 py-4 md:mx-10 md:gap-y-8">
			{#each messages as message (message.id)}
				<Message {...message} />
			{/each}
		</div>
	</div>
	<ChatInput />
</div>
