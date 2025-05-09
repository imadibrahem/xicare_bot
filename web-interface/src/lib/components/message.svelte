<script lang="ts">
	import { cn } from '$lib/utils';

	import type { Message } from '$lib/types';
	import type { SvelteHTMLElements } from 'svelte/elements';
	import type { WithElementRef } from 'bits-ui';

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
		// { 'border-foreground border-[1px] border-dashed text-primary-foreground': role === 'user' },
		{ '_border-dashed': role === 'user' },
		role === 'user' ? 'self-end' : 'self-start',
		'flex flex-col gap-0.5 p-4 md:mx-4',
		className
	)}
	bind:this={ref}
	{...rest}
>
	<!-- md:text-lg -->
	<span>{text}</span>
	<span class="text-xs opacity-80">{new Date(created).toLocaleTimeString('en-US')}</span>
</div>

<style>
	._border-dashed {
		background-image: url("data:image/svg+xml,%3csvg width='100%25' height='100%25' xmlns='http://www.w3.org/2000/svg'%3e%3crect width='100%25' height='100%25' fill='none' stroke='hsl(0 0 98%)' stroke-width='2' stroke-dasharray='14%2c 14' stroke-dashoffset='0' stroke-linecap='square'/%3e%3c/svg%3e");
	}
</style>
