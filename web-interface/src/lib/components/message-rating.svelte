<script lang="ts">
	import ThumbsUp from '@lucide/svelte/icons/thumbs-up';
	import ThumbsDown from '@lucide/svelte/icons/thumbs-down';
	import ArrorRight from '@lucide/svelte/icons/arrow-right';

	import { slide } from 'svelte/transition';
	import { toast } from 'svelte-sonner';

	import { cn } from '$lib/utils';
	import { pb } from '$lib/pocketbase.svelte';

	import type { Message } from '$lib/types';

	let { id, conversation, text, role, rating, comment }: Omit<Message, 'created'> & { id: string } =
		$props();

	const setRating = async (rating: number) => {
		try {
			await pb
				.collection('messages')
				.update<Message>(id, { conversation, text, role, rating: rating, comment: commentText });
		} catch (error) {
			toast.error('Fehler beim Speichern der Wertung');
			console.error('Failed to to save rating to database:', error);
		}
	};

	let commentText = $state(comment);
	const submitComment = async () => {
		try {
			await pb
				.collection('messages')
				.update<Message>(id, { conversation, text, role, rating: rating, comment: commentText });
			toast.success('Kommentar gespeichert');
		} catch (error) {
			toast.error('Fehler beim Speichern des Kommentars');
			console.error('Failed to to save comment to database:', error);
		}
	};
</script>

<div class="flex md:mr-4">
	<div class="flex">
		<button
			class={cn(
				'group-hover/message:text-muted-foreground inline-flex p-1 transition-all [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0',
				rating > 0 ? 'text-foreground group-hover/message:text-foreground' : 'text-muted'
			)}
			onclick={() => {
				if (rating < 1) {
					setRating(1);
				} else {
					setRating(0);
				}
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
				if (rating > -1) {
					setRating(-1);
				} else {
					setRating(0);
				}
			}}
		>
			<ThumbsDown />
		</button>
	</div>
	{#if rating !== 0}
		<div
			class="border-muted has-[button:hover]:border-muted-foreground ml-4 flex items-stretch overflow-hidden rounded-md border-2"
			transition:slide={{ duration: 500, axis: 'x' }}
		>
			<input
				class="w-24 px-1 text-sm outline-none focus:ring-0 md:w-40"
				type="text"
				placeholder="(Optionale) Details..."
				bind:value={commentText}
			/>
			<button
				class="bg-muted hover:bg-muted-foreground hover:text-background flex w-5 items-center justify-center [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0"
				onclick={submitComment}
			>
				<ArrorRight />
			</button>
		</div>
	{/if}
</div>
