interface Env {
	BACKEND_URL: string;
	CF_ACCESS_CLIENT_ID: string;
	CF_ACCESS_CLIENT_SECRET: string;
	NTFY_TOPIC: string;
	CANARY_SECRET: string;
}

export const onRequestGet: PagesFunction<Env> = async (context) => {
	const { env, request } = context;
	const url = new URL(request.url);

	if (url.searchParams.get("key") !== env.CANARY_SECRET) {
		return new Response("unauthorized", { status: 401 });
	}

	try {
		const backendUrl = new URL("/api/health", env.BACKEND_URL);
		const resp = await fetch(backendUrl.toString(), {
			headers: {
				"CF-Access-Client-Id": env.CF_ACCESS_CLIENT_ID,
				"CF-Access-Client-Secret": env.CF_ACCESS_CLIENT_SECRET,
			},
		});

		if (!resp.ok) {
			await notify(env, "Canary: backend error", `Backend returned ${resp.status}`);
			return new Response("backend error", { status: 502 });
		}

		const data: { status: string; transcripts_20min: number } = await resp.json();
		if (data.status !== "ok") {
			await notify(env, "Canary: pipeline down", "0 transcripts in last 20 min. Pod may be preempted or tunnel down.");
			return new Response("down", { status: 503 });
		}

		return new Response(`ok: ${data.transcripts_20min} transcripts in last 20 min`, { status: 200 });
	} catch (e: unknown) {
		const msg = e instanceof Error ? e.message : String(e);
		await notify(env, "Canary: unreachable", `Failed to reach backend: ${msg}`);
		return new Response("unreachable", { status: 502 });
	}
};

async function notify(env: Env, title: string, message: string) {
	if (!env.NTFY_TOPIC) return;
	await fetch(`https://ntfy.sh/${env.NTFY_TOPIC}`, {
		method: "POST",
		headers: { Title: title, Priority: "urgent", Tags: "rotating_light" },
		body: message,
	});
}
