import { verifyKey } from "discord-interactions";

interface Env {
  DB: D1Database;
  DISCORD_TOKEN: string;
  DISCORD_PUBLIC_KEY: string;
  DISCORD_APPLICATION_ID: string;
}

interface ExecutionContextLike {
  waitUntil(promise: Promise<unknown>): void;
}

interface Route {
  youtube_channel_id: string;
  youtube_channel_name: string;
  discord_channel_id: string;
  last_video_id: string | null;
}

interface Video {
  videoId: string;
  title: string;
  url: string;
  published: string;
  thumbnailUrl: string;
  channelName: string;
}

interface DiscordInteraction {
  id: string;
  application_id: string;
  token: string;
  type: number;
  guild_id?: string;
  channel_id?: string;
  member?: { permissions?: string };
  data?: {
    name?: string;
    options?: Array<{ name: string; value: string }>;
  };
}

const DISCORD_API = "https://discord.com/api/v10";
const MANAGE_GUILD = 32n;
const POLL_BATCH_SIZE = 20;
const SEND_BATCH_SIZE = 20;

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function decodeXml(value: string): string {
  return value
    .replaceAll("&amp;", "&")
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">")
    .replaceAll("&quot;", '"')
    .replaceAll("&#39;", "'");
}

function tagValue(xml: string, tag: string): string {
  const match = xml.match(new RegExp(`<${tag}[^>]*>(?:<!\\[CDATA\\[)?([\\s\\S]*?)(?:\\]\\]>)?</${tag}>`));
  return decodeXml((match?.[1] ?? "").trim());
}

export function parseAtomFeed(xml: string): Video[] {
  const channelName = tagValue(xml, "title");
  return [...xml.matchAll(/<entry>([\s\S]*?)<\/entry>/g)].map((match) => {
    const entry = match[1];
    const videoId = tagValue(entry, "yt:videoId");
    return {
      videoId,
      title: tagValue(entry, "title"),
      url: `https://www.youtube.com/watch?v=${videoId}`,
      published: tagValue(entry, "published"),
      thumbnailUrl: `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`,
      channelName,
    };
  }).filter((video) => video.videoId.length > 0);
}

export function extractChannelId(input: string, pageHtml = ""): string | null {
  const direct = input.match(/(?:channel\/)?(UC[A-Za-z0-9_-]{22})/);
  if (direct) return direct[1];
  const pageMatch = pageHtml.match(/"channelId"\s*:\s*"(UC[A-Za-z0-9_-]{22})"/);
  return pageMatch?.[1] ?? null;
}

export function slugify(value: string): string {
  const slug = value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return (slug || "youtube-creator").slice(0, 90);
}

async function verifyDiscordRequest(request: Request, publicKey: string, body: ArrayBuffer): Promise<boolean> {
  const signature = request.headers.get("x-signature-ed25519");
  const timestamp = request.headers.get("x-signature-timestamp");
  if (!signature || !timestamp) return false;
  return verifyKey(new Uint8Array(body), signature, timestamp, publicKey);
}

async function discordApi(env: Env, path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("authorization", `Bot ${env.DISCORD_TOKEN}`);
  headers.set("content-type", "application/json");
  const response = await fetch(`${DISCORD_API}${path}`, { ...init, headers });
  if (!response.ok) {
    const detail = (await response.text()).slice(0, 300);
    throw new Error(`Discord API ${response.status}: ${detail}`);
  }
  return response;
}

async function editInteraction(env: Env, interaction: DiscordInteraction, content: string): Promise<void> {
  await fetch(`${DISCORD_API}/webhooks/${interaction.application_id}/${interaction.token}/messages/@original`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ content, allowed_mentions: { parse: [] } }),
  });
}

async function fetchFeed(channelId: string): Promise<Video[]> {
  const response = await fetch(`https://www.youtube.com/feeds/videos.xml?channel_id=${encodeURIComponent(channelId)}`);
  if (!response.ok) throw new Error(`YouTube feed returned ${response.status}`);
  return parseAtomFeed(await response.text());
}

async function resolveYouTubeChannel(input: string): Promise<{ channelId: string; channelName: string; videos: Video[] }> {
  let channelId = extractChannelId(input);
  if (!channelId) {
    const response = await fetch(input, { redirect: "follow" });
    if (!response.ok) throw new Error(`YouTube page returned ${response.status}`);
    channelId = extractChannelId(input, await response.text());
  }
  if (!channelId) throw new Error("Could not find a YouTube channel ID");
  const videos = await fetchFeed(channelId);
  return { channelId, channelName: videos[0]?.channelName || channelId, videos };
}

