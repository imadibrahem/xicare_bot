<script lang="ts">
	import Message from '$lib/components/message.svelte';
	import ChatInput from '$lib/components/chat-input.svelte';
	import { Switch } from '$lib/components/ui/switch/index';

	import { goto, invalidateAll } from '$app/navigation';
	import type { Message as MessageType } from '$lib/types';

	let settings = $state([
		{
			id: 'awareness',
			description: 'Norbert Wiener is aware of his death and current developments',
			value: false
		},
		{
			id: 'politeness',
			description: 'He insists upon being treated respectfully and politely',
			value: true
		}
	]);

	let text = $state('');

	let messages = <MessageType[]>$state([]);
</script>

<div class="container flex h-full flex-col px-0">
	<div class="flex-1 overflow-y-auto">
		{#if !messages.length}
			<div class="mx-4 flex h-full flex-col items-center justify-center gap-10 py-4 md:mx-10">
				<div class="max-w-2xl text-center">
					<p class="[&:not(:first-child)]:mt-6">
						Lorem ipsum dolor sit amet, consectetur adipiscing elit. Praesent nec maximus nisl,
						vitae faucibus turpis. Donec viverra lacinia dapibus. Etiam laoreet elit enim, ut
						pellentesque diam egestas sed. Nam feugiat efficitur ultricies. Nunc efficitur sem
						magna. Etiam rutrum quis erat quis eleifend. In hac habitasse platea dictumst. In id
						metus mauris. In sed velit dui.
					</p>
					<p class="[&:not(:first-child)]:mt-6">
						Vivamus molestie commodo ipsum, quis viverra enim ultricies et. Nam ornare magna at
						augue bibendum, ac mattis sem lobortis. Duis at vestibulum urna, vitae accumsan erat.
						Sed velit ipsum, tincidunt et ex eu, pulvinar sagittis dolor. Vestibulum in dictum quam.
						Donec vestibulum id mi ac congue. Duis ut tristique magna, vitae dapibus dolor.
						Pellentesque eget risus nec est ultrices euismod.
					</p>
				</div>
				<div class="flex w-full flex-col items-center gap-6 text-center">
					<div class="flex flex-col">
						<span>Conversation setting setting</span>
						<span><em>Can't be changed after conversation has started</em></span>
					</div>
					<div class="flex w-full flex-col gap-4">
						<!--  Render settings -->
						{#each settings as setting}
							<div class="flex items-center gap-4">
								<span class="grow-1 w-1/2 shrink-0 text-right">{setting.description}</span>
								<div class="grow-1 flex w-1/2 shrink-0 justify-start">
									<Switch bind:checked={setting.value} />
								</div>
							</div>
						{/each}
					</div>
				</div>
			</div>
		{:else}
			<div
				class="mx-4 flex h-full flex-col justify-end gap-y-4 pb-8 pt-4 md:mx-10 md:gap-y-8 md:pb-10 md:pt-0"
			>
				{#each messages as message (message.id)}
					<Message {...message} />
				{/each}
			</div>
		{/if}
	</div>
	<ChatInput
		bind:text
		onclick={async () => {
			// Add user message to messages and reset the textarea
			const query = {
				id: null,
				conversation: null,
				text: text,
				role: 'user',
				created: String(new Date())
			} as MessageType;
			messages.push(query);
			text = '';

			// Get the response and navigate to the new conversation
			const response = await fetch('/message/send', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					message: query,
					settings: settings.reduce((obj: { [key: string]: boolean }, { id, value }) => {
						obj[id] = value;
						return obj;
					}, {})
				})
			});
			const reply = (await response.json()) as MessageType;
			await invalidateAll();
			await goto(`/${reply.conversation}`);
		}}
	/>
</div>
