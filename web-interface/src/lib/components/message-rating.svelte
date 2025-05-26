<script lang="ts">
	import ThumbsUp from '@lucide/svelte/icons/thumbs-up';
	import ThumbsDown from '@lucide/svelte/icons/thumbs-down';

	import { cn } from '$lib/utils';
	import { pb } from '$lib/pocketbase.svelte';

	import type { Message } from '$lib/types';

	let { id, conversation, text, role, rating, comment }: Omit<Message, 'created'> & { id: string } =
		$props();

	const setRating = async (rating: number) => {
		await pb
			.collection('messages')
			.update<Message>(id, { conversation, text, role, rating: rating, comment });
	};
</script>

<div class="mr-4 flex">
	<button
		class={cn(
			'group-hover/message:text-muted-foreground inline-flex p-1 transition-all [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0',
			rating > 0 ? 'text-foreground group-hover/message:text-foreground' : 'text-muted'
		)}
		onclick={() => {
			setRating(1);
		}}
	>
		<ThumbsUp />
	</button>
	<button
		class={cn(
			'group-hover/message:text-muted-foreground inline-flex p-1 transition-all [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0',
			rating < 0 ? 'text-foreground group-hover/message:text-foreground' : 'text-muted'
		)}
		onclick={() => {
			setRating(-1);
		}}
	>
		<ThumbsDown />
	</button>
</div>
