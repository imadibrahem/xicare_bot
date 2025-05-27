import PocketBase from 'pocketbase';
import { PUBLIC_PB_URL } from '$env/static/public';

export const pb = new PocketBase(PUBLIC_PB_URL.length ? PUBLIC_PB_URL : '/');

class User {
	store = $state(pb.authStore);
}
export const currentUser = new User();

pb.authStore.onChange(() => {
	currentUser.store = pb.authStore;
});
