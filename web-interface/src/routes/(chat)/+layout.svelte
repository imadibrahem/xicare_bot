<script lang="ts">
	import * as Sidebar from '$lib/components/ui/sidebar/index';
	import ChatSidebar from '$lib/components/chat-sidebar.svelte';

	import { onNavigate } from '$app/navigation';
	import { page } from '$app/state';
	import type { SidebarState } from '$lib/components/ui/sidebar/index';
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
	<ChatSidebar
		conversations={data.conversations}
		error={data.error}
		currentId={page.params.id}
		bind:sidebar
	/>
	{@render children()}
</Sidebar.Provider>
