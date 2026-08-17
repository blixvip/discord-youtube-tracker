const applicationId = process.env.DISCORD_APPLICATION_ID;
const token = process.env.DISCORD_TOKEN;

if (!applicationId || !token) {
  throw new Error("Set DISCORD_APPLICATION_ID and DISCORD_TOKEN before registering commands.");
}

const text = (name, description, required = true) => ({
  type: 3,
  name,
  description,
  required,
});

const commands = [
  {
    name: "addchannel",
    description: "Track a YouTube creator in this server",
    options: [text("channel", "Channel ID, @handle, channel URL, or video URL")],
  },
  {
    name: "removechannel",
    description: "Stop routing a YouTube creator to this channel",
    options: [text("channel", "Channel ID, @handle, channel URL, or video URL")],
  },
  { name: "channels", description: "List YouTube creators routed to this channel" },
  { name: "checkchannels", description: "Run an immediate upload check" },
  {
    name: "transcript",
    description: "Search a cached video transcript with timestamped results",
    options: [
      text("video", "YouTube video URL or ID"),
      text("query", "Optional words to find", false),
    ],
  },
  { name: "health", description: "Show private tracker diagnostics" },
];

const response = await fetch(
  `https://discord.com/api/v10/applications/${applicationId}/commands`,
  {
    method: "PUT",
    headers: {
      authorization: `Bot ${token}`,
      "content-type": "application/json",
    },
    body: JSON.stringify(commands),
  },
);

if (!response.ok) {
  throw new Error(`Discord command registration failed (${response.status}): ${(await response.text()).slice(0, 500)}`);
}

const registered = await response.json();
console.log(`Registered ${registered.length} Discord application commands.`);