async function ensureDestinations(env: Env, guildId: string, creatorName: string): Promise<string[]> {
  let channels = await (await discordApi(env, `/guilds/${guildId}/channels`)).json() as Array<Record<string, unknown>>;
  let category = channels.find((channel) => channel.type === 4 && String(channel.name).toLowerCase() === "ai video feeds");
  if (!category) {
    category = await (await discordApi(env, `/guilds/${guildId}/channels`, {
      method: "POST",
      body: JSON.stringify({ name: "AI Video Feeds", type: 4 }),
    })).json() as Record<string, unknown>;
    channels = [...channels, category];
  }
  const categoryId = String(category.id);
  async function ensureTextChannel(name: string, topic: string): Promise<string> {
    const existing = channels.find((channel) => channel.type === 0 && String(channel.parent_id) === categoryId && String(channel.name).toLowerCase() === name.toLowerCase());
    if (existing) return String(existing.id);
    const created = await (await discordApi(env, `/guilds/${guildId}/channels`, {
      method: "POST",
      body: JSON.stringify({ name, topic, type: 0, parent_id: categoryId }),
    })).json() as Record<string, unknown>;
    channels.push(created);
    return String(created.id);
  }
  return [
    await ensureTextChannel("everything", "Every new upload from all watched creators."),
    await ensureTextChannel(slugify(creatorName), `New videos from ${creatorName}.`),
  ];
}

async function addChannel(env: Env, interaction: DiscordInteraction, input: string): Promise<string> {
  if (!interaction.guild_id) throw new Error("Use this command inside a Discord server.");
  const resolved = await resolveYouTubeChannel(input);
  const destinations = await ensureDestinations(env, interaction.guild_id, resolved.channelName);
  const latest = resolved.videos[0]?.videoId ?? null;
  await env.DB.batch(destinations.map((channelId) => env.DB.prepare(
    `INSERT OR IGNORE INTO routes
     (youtube_channel_id, youtube_channel_name, discord_channel_id, last_video_id)
     VALUES (?, ?, ?, ?)`,
  ).bind(resolved.channelId, resolved.channelName, channelId, latest)));
  return `YouTube feed ready: **${resolved.channelName}** → ${destinations.map((id) => `<#${id}>`).join(" + ")}`;
}

async function removeChannel(env: Env, interaction: DiscordInteraction, input: string): Promise<string> {
  if (!interaction.channel_id) throw new Error("Missing Discord channel.");
  const resolved = await resolveYouTubeChannel(input);
  const result = await env.DB.prepare(
    "DELETE FROM routes WHERE youtube_channel_id = ? AND discord_channel_id = ?",
  ).bind(resolved.channelId, interaction.channel_id).run();
  return result.meta.changes ? `Stopped watching **${resolved.channelName}** here.` : "That YouTube channel is not watched here.";
}

async function listChannels(env: Env, interaction: DiscordInteraction): Promise<string> {
  if (!interaction.channel_id) throw new Error("Missing Discord channel.");
  const rows = await env.DB.prepare(
    "SELECT youtube_channel_id, youtube_channel_name FROM routes WHERE discord_channel_id = ? ORDER BY youtube_channel_name",
  ).bind(interaction.channel_id).all<Route>();
  if (!rows.results.length) return "No YouTube channels are watched here yet.";
  return "Watched YouTube channels:\n" + rows.results.map((route) =>
    `• **${route.youtube_channel_name}** — https://youtube.com/channel/${route.youtube_channel_id}`,
  ).join("\n");
}

async function handleInteraction(env: Env, interaction: DiscordInteraction): Promise<void> {
  try {
    const command = interaction.data?.name;
    const input = interaction.data?.options?.find((option) => option.name === "channel")?.value ?? "";
    const canManage = (BigInt(interaction.member?.permissions ?? "0") & MANAGE_GUILD) !== 0n;
    let message: string;
    if (command === "addchannel" || command === "removechannel" || command === "checkchannels") {
      if (!canManage) throw new Error("You need Manage Server permission for this command.");
    }
    if (command === "addchannel") message = await addChannel(env, interaction, input);
    else if (command === "removechannel") message = await removeChannel(env, interaction, input);
    else if (command === "channels") message = await listChannels(env, interaction);
    else if (command === "checkchannels") {
      const posted = await runPoll(env);
      message = `Check complete. Posted ${posted} new video(s).`;
    } else message = "Unknown tracker command.";
    await editInteraction(env, interaction, message.slice(0, 1900));
  } catch (error) {
    await editInteraction(env, interaction, `Tracker error: ${error instanceof Error ? error.message : String(error)}`.slice(0, 1900));
  }
}

function newVideos(videos: Video[], lastVideoId: string | null): Video[] {
  if (!lastVideoId) return [];
  const pending: Video[] = [];
  for (const video of videos) {
    if (video.videoId === lastVideoId) break;
    pending.push(video);
  }
  return pending.reverse();
}

