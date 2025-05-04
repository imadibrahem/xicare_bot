<script lang="ts">
	let { children } = $props();
</script>

<main class="prose prose-xl prose-invert prose-neutral container">
	{@render children()}
</main>
