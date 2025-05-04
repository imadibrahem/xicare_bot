<script lang="ts">
	import type { LayoutProps } from './$types';

	import * as Sidebar from '$lib/components/ui/sidebar/index';
	import ChatSidebar from '$lib/components/chat-sidebar.svelte';

	let { children }: LayoutProps = $props();
</script>

<Sidebar.Provider>
	<ChatSidebar />
	<main>
		<Sidebar.Trigger class="m-2" />
		{@render children()}
	</main>
</Sidebar.Provider>
