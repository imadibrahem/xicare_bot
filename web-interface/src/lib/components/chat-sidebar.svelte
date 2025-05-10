<script lang="ts">
	import * as Sidebar from '$lib/components/ui/sidebar/index';
	import Plus from '@lucide/svelte/icons/plus';

	import type { Conversation } from '$lib/types';

	const dateOptions: Intl.DateTimeFormatOptions = {
		year: 'numeric',
		month: 'long',
		day: 'numeric'
	};

	let { conversations, currentId }: { conversations: Conversation[]; currentId?: string } =
		$props();
</script>

<Sidebar.Root>
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
							<Sidebar.MenuButton isActive={currentId === conversation.id}>
								{#snippet child({ props })}
									<a href="/{conversation.id}" {...props}>
										{new Date(conversation.updated).toLocaleTimeString('en-US', dateOptions)}
									</a>
								{/snippet}
							</Sidebar.MenuButton>
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
				<form action="/logout" method="POST">
					<Sidebar.MenuButton>Log out</Sidebar.MenuButton>
				</form>
			</Sidebar.MenuItem>
		</Sidebar.Menu>
	</Sidebar.Footer>
</Sidebar.Root>
