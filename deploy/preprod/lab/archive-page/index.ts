// Local capability lab. This endpoint reads through the caller's RLS policies.
Deno.serve(async (request) => {
  if (request.method !== "GET") return new Response(null, { status: 405, headers: { Allow: "GET" } });
  const authorization = request.headers.get("authorization");
  if (!authorization) return new Response(null, { status: 401 });
  const after = new URL(request.url).searchParams.get("after") ?? "0";
  if (!/^\d+$/.test(after) || !Number.isSafeInteger(Number(after))) {
    return new Response(null, { status: 400 });
  }
  const response = await fetch(Deno.env.get("SUPABASE_URL") + "/rest/v1/rpc/lab_archive_page", {
    method: "POST",
    headers: {
      authorization,
      apikey: Deno.env.get("SUPABASE_ANON_KEY")!,
      "content-type": "application/json",
    },
    body: JSON.stringify({ after_id: Number(after) }),
  });
  return new Response(response.body, {
    status: response.status,
    headers: { "content-type": "application/json", "cache-control": "private, no-store" },
  });
});
