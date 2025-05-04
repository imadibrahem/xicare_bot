<script lang="ts">
	import type { Message } from '$lib/types';

	import { cn } from '$lib/utils';

	let { text, time, role }: Message = $props();
</script>

<div
	class={cn(
		{ 'text-right': role === 'user' },
		{ 'bg-primary': role === 'user' },
		{ 'text-primary-foreground': role === 'user' },
		role === 'user' ? 'self-end' : 'self-start',
		'flex flex-col gap-0.5 p-4'
	)}
>
	<span class="md:text-lg">{text}</span>
	<span class="text-sm opacity-80">{time.toLocaleTimeString('en-US')}</span>
</div>
