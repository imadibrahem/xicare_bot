<script lang="ts">
	import type { LayoutProps } from './$types';

	import * as Sidebar from '$lib/components/ui/sidebar/index';
	import ChatSidebar from '$lib/components/chat-sidebar.svelte';

	let { children }: LayoutProps = $props();
</script>

<Sidebar.Provider>
	<ChatSidebar />
	<main class="w-full">
		<Sidebar.Trigger class="bg-background fixed top-0 m-6 md:m-2" />
		{@render children()}
	</main>
</Sidebar.Provider>
