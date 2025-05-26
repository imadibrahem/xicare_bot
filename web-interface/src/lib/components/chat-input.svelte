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
	let form: HTMLFormElement;

	// Adjust textarea so it is always as high as text
	const adjustHeight = () => {
		if (textarea) {
			textarea.style.height = 'auto';
			textarea.style.height = `${textarea.scrollHeight}px`;
		}
	};

	// Focus the textarea when form is clicked or focused
	const focusTextarea = () => {
		if (textarea) {
			textarea.focus();
		}
	};

	// Ensure onclick is defined and properly handled
	const handleKeyDown = (event: KeyboardEvent) => {
		if (event.key === 'Enter') {
			if (!event.shiftKey) {
				// Plain Enter - submit the form
				event.preventDefault();
				if (onclick) {
					onclick();
				}
			}
			// Shift+Enter - let default behavior happen (new line)
		}
	};
</script>

<div
	class="from-background pointer-events-none sticky bottom-0 -mt-14 shrink-0 resize-none bg-gradient-to-t from-50% to-transparent px-4 pb-10 pt-14 md:px-10"
>
	<form
		bind:this={form}
		onclick={focusTextarea}
		onfocus={focusTextarea}
		class={cn(
			className,
			'bg-secondary border-foreground pointer-events-auto flex gap-x-4 rounded-xl border-[2px] p-4 dark:border-[1px]'
		)}
		{...rest}
	>
		<textarea
			name="query"
			class={cn(
				className,
				'bg-secondary w-full resize-none self-center overflow-hidden outline-none focus:ring-0'
			)}
			placeholder="Geben Sie hier Ihre Frage ein..."
			autocomplete="off"
			bind:this={textarea}
			bind:value={text}
			oninput={adjustHeight}
			onkeydown={handleKeyDown}
			rows="1"
		></textarea>
		<!-- TODO -->
		<Button
			size="icon"
			class="hover:bg-foreground h-8 w-8 shrink-0 self-end rounded-full bg-[#c41b31]"
			{onclick}
		>
			<ArrowUp />
		</Button>
	</form>
</div>
