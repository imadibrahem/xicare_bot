import PocketBase from 'pocketbase';
import { PUBLIC_PB_URL } from '$env/static/public';

export const pb = new PocketBase(PUBLIC_PB_URL.length ? PUBLIC_PB_URL : '/');

class User {
	token = $state(pb.authStore.token);
	record = $state(pb.authStore.record);
}
export const currentUser = new User();

pb.authStore.onChange(() => {
	currentUser.token = pb.authStore.token;
	currentUser.record = pb.authStore.record;
});
