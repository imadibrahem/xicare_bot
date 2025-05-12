<script lang="ts">
	import * as Sidebar from '$lib/components/ui/sidebar/index';
	import * as ContextMenu from '$lib/components/ui/context-menu/index';
	import Plus from '@lucide/svelte/icons/plus';

	import { goto, invalidateAll } from '$app/navigation';
	import type { Conversation } from '$lib/types';
	import { page } from '$app/state';

	const dateOptions: Intl.DateTimeFormatOptions = {
		year: 'numeric',
		month: 'long',
		day: 'numeric'
	};

	let {
		conversations,
		currentId,
		error,
		sidebar = $bindable(null)
	}: {
		conversations: Conversation[];
		currentId?: string;
		error?: unknown;
		sidebar?: any;
	} = $props();
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
			{#if error}
				<span class="text-sm text-red-800"
					><strong>Error loading conversations:</strong> {error}</span
				>
			{:else}
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
											onclick={async () => {
												// Delete conversation and navigate to a new conversation if the current one was deleted
												await fetch(`conversation/${conversation.id}/delete`, {
													method: 'DELETE'
												});
												await invalidateAll();
												if (page.params.id && page.params.id === conversation.id) {
													await goto('/');
												}
											}}
										>
											Delete
										</ContextMenu.Item>
									</ContextMenu.Content>
								</ContextMenu.Root>
							</Sidebar.MenuItem>
						{/each}
					</Sidebar.Menu>
				</Sidebar.GroupContent>
			{/if}
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
				<form action="/logout" method="POST">
					<Sidebar.MenuButton>Log out</Sidebar.MenuButton>
				</form>
			</Sidebar.MenuItem>
		</Sidebar.Menu>
	</Sidebar.Footer>
</Sidebar.Root>
