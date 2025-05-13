<script lang="ts">
	import { Button } from '$lib/components/ui/button/index.js';
	import { cn } from '$lib/utils.js';
	import PanelLeft from '@lucide/svelte/icons/panel-left';
	import type { ComponentProps } from 'svelte';
	import { useSidebar } from './context.svelte.js';

	let {
		ref = $bindable(null),
		sidebarObj = $bindable(null), // Add new bindable prop
		class: className,
		onclick,
		...restProps
	}: ComponentProps<typeof Button> & {
		onclick?: (e: MouseEvent) => void;
		sidebarObj?: any; // Add to type definition
	} = $props();

	const sidebar = useSidebar();
	// Assign the sidebar object to the bindable
	$effect(() => {
		sidebarObj = sidebar;
	});
</script>

<Button
	type="button"
	onclick={(e) => {
		onclick?.(e);
		sidebar.toggle();
	}}
	data-sidebar="trigger"
	variant="ghost"
	size="icon"
	class={cn('h-7 w-7', className)}
	{...restProps}
>
	<PanelLeft />
	<span class="sr-only">Toggle Sidebar</span>
</Button>
