<script lang="ts">
	import * as Tooltip from '$lib/components/ui/tooltip';
	import Copy from '@lucide/svelte/icons/clipboard-copy';
	import * as Sidebar from '$lib/components/ui/sidebar/index';

	import { page } from '$app/state';
	import { pb } from '$lib/pocketbase.svelte';
	import { copyMessagesToClipboard } from '$lib/utils';

	import type { Conversation, Message } from '$lib/types';

	let { conversation }: { conversation?: Conversation } = $props();

	const copy = async () => {
		copyMessagesToClipboard(
			(await pb.collection('messages').getFullList({
				filter: pb.filter('conversation = {:id}', { id: page.params.id }),
				sort: 'created'
			})) as Message[]
		);
	};
</script>

<div
	class="from-background sticky top-0 z-10 flex w-full shrink-0 items-start justify-between bg-gradient-to-b from-60% to-transparent md:pointer-events-none"
>
	<Sidebar.Trigger class="bg-background pointer-events-auto m-2 md:m-2" />
	<!-- Show settings in top bar -->
	{#if conversation}
		<em class="p-4 text-center text-sm md:text-base"
			>Norbert Wiener is {!conversation.awareness ? 'not ' : ''}aware of his death and current
			developments and {!conversation.politeness ? 'does not insist ' : 'insists '}upon respect and
			politeness.</em
		>
		<Tooltip.Provider>
			<Tooltip.Root>
				<Tooltip.Trigger
					class="bg-background ring-offset-background focus-visible:ring-ring hover:bg-accent hover:text-accent-foreground pointer-events-auto m-2 inline-flex h-7 w-7 items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 md:m-2 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0"
					onclick={copy}
				>
					<Copy />
				</Tooltip.Trigger>
				<Tooltip.Content>
					<p>Copy conversation to clipboard</p>
				</Tooltip.Content>
			</Tooltip.Root>
		</Tooltip.Provider>
	{/if}
</div>
