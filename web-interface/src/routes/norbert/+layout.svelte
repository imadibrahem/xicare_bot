<script lang="ts">
	import type { LayoutProps } from './$types';

	import * as Sidebar from '$lib/components/ui/sidebar/index';
	import ChatSidebar from '$lib/components/chat-sidebar.svelte';

	let { children }: LayoutProps = $props();
</script>

<Sidebar.Provider>
	<ChatSidebar />
	<main>
		<Sidebar.Trigger />
		{@render children()}
	</main>
</Sidebar.Provider>
