<script lang="ts">
	import ChatInput from '$lib/components/chat-input.svelte';
	// import { Switch } from '$lib/components/ui/switch/index';

	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';
	import { currentUser, pb } from '$lib/pocketbase.svelte';
	import { initialMessage } from '$lib/message.svelte';

	import type { Conversation, Configuration } from '$lib/types';

	// let settings = $state([
	// 	{
	// 		id: 'setting1',
	// 		description: 'Einstellung 1',
	// 		value: false
	// 	}
	// ]);

	let text = $state('');

	const createConversation = async () => {
		// Get user message and reset the textarea
		const message = text;
		text = '';

		try {
			// Get default config
			const configurations = await pb.collection('configurations').getList<Configuration>(1, 1, {
				filter: 'default = true',
				fetch: fetch
			});

			// The first item in the randomized list is the random entry
			let configuration: Configuration;
			if (configurations.items.length > 0) {
				configuration = configurations.items[0];
			} else {
				throw Error('No default configuration found.');
			}

			// Create the conversation and navigate to it
			const conversation = await pb.collection('conversations').create<Conversation>({
				user: currentUser.record?.id,
				configuration: configuration.id
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
			<div class="flex min-h-[60vh] w-full flex-col items-center justify-center gap-10 text-center">
				<enhanced:img src="$lib/img/Chatbot_Icon.png" alt="Icon EA Chatbot" class="w-20" />
				<div class="max-w-2xl text-center [&_p:not(:first-child)]:mt-4">
					<p class="[&:not(:first-child)]:mt-6">
						<strong>
							SUSI – Ihr digitaler Assistent beim Einheitlichen Ansprechpartner Berlin.
						</strong>
						<br />
						Ich unterstütze Sie dabei, schnell und unkompliziert den passenden Online-Dienst für Ihr
						Anliegen in Berlin zu finden – ob als Privatperson, Unternehmen oder Organisation.
						<br />
						Schön, dass Sie da sind!
					</p>
				</div>
				<!-- <div class="flex flex-col gap-6">
					<div>
						<p>Conversation setting setting</p>
						<p><em>Can't be changed after conversation has started</em></p>
					</div>
					<div class="flex flex-col gap-4">
						{#each settings as setting}
							<div class="grid grid-cols-4 items-center gap-4">
								<span class="col-span-3">{setting.description}</span>
								<Switch bind:checked={setting.value} />
							</div>
						{/each}
					</div>
				</div> -->
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
