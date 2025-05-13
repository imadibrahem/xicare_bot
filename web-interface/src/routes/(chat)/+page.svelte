<script lang="ts">
	import ChatInput from '$lib/components/chat-input.svelte';
	import { Switch } from '$lib/components/ui/switch/index';

	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';
	import { currentUser, pb } from '$lib/pocketbase.svelte';

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
			await goto(`/${conversation.id}?message=${message}`);
		} catch (error) {
			toast.error('Error creating conversation');
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
				<p class="[&:not(:first-child)]:mt-6">
					Vivamus molestie commodo ipsum, quis viverra enim ultricies et. Nam ornare magna at augue
					bibendum, ac mattis sem lobortis. Duis at vestibulum urna, vitae accumsan erat. Sed velit
					ipsum, tincidunt et ex eu, pulvinar sagittis dolor. Vestibulum in dictum quam. Donec
					vestibulum id mi ac congue. Duis ut tristique magna, vitae dapibus dolor. Pellentesque
					eget risus nec est ultrices euismod.
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
	</div>
	<ChatInput bind:text onclick={createConversation} />
</div>
