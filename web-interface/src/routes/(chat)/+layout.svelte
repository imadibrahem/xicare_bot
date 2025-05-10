<script lang="ts">
	import * as Tooltip from '$lib/components/ui/tooltip';
	import Copy from '@lucide/svelte/icons/clipboard-copy';
	import * as Sidebar from '$lib/components/ui/sidebar/index';
	import ChatSidebar from '$lib/components/chat-sidebar.svelte';

	import { onNavigate } from '$app/navigation';
	import { page } from '$app/state';
	import type { SidebarState } from '$lib/components/ui/sidebar/index';
	import { copyMessagesToClipboard } from '$lib/utils';
	import type { LayoutProps } from './$types';

	let { data, children }: LayoutProps = $props();

	let sidebar = $state<SidebarState | null>(null);

	// Close the sidebar on mobile navigation
	onNavigate(() => {
		if (sidebar && sidebar.isMobile && sidebar.open) {
			sidebar.toggle();
		}
	});
</script>

<Sidebar.Provider>
	<ChatSidebar conversations={data.conversations} currentId={page.params.id} />
	<main class="relative flex min-h-screen w-full flex-col">
		<div
			class="bg-background border-foreground sticky top-0 z-10 flex w-full shrink-0 items-center justify-between border-b-[1px] md:pointer-events-none md:border-none md:bg-transparent"
		>
			<Sidebar.Trigger
				bind:sidebarObj={sidebar}
				class="bg-background pointer-events-auto m-2 md:m-2"
			/>
			<!-- Show settings in top bar -->
			{#if page.params.id}
				{#each data.conversations.filter((conversation) => conversation.id === page.params.id) as conversation}
					<em class="p-4 text-center text-sm md:text-base"
						>Norbert Wiener is {!conversation.awareness ? 'not ' : ''}aware of his death and current
						developments and {!conversation.politeness ? 'does not insist ' : 'insists '}upon
						respect and politeness.</em
					>
				{/each}
				<Tooltip.Provider>
					<Tooltip.Root>
						<Tooltip.Trigger
							class="bg-background ring-offset-background focus-visible:ring-ring hover:bg-accent hover:text-accent-foreground pointer-events-auto m-2 inline-flex h-7 w-7 items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 md:m-2 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0"
							onclick={async () => {
								// Fetch all messages
								const response = await fetch(`conversation/${page.params.id}/list`);
								const reply = await response.json();
								copyMessagesToClipboard(reply);
							}}
						>
							<Copy />
						</Tooltip.Trigger>
						<Tooltip.Content>
							<p>Copy conversation to clipboard</p>
						</Tooltip.Content>
					</Tooltip.Root>
				</Tooltip.Provider>
			{/if}
		</div>
		<div class="flex-1">
			{@render children()}
		</div>
	</main>
</Sidebar.Provider>
