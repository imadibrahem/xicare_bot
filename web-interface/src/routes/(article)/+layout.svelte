<script lang="ts">
	let { children } = $props();
</script>

<main class="mx-auto my-9 max-w-screen-lg px-4 md:px-10">
	{@render children()}
</main>
