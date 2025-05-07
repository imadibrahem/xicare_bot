<script lang="ts">
	import * as Tooltip from '$lib/components/ui/tooltip';
	import Copy from '@lucide/svelte/icons/clipboard-copy';
	import * as Sidebar from '$lib/components/ui/sidebar/index';
	import ChatSidebar from '$lib/components/chat-sidebar.svelte';

	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();
</script>

<Sidebar.Provider>
	<ChatSidebar />
	<main class="relative flex min-h-screen w-full flex-col">
		<div
			class="bg-background border-foreground sticky top-0 z-10 flex w-full shrink-0 justify-between border-[1px] md:pointer-events-none md:border-none md:bg-transparent"
		>
			<Sidebar.Trigger class="bg-background pointer-events-auto m-2 md:m-2" />
			<Tooltip.Provider>
				<Tooltip.Root>
					<Tooltip.Trigger
						class="bg-background ring-offset-background focus-visible:ring-ring hover:bg-accent hover:text-accent-foreground pointer-events-auto m-2 inline-flex h-7 w-7 items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 md:m-2 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0"
					>
						<Copy />
					</Tooltip.Trigger>
					<Tooltip.Content>
						<p>Copy conversation to clipboard</p>
					</Tooltip.Content>
				</Tooltip.Root>
			</Tooltip.Provider>
		</div>
		<div class="flex-1">
			{@render children()}
		</div>
	</main>
</Sidebar.Provider>
