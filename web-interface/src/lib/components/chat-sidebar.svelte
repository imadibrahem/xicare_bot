<script lang="ts">
	import * as Sidebar from '$lib/components/ui/sidebar/index';
	import Plus from '@lucide/svelte/icons/plus';

	const dateOptions: Intl.DateTimeFormatOptions = {
		year: 'numeric',
		month: 'long',
		day: 'numeric'
	};

	// Menu items.
	const items = [
		{
			date: new Date(2025, 4, 4),
			id: ''
		},
		{
			date: new Date(2025, 4, 3),
			id: ''
		},
		{
			date: new Date(2025, 4, 2),
			id: ''
		},
		{
			date: new Date(2025, 4, 1),
			id: ''
		},
		{
			date: new Date(2025, 3, 30),
			id: ''
		},
		{
			date: new Date(2025, 3, 29),
			id: ''
		}
	];
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
					{#each items as item (item.date)}
						<Sidebar.MenuItem>
							<Sidebar.MenuButton>
								{#snippet child({ props })}
									<a href="/{item.id}" {...props}>
										{item.date.toLocaleDateString('en-US', dateOptions)}
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
		</Sidebar.Menu>
	</Sidebar.Footer>
</Sidebar.Root>
