<script lang="ts">
	import ChatInput from '$lib/components/chat-input.svelte';
	import { Switch } from '$lib/components/ui/switch/index';

	let switch1 = $state(false);
	let switch2 = $state(false);
	let switch3 = $state(true);
</script>

<div class="container flex h-full flex-col px-0">
	<div class="flex-1 overflow-y-auto">
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
					<div class="flex items-center gap-4">
						<span class="grow-1 w-1/2 shrink-0 text-right">Some setting</span>
						<div class="grow-1 flex w-1/2 shrink-0 justify-start">
							<Switch aria-readonly disabled bind:checked={switch1} />
						</div>
					</div>
					<div class="flex items-center gap-4">
						<span class="grow-1 w-1/2 shrink-0 text-right">Some much longer setting</span>
						<div class="grow-1 flex w-1/2 shrink-0 justify-start">
							<Switch bind:checked={switch2} />
						</div>
					</div>
					<div class="flex items-center gap-4">
						<span class="grow-1 w-1/2 shrink-0 text-right">Some other setting</span>
						<div class="grow-1 flex w-1/2 shrink-0 justify-start">
							<Switch bind:checked={switch3} />
						</div>
					</div>
				</div>
			</div>
		</div>
	</div>
	<ChatInput />
</div>
