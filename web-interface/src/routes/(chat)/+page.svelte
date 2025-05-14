<script lang="ts">
	import ChatInput from '$lib/components/chat-input.svelte';
	import { Switch } from '$lib/components/ui/switch/index';

	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';
	import { currentUser, pb } from '$lib/pocketbase.svelte';
	import { initialMessage } from '$lib/message.svelte';

	let settings = $state([
		{
			id: 'setting1',
			description: 'Einstellung 1',
			value: false
		}
	]);

	let text = $state('');

	const createConversation = async () => {
		// Get user message and reset the textarea
		const message = text;
		text = '';

		try {
			// Create the conversation and navigate to it
			const conversation = await pb.collection('conversations').create({
				user: currentUser.record?.id,
				...settings.reduce((obj: { [key: string]: boolean }, { id, value }) => {
					obj[id] = value;
					return obj;
				}, {})
			});
			// Set the global message state to transfer the first message to the new conversation
			initialMessage.text = message;
			// Navigate to the new conversation
			await goto(`/${conversation.id}`);
		} catch (error) {
			toast.error('Fehler beim Erstellen eines neuen Chats');
			console.error('Error creating conversation:', error);
		}
	};
</script>

<div class="container flex h-full flex-col px-0">
	<div class="flex-1">
		<div class="mx-4 flex h-full flex-col items-center justify-center gap-10 py-4 md:mx-10">
			<div class="max-w-2xl text-center">
				<p class="[&:not(:first-child)]:mt-6">
					Lorem ipsum dolor sit amet, consectetur adipiscing elit. Praesent nec maximus nisl, vitae
					faucibus turpis. Donec viverra lacinia dapibus. Etiam laoreet elit enim, ut pellentesque
					diam egestas sed. Nam feugiat efficitur ultricies. Nunc efficitur sem magna. Etiam rutrum
					quis erat quis eleifend. In hac habitasse platea dictumst. In id metus mauris. In sed
					velit dui.
				</p>
			</div>
			<div class="flex w-full flex-col items-center gap-6 text-center">
				<div class="flex flex-col">
					<span>Entwicklereinstellungen</span>
					<span><em>Können nach Beginn des Chats nicht mehr geändert werden</em></span>
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
	</div>
	<ChatInput
		bind:text
		onclick={() => {
			if (text) createConversation();
		}}
	/>
</div>
