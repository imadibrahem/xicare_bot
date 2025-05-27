<script lang="ts">
	import '../app.css';

	import { ModeWatcher } from 'mode-watcher';
	import { Toaster } from '$lib/components/ui/sonner/index';

	let { children } = $props();
</script>

<Toaster duration={8000} />
<ModeWatcher defaultMode="light" />
{@render children()}
