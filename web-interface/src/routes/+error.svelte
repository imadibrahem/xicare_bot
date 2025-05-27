<script lang="ts">
	import ArrowLeft from '@lucide/svelte/icons/arrow-left';

	import { page } from '$app/state';
	import { currentUser } from '$lib/pocketbase.svelte';
</script>

<div class="flex h-screen w-full items-center justify-center">
	<div class="flex items-center gap-4">
		<a class="pt-1" href={currentUser.store.record ? '/' : '/login'}><ArrowLeft /></a>
		<h1 class="text-2xl">
			{page.status}{#if page.error}{' – '}{page.error.message}{/if}
		</h1>
	</div>
</div>
