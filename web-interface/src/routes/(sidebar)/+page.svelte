<script lang="ts">
	import Button from '$lib/components/ui/button/button.svelte';
	import ArrowUp from '@lucide/svelte/icons/arrow-up';

	let textarea: HTMLTextAreaElement;

	const adjustHeight = () => {
		if (textarea) {
			textarea.style.height = 'auto';
			textarea.style.height = `${textarea.scrollHeight}px`;
		}
	};
</script>

<div class="container flex h-full flex-col px-0">
	<div class="flex-1 overflow-y-auto">
		<div class="mx-4 flex h-full flex-col items-center justify-center py-4 md:mx-10">
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
			<div>
				<span>Conversation setting setting</span>
				<span>Can't be changed after conversation has started</span>
			</div>
		</div>
	</div>
	<div
		class="from-background pointer-events-none sticky bottom-0 -mt-14 shrink-0 resize-none bg-gradient-to-t from-50% to-transparent px-4 pb-10 pt-14 md:px-10"
	>
		<div class="bg-secondary border-foreground pointer-events-auto flex gap-x-4 border-[1px] p-4">
			<!-- md:text-lg -->
			<textarea
				name="query"
				class="bg-secondary focus:border-foreground w-full resize-none self-center overflow-hidden outline-none focus:ring-0"
				placeholder="Type your message here..."
				bind:this={textarea}
				oninput={adjustHeight}
				rows="1"
			></textarea>
			<Button size="icon" class="h-8 w-8 shrink-0 self-end rounded-full">
				<ArrowUp />
			</Button>
		</div>
	</div>
</div>
