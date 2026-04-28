interface Env {
	CLICKHOUSE_URL: string;
	CLICKHOUSE_USER: string;
	CLICKHOUSE_PASSWORD: string;
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

	const chUrl = new URL(env.CLICKHOUSE_URL);
	chUrl.searchParams.set("default_format", "JSONEachRow");

	try {
		const resp = await fetch(chUrl.toString(), {
			method: "POST",
			headers: {
				"Content-Type": "text/plain",
				"X-ClickHouse-User": env.CLICKHOUSE_USER,
				"X-ClickHouse-Key": env.CLICKHOUSE_PASSWORD,
				"CF-Access-Client-Id": env.CF_ACCESS_CLIENT_ID,
				"CF-Access-Client-Secret": env.CF_ACCESS_CLIENT_SECRET,
			},
			body: "SELECT count() as c FROM blotter.scanner_transcripts WHERE created_at > now() - INTERVAL 20 MINUTE",
		});

		if (!resp.ok) {
			await notify(env, "Canary: ClickHouse error", `ClickHouse returned ${resp.status}`);
			return new Response("clickhouse error", { status: 502 });
		}

		const text = await resp.text();
		const row = JSON.parse(text.trim().split("\n")[0]);
		const count = Number(row.c);

		if (count === 0) {
			await notify(env, "Canary: pipeline down", "0 transcripts in last 20 min. Pod may be preempted or tunnel down.");
			return new Response("down", { status: 503 });
		}

		return new Response(`ok: ${count} transcripts in last 20 min`, { status: 200 });
	} catch (e: unknown) {
		const msg = e instanceof Error ? e.message : String(e);
		await notify(env, "Canary: unreachable", `Failed to reach ClickHouse: ${msg}`);
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
