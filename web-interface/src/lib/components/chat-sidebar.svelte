<script lang="ts">
	import * as Sidebar from '$lib/components/ui/sidebar/index';

	const dateOptions: Intl.DateTimeFormatOptions = {
		year: 'numeric',
		month: 'long',
		day: 'numeric'
	};

	// Menu items.
	const items = [
		{
			date: new Date(2025, 5, 4),
			url: '#'
		},
		{
			date: new Date(2025, 5, 3),
			url: '#'
		},
		{
			date: new Date(2025, 5, 2),
			url: '#'
		},
		{
			date: new Date(2025, 5, 1),
			url: '#'
		},
		{
			date: new Date(2025, 4, 30),
			url: '#'
		},
		{
			date: new Date(2025, 4, 29),
			url: '#'
		}
	];
</script>

<Sidebar.Root>
	<Sidebar.Header />
	<Sidebar.Content>
		<Sidebar.Group>
			<Sidebar.GroupLabel>Conversations</Sidebar.GroupLabel>
			<Sidebar.GroupContent>
				<Sidebar.Menu>
					{#each items as item (item.date)}
						<Sidebar.MenuItem>
							<Sidebar.MenuButton>
								{#snippet child({ props })}
									<a href={item.url} {...props}>
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
