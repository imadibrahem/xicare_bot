<script lang="ts">
	import '../app.css';

	import { Toaster } from '$lib/components/ui/sonner/index';

	let { children } = $props();
</script>

<Toaster />

{@render children()}