async function queueVideos(env: Env, routes: Route[], videosByChannel: Map<string, Video[]>): Promise<void> {
  const inserts: Array<{ route: Route; video: Video }> = [];
  const updates: Array<{ channelId: string; latest: string }> = [];
  for (const [channelId, videos] of videosByChannel) {
    if (!videos.length) continue;
    const channelRoutes = routes.filter((route) => route.youtube_channel_id === channelId);
    for (const route of channelRoutes) {
      for (const video of newVideos(videos, route.last_video_id)) inserts.push({ route, video });
    }
    updates.push({ channelId, latest: videos[0].videoId });
  }
  const statements: D1PreparedStatement[] = [];
  for (let index = 0; index < inserts.length; index += 10) {
    const chunk = inserts.slice(index, index + 10);
    const values = chunk.map(() => "(?, ?, ?, ?, ?, ?, ?, ?)").join(",");
    const parameters = chunk.flatMap(({ route, video }) => [
      route.discord_channel_id,
      route.youtube_channel_id,
      route.youtube_channel_name,
      video.videoId,
      video.title,
      video.url,
      video.published,
      video.thumbnailUrl,
    ]);
    statements.push(env.DB.prepare(
      `INSERT OR IGNORE INTO pending_posts
       (discord_channel_id, youtube_channel_id, youtube_channel_name, video_id, title, url, published, thumbnail_url)
       VALUES ${values}`,
    ).bind(...parameters));
  }
  if (updates.length) {
    const cases = updates.map(() => "WHEN ? THEN ?").join(" ");
    const ids = updates.map(() => "?").join(",");
    statements.push(env.DB.prepare(
      `UPDATE routes
       SET last_video_id = CASE youtube_channel_id ${cases} ELSE last_video_id END
       WHERE youtube_channel_id IN (${ids})`,
    ).bind(
      ...updates.flatMap(({ channelId, latest }) => [channelId, latest]),
      ...updates.map(({ channelId }) => channelId),
    ));
  }
  if (statements.length) await env.DB.batch(statements);
}

async function sendPending(env: Env): Promise<number> {
  const pending = await env.DB.prepare(
    "SELECT * FROM pending_posts ORDER BY id LIMIT ?",
  ).bind(SEND_BATCH_SIZE).all<Record<string, string | number>>();
  let sent = 0;
  for (const post of pending.results) {
    try {
      await discordApi(env, `/channels/${post.discord_channel_id}/messages`, {
        method: "POST",
        body: JSON.stringify({
          embeds: [{
            title: String(post.title).slice(0, 256),
            url: post.url,
            description: "New YouTube upload",
            color: 0xff0000,
            timestamp: post.published || undefined,
            author: { name: post.youtube_channel_name, url: `https://youtube.com/channel/${post.youtube_channel_id}` },
            image: { url: post.thumbnail_url },
            footer: { text: "YouTube • New video" },
          }],
          components: [{ type: 1, components: [{ type: 2, style: 5, label: "Watch on YouTube", url: post.url }] }],
          allowed_mentions: { parse: [] },
        }),
      });
      await env.DB.prepare("DELETE FROM pending_posts WHERE id = ?").bind(post.id).run();
      sent += 1;
    } catch (error) {
      console.error("Could not post queued video", error);
    }
  }
  return sent;
}

export async function runPoll(env: Env): Promise<number> {
  const channels = await env.DB.prepare(
    "SELECT DISTINCT youtube_channel_id FROM routes ORDER BY youtube_channel_id",
  ).all<{ youtube_channel_id: string }>();
  if (!channels.results.length) return 0;
  const state = await env.DB.prepare("SELECT cursor FROM poll_state WHERE id = 1").first<{ cursor: number }>();
  const start = (state?.cursor ?? 0) % channels.results.length;
  const batch = Array.from({ length: Math.min(POLL_BATCH_SIZE, channels.results.length) }, (_, offset) =>
    channels.results[(start + offset) % channels.results.length].youtube_channel_id,
  );
  const placeholders = batch.map(() => "?").join(",");
  const routes = await env.DB.prepare(
    `SELECT * FROM routes WHERE youtube_channel_id IN (${placeholders})`,
  ).bind(...batch).all<Route>();
  const videosByChannel = new Map<string, Video[]>();
  for (let index = 0; index < batch.length; index += 5) {
    await Promise.all(batch.slice(index, index + 5).map(async (channelId) => {
      try {
        videosByChannel.set(channelId, (await fetchFeed(channelId)).slice(0, 5));
      } catch (error) {
        console.error("YouTube feed error", error);
      }
    }));
  }
  await queueVideos(env, routes.results, videosByChannel);
  await env.DB.prepare("UPDATE poll_state SET cursor = ? WHERE id = 1")
    .bind((start + batch.length) % channels.results.length).run();
  return sendPending(env);
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContextLike): Promise<Response> {
    if (request.method === "GET") {
      return new Response("Discord YouTuber Tracker is running.");
    }
    if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });
    const body = await request.arrayBuffer();
    if (!(await verifyDiscordRequest(request, env.DISCORD_PUBLIC_KEY, body))) return new Response("Invalid signature", { status: 401 });
    const interaction = JSON.parse(new TextDecoder().decode(body)) as DiscordInteraction;
    if (interaction.type === 1) return json({ type: 1 });
    if (interaction.type !== 2) return json({ type: 4, data: { content: "Unsupported interaction." } });
    ctx.waitUntil(handleInteraction(env, interaction));
    return json({ type: 5, data: { flags: 64 } });
  },

  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContextLike): Promise<void> {
    ctx.waitUntil(runPoll(env).then((posted) => console.log(`Poll complete: ${posted} new video(s)`)));
  },
};
