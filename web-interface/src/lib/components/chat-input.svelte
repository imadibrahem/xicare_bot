<script lang="ts">
	import Button from '$lib/components/ui/button/button.svelte';
	import ArrowUp from '@lucide/svelte/icons/arrow-up';

	import { cn } from '$lib/utils';

	import type { HTMLFormAttributes } from 'svelte/elements';

	interface ChatInputProps {
		text?: string;
		onclick?: () => void;
	}

	let {
		class: className,
		text = $bindable(''),
		onclick,
		...rest
	}: HTMLFormAttributes & ChatInputProps = $props();

	let textarea: HTMLTextAreaElement;

	const adjustHeight = () => {
		if (textarea) {
			textarea.style.height = 'auto';
			textarea.style.height = `${textarea.scrollHeight}px`;
		}
	};
</script>

<div
	class="from-background pointer-events-none sticky bottom-0 -mt-14 shrink-0 resize-none bg-gradient-to-t from-50% to-transparent px-4 pb-10 pt-14 md:px-10"
>
	<form
		class={cn(
			className,
			'bg-secondary border-foreground pointer-events-auto flex gap-x-4 border-[1px] p-4'
		)}
		{...rest}
	>
		<textarea
			name="query"
			class={cn(
				className,
				'bg-secondary focus:border-foreground w-full resize-none self-center overflow-hidden outline-none focus:ring-0'
			)}
			placeholder="Type your message here..."
			autocomplete="off"
			bind:this={textarea}
			bind:value={text}
			oninput={adjustHeight}
			rows="1"
		></textarea>
		<Button size="icon" class="h-8 w-8 shrink-0 self-end rounded-full" {onclick}>
			<ArrowUp />
		</Button>
	</form>
</div>
