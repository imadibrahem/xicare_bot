<script lang="ts">
	import Message from '$lib/components/message.svelte';
	import Button from '$lib/components/ui/button/button.svelte';
	import * as Tooltip from '$lib/components/ui/tooltip';

	import type { Message as MessageType } from '$lib/types';

	import ArrowUp from '@lucide/svelte/icons/arrow-up';
	import Copy from '@lucide/svelte/icons/clipboard-copy';

	const messages: MessageType[] = [
		{
			text: 'Integer scelerisque, arcu ac maximus lobortis, odio diam viverra velit, vel semper tellus nunc quis augue.',
			time: new Date(2025, 4, 4, 15, 1, 15),
			role: 'user'
		},
		{
			text: 'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed in dolor quis dui consequat ornare. Morbi consequat justo sit amet odio cursus, sit amet consequat ex varius. Nullam consectetur eget ex nec placerat. Donec vitae quam quam. Duis ullamcorper gravida suscipit. Ut nec augue massa. Curabitur porta suscipit eros, sed semper quam malesuada ut. Duis id leo eu libero luctus eleifend. Nunc lacus lectus, egestas a sollicitudin ut, congue sit amet eros. Donec sed malesuada arcu, a cursus arcu. In a fringilla eros. Sed tempus lectus nec luctus luctus.',
			time: new Date(2025, 4, 4, 15, 2, 20),
			role: 'norbert'
		},
		{
			text: 'Nam feugiat neque nec euismod placerat. Suspendisse ipsum augue, gravida sit amet nunc at, mattis bibendum massa.',
			time: new Date(2025, 4, 4, 15, 3, 48),
			role: 'user'
		},
		{
			text: 'Donec et porttitor dui. Integer lacinia, dolor ac porta accumsan, nunc nibh auctor nulla, sit amet fermentum nisi nisi a lorem. Ut ac tortor erat. Praesent vel consequat arcu. Proin sodales malesuada turpis vitae accumsan. Aenean ut purus augue. Nullam vitae dui eros. Sed rhoncus enim ac enim tincidunt porttitor. Orci varius natoque penatibus et magnis dis parturient montes, nascetur ridiculus mus. Ut ultrices libero massa, semper efficitur nibh blandit ut. Nam elit felis, feugiat eget aliquam et, mattis a sapien. ',
			time: new Date(2025, 4, 4, 15, 4, 5),
			role: 'norbert'
		},
		{
			text: 'Vestibulum semper eros eu lorem malesuada dapibus.',
			time: new Date(2025, 4, 4, 15, 4, 50),
			role: 'user'
		},
		{
			text: 'Nunc placerat varius mattis. Curabitur sed metus a felis sollicitudin semper id quis nisi. Suspendisse lectus felis, tristique nec venenatis nec, sodales quis magna. Fusce non massa felis. Sed id bibendum eros. Donec mollis est ultrices elementum scelerisque. Sed id justo commodo, blandit diam vel, malesuada urna. ',
			time: new Date(2025, 4, 4, 15, 5, 23),
			role: 'norbert'
		},
		{
			text: 'Sed dictum lobortis nunc, in vestibulum turpis sagittis nec. Sed et elementum ipsum. Etiam semper purus sit amet urna bibendum, ac vestibulum ante tincidunt.',
			time: new Date(2025, 4, 4, 15, 6, 0),
			role: 'user'
		},
		{
			text: ' Vivamus nec mauris enim. Sed ex arcu, scelerisque vel aliquet a, feugiat nec metus. Vivamus commodo ex a rhoncus euismod. Mauris pharetra mauris ut tellus euismod vestibulum. Aenean interdum, nisi ac consectetur molestie, magna nibh consequat libero, at mattis lectus diam luctus sapien. Duis scelerisque sodales ligula, in efficitur est fermentum vitae. Duis rhoncus enim leo, sit amet faucibus ex rutrum in. Quisque at cursus nunc, at fermentum nisl. ',
			time: new Date(2025, 4, 4, 15, 6, 47),
			role: 'norbert'
		}
	];

	let textarea: HTMLTextAreaElement;

	const adjustHeight = () => {
		if (textarea) {
			textarea.style.height = 'auto';
			textarea.style.height = `${textarea.scrollHeight}px`;
		}
	};
</script>

<div class="container flex h-screen flex-col px-0">
	<div class="flex-1 overflow-y-auto">
		<div class="mx-4 flex flex-col gap-y-8 py-4 md:mx-10">
			{#each messages as message (message.time)}
				<Message {...message}></Message>
			{/each}
		</div>
	</div>
	<div
		class="bg-secondary border-foreground mx-4 mb-10 flex shrink-0 resize-none gap-x-4 border-[1px] p-4 md:mx-10"
	>
		<textarea
			name="query"
			class="bg-secondary focus:border-foreground w-full resize-none self-center overflow-hidden outline-none focus:ring-0 md:text-lg"
			placeholder="Type your message here..."
			bind:this={textarea}
			oninput={adjustHeight}
			rows="1"
		></textarea>
		<Button size="icon" class="self-end rounded-full">
			<ArrowUp />
		</Button>
	</div>
</div>
<Tooltip.Provider>
	<Tooltip.Root>
		<Tooltip.Trigger class="fixed right-0 top-0 m-6 md:m-2">
			<Button size="icon" variant="ghost" class="bg-background h-7 w-7">
				<Copy />
			</Button>
		</Tooltip.Trigger>
		<Tooltip.Content>
			<p>Copy conversation to clipboard</p>
		</Tooltip.Content>
	</Tooltip.Root>
</Tooltip.Provider>
