<script lang="ts">
	import { marked } from 'marked';
	import { cn } from '$lib/utils';

	import type { Message } from '$lib/types';
	import type { SvelteHTMLElements } from 'svelte/elements';
	import type { WithElementRef } from 'bits-ui';

	const timeOptions: Intl.DateTimeFormatOptions = { hour: 'numeric', minute: '2-digit' };

	let {
		text,
		created,
		role,
		class: className,
		ref = $bindable(null),
		...rest
	}: Message & WithElementRef<SvelteHTMLElements['div']> = $props();
</script>

<div
	class={cn(
		{ 'text-right': role === 'user' },
		{ 'bg-muted rounded-xl': role === 'user' },
		role === 'user' ? 'self-end' : 'self-start',
		'flex flex-col gap-0.5 px-4 py-2 md:mx-4',
		className
	)}
	bind:this={ref}
	{...rest}
>
	<div
		class="[&_a]:text-muted-foreground [&_a:hover]:text-foreground leading-relaxed [&_a:hover]:underline [&_p:first-child]:mt-0 [&_p:last-child]:mb-0 [&_p]:my-3"
	>
		{@html marked.parse(text)}
	</div>
	<span class="pt-1 text-xs opacity-80"
		>{new Date(created).toLocaleTimeString('de-DE', timeOptions)}</span
	>
</div>
