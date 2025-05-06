<script lang="ts">
	import type { Message } from '$lib/types';

	import { cn } from '$lib/utils';

	let { text, time, role }: Message = $props();
</script>

<div
	class={cn(
		{ 'text-right': role === 'user' },
		// { 'border-foreground border-[1px] border-dashed text-primary-foreground': role === 'user' },
		{ 'border--dashed': role === 'user' },
		role === 'user' ? 'self-end' : 'self-start',
		'flex flex-col gap-0.5 p-4 md:mx-4 '
	)}
>
	<!-- md:text-lg -->
	<span>{text}</span>
	<span class="text-xs opacity-80">{time.toLocaleTimeString('en-US')}</span>
</div>

<style>
	.border--dashed {
		background-image: url("data:image/svg+xml,%3csvg width='100%25' height='100%25' xmlns='http://www.w3.org/2000/svg'%3e%3crect width='100%25' height='100%25' fill='none' stroke='hsl(0 0 98%)' stroke-width='2' stroke-dasharray='14%2c 14' stroke-dashoffset='0' stroke-linecap='square'/%3e%3c/svg%3e");
	}
</style>
