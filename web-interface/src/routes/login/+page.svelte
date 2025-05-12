<script lang="ts">
	import Login from '$lib/components/login.svelte';

	import { goto } from '$app/navigation';
</script>

<main class="flex h-screen w-screen items-center justify-center">
	<Login
		onlogin={() => {
			goto('/');
		}}
	/>
</main>
