<script lang="ts">
	import * as Sidebar from '$lib/components/ui/sidebar/index';
	import ChatSidebar from '$lib/components/chat-sidebar.svelte';
	import ChatHeader from '$lib/components/chat-header.svelte';

	import { goto, onNavigate } from '$app/navigation';
	import { onDestroy, onMount } from 'svelte';
	import { page } from '$app/state';
	import { pb } from '$lib/pocketbase.svelte';

	import type { SidebarState } from '$lib/components/ui/sidebar/index';
	import type { LayoutProps } from './$types';
	import type { Conversation } from '$lib/types';

	let { data, children }: LayoutProps = $props();

	let sidebar = $state<SidebarState | null>(null);

	let conversations = $state(data.conversations);

	// Add pocketbase subscriber for conversations
	let unsubscribe: () => void;
	onMount(async () => {
		unsubscribe = await pb
			.collection('conversations')
			.subscribe<Conversation>('*', async ({ action, record }) => {
				if (action === 'create') {
					conversations.push({
						id: record.id,
						user: record.user,
						created: record.created,
						updated: record.updated,
						awareness: record.awareness,
						politeness: record.politeness
					});
				} else if (action === 'delete') {
					conversations = conversations.filter((conversation) => conversation.id !== record.id);
				}
			});
	});
	// Unsubscribe on dismounting component
	onDestroy(() => {
		unsubscribe();
	});

	// Close the sidebar on mobile navigation
	onNavigate(() => {
		if (sidebar && sidebar.isMobile && sidebar.open) {
			sidebar.toggle();
		}
	});
</script>

<Sidebar.Provider>
	<ChatSidebar
		{conversations}
		currentId={page.params.id}
		bind:sidebar
		onlogout={async () => {
			await goto('/login');
		}}
	/>
	<main class="relative flex min-h-screen w-full flex-col">
		<ChatHeader
			conversation={conversations.find((conversation) => page.params.id === conversation.id)}
		/>
		<div class="flex-1">
			{@render children()}
		</div>
	</main>
</Sidebar.Provider>
