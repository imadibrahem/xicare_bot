<script lang="ts">
	import * as Sidebar from '$lib/components/ui/sidebar/index';
	import * as ContextMenu from '$lib/components/ui/context-menu/index';
	import Plus from '@lucide/svelte/icons/plus';

	import { page } from '$app/state';
	import { goto, invalidateAll } from '$app/navigation';
	import { pb } from '$lib/pocketbase.svelte';
	import type { Conversation } from '$lib/types';

	const dateOptions: Intl.DateTimeFormatOptions = {
		year: 'numeric',
		month: 'long',
		day: 'numeric'
	};

	let {
		conversations,
		currentId,
		sidebar = $bindable(null),
		onlogout
	}: {
		conversations: Conversation[];
		currentId?: string;
		sidebar?: any;
		onlogout?: () => void;
	} = $props();

	const logout = () => {
		pb.authStore.clear();

		if (onlogout) onlogout();
	};

	const deleteConversation = async (id: string) => {
		// Delete conversation and navigate to a new conversation if the current one was deleted
		await pb.collection('conversations').delete(id);
		await invalidateAll();
		if (page.params.id && page.params.id === id) {
			await goto('/');
		}
	};
</script>

<Sidebar.Root bind:sidebarObj={sidebar}>
	<Sidebar.Header>
		<Sidebar.Menu>
			<Sidebar.MenuItem class="mt-4 md:mt-8">
				<Sidebar.MenuButton>
					{#snippet child({ props })}
						<a href="/" {...props}>
							<Plus />
							<span>New conversation</span>
						</a>
					{/snippet}
				</Sidebar.MenuButton>
			</Sidebar.MenuItem>
		</Sidebar.Menu>
	</Sidebar.Header>
	<Sidebar.Content>
		<Sidebar.Group>
			<Sidebar.GroupLabel>Conversations</Sidebar.GroupLabel>
			<Sidebar.GroupContent>
				<Sidebar.Menu>
					{#each conversations as conversation (conversation.id)}
						<Sidebar.MenuItem>
							<ContextMenu.Root>
								<ContextMenu.Trigger>
									<Sidebar.MenuButton isActive={currentId === conversation.id}>
										{#snippet child({ props })}
											<a href="/{conversation.id}" {...props}>
												{new Date(conversation.updated).toLocaleTimeString('en-US', dateOptions)}
											</a>
										{/snippet}
									</Sidebar.MenuButton>
								</ContextMenu.Trigger>
								<ContextMenu.Content>
									<ContextMenu.Item
										onclick={() => {
											deleteConversation(conversation.id);
										}}>Delete</ContextMenu.Item
									>
								</ContextMenu.Content>
							</ContextMenu.Root>
						</Sidebar.MenuItem>
					{/each}
				</Sidebar.Menu>
			</Sidebar.GroupContent>
		</Sidebar.Group>
	</Sidebar.Content>
	<Sidebar.Footer>
		<Sidebar.Menu>
			<Sidebar.MenuItem>
				<Sidebar.MenuButton>
					{#snippet child({ props })}
						<a href="/about" {...props}>About</a>
					{/snippet}
				</Sidebar.MenuButton>
			</Sidebar.MenuItem>
			<Sidebar.MenuItem>
				<Sidebar.MenuButton onclick={logout}>Log out</Sidebar.MenuButton>
			</Sidebar.MenuItem>
		</Sidebar.Menu>
	</Sidebar.Footer>
</Sidebar.Root>
