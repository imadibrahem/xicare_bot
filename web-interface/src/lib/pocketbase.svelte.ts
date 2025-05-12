import PocketBase from 'pocketbase';

export const pb = new PocketBase('http://127.0.0.1:8090');

class User {
	token = $state(pb.authStore.token);
	record = $state(pb.authStore.record);
}
export const currentUser = new User();

pb.authStore.onChange(() => {
	currentUser.token = pb.authStore.token;
	currentUser.record = pb.authStore.record;
});
