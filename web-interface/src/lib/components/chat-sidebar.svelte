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
			id: '2ba163be-819a-4440-8645-05e3a481a6eb'
		},
		{
			date: new Date(2025, 4, 3),
			id: '3336643c-7f8b-4dfa-9849-43e2cd5dbcc4'
		},
		{
			date: new Date(2025, 4, 2),
			id: '15a3be9d-0353-4840-8232-f0324c149545'
		},
		{
			date: new Date(2025, 4, 1),
			id: '36755256-d552-44f3-832d-58a10cd81641'
		},
		{
			date: new Date(2025, 3, 30),
			id: '87328c9a-73a5-4794-a709-475cb81cbbb0'
		},
		{
			date: new Date(2025, 3, 29),
			id: '10da238b-b829-46fd-9d9e-d84f43726ccb'
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
