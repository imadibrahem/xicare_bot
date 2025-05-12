import PocketBase from 'pocketbase';

export const pb = new PocketBase('http://127.0.0.1:8090');

class User {
	record = $state(pb.authStore.record);
}
export const currentUser = new User();

pb.authStore.onChange(() => {
	currentUser.record = pb.authStore.record;
});
