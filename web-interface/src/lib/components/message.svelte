<script lang="ts">
	import { marked } from 'marked';
	import { cn } from '$lib/utils';

	import type { Message } from '$lib/types';
	import type { SvelteHTMLElements } from 'svelte/elements';
	import type { WithElementRef } from 'bits-ui';

	// Configure marked to open links in new tabs
	marked.use({
		renderer: {
			link({ href, title, text }) {
				const titleAttr = title ? `title="${title}"` : '';
				return `<a href="${href}" ${titleAttr} target="_blank" rel="noopener noreferrer">${text}</a>`;
			}
		}
	});

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
	bind:this={ref}
	class={cn(
		'flex items-start md:mx-4',
		role === 'user' ? 'justify-end' : 'justify-start',
		className
	)}
>
	{#if role !== 'user'}
		<enhanced:img src="$lib/img/Chatbot_Logo.png" alt="Logo EA Chatbot" class="w-14 py-4" />
	{/if}
	<div
		class={cn(
			{ 'text-right': role === 'user' },
			{ 'bg-muted rounded-xl': role === 'user' },
			role === 'user' ? 'self-end' : 'self-start',
			'flex flex-col gap-0.5 px-4 py-2'
		)}
	>
		<div
			class="[&_a:hover]:text-foreground leading-relaxed [&_a:hover]:underline [&_a]:text-[#c41b31] [&_li]:my-1 [&_ol]:my-3 [&_ol]:list-decimal [&_ol]:pl-5 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0 [&_p]:my-3 [&_ul]:my-3 [&_ul]:list-disc [&_ul]:pl-5"
		>
			{@html marked.parse(text)}
		</div>
		<span class="pt-1 text-xs opacity-80"
			>{new Date(created).toLocaleTimeString('de-DE', timeOptions)}</span
		>
	</div>
</div>
