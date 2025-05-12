<script lang="ts">
	import * as Sidebar from '$lib/components/ui/sidebar/index';
	import ChatSidebar from '$lib/components/chat-sidebar.svelte';

	import { onNavigate } from '$app/navigation';
	import { page } from '$app/state';
	import type { SidebarState } from '$lib/components/ui/sidebar/index';
	import type { LayoutProps } from './$types';
	import ChatHeader from '$lib/components/chat-header.svelte';

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
	<ChatSidebar
		conversations={data.conversations}
		error={data.error}
		currentId={page.params.id}
		bind:sidebar
	/>
	<main class="relative flex min-h-screen w-full flex-col">
		<ChatHeader
			conversation={data.conversations.find((conversation) => page.params.id === conversation.id)}
		/>
		<div class="flex-1">
			{@render children()}
		</div>
	</main>
</Sidebar.Provider>
