# Discord video notification message design

Research date: 2026-07-31. Sources limited to Discord, discord.py, YouTube, and the official discord.py GitHub repository.

## Recommendation

Use one compact rich embed plus one link button:

- YouTube-red accent (`0xFF0000`).
- Video title as the embed title; make it the video link.
- Creator as the author; make it the channel link and include its avatar when available.
- Large video thumbnail via `set_image`, not a tiny side thumbnail.
- Upload time as the embed timestamp; optionally show a relative Discord timestamp in one inline field.
- Short footer: `YouTube • New upload`.
- One `▶ Watch on YouTube` link button.
- No bare video URL in message content; it can create a second preview and adds visual noise.
- `discord.AllowedMentions.none()` on every automated notification.

This produces one obvious hierarchy: creator → title → thumbnail → watch action. Creator and upload time should not be repeated in several fields unless the duplicate adds meaning.

## Evidence

Discord rich embeds natively support title, URL, description, timestamp, color, footer, image, thumbnail, author, and fields. Image URLs must be HTTP(S) or attachments. Embed limits include 256 characters for title, 4,096 for description, 25 fields, and 6,000 characters combined across all embeds in a message. Therefore, truncate untrusted titles and keep notification copy short. [Discord Message Resource](https://docs.discord.com/developers/resources/message#embed-object)

Discord link-style buttons require a URL, cannot have a `custom_id`, and do not send an interaction back to the bot. They are ideal for a stateless `Watch on YouTube` action. [Discord Component Reference](https://docs.discord.com/developers/components/reference#button)

discord.py's official GitHub example constructs a link button manually with `discord.ui.Button(label=..., url=...)`, adds it to a `discord.ui.View`, and sends the view with the message. [discord.py `examples/views/link.py`](https://github.com/Rapptz/discord.py/blob/master/examples/views/link.py)

Discord processes mentions by default in ordinary messages. Suppressing all mentions avoids a malicious or unusual creator/title string causing an accidental ping. Discord explicitly recommends `allowed_mentions` when sending user-generated strings. [Discord Allowed Mentions](https://docs.discord.com/developers/resources/message#allowed-mentions-object)

YouTube exposes thumbnail variants as URLs (`default`, `medium`, `high`, and sometimes `standard`/`maxres`). Prefer a URL returned by the feed/API; choose the best available variant rather than assuming the highest resolution exists. [YouTube thumbnail resource](https://developers.google.com/youtube/v3/docs/thumbnails)

Do not try to build a custom playable-video embed: Discord does not let message authors set the embed's `video` property. A linked thumbnail plus URL button is the reliable custom-card design. [Discord Create Message limitations](https://docs.discord.com/developers/resources/message#create-message)

Keep this repo's normal embed plus `discord.ui.View`. Components V2 offer new layouts, but a V2 message cannot also contain traditional content or embeds, and the repo pins discord.py 2.5.2. An upgrade/migration adds risk without improving this simple notification card. [Discord component overview](https://docs.discord.com/developers/components/overview)

## discord.py 2.5.2 pattern

```python
embed = discord.Embed(
    title=video["title"][:256],
    url=video["url"],
    description="New YouTube upload",
    colour=discord.Colour.from_rgb(255, 0, 0),
    timestamp=published_at,
)
embed.set_author(name=creator_name, url=creator_url, icon_url=creator_avatar_url)
embed.set_image(url=thumbnail_url)
embed.set_footer(text="YouTube • New upload")

view = discord.ui.View(timeout=None)
view.add_item(discord.ui.Button(
    label="Watch on YouTube",
    emoji="▶️",
    style=discord.ButtonStyle.link,
    url=video["url"],
))

await target.send(
    embed=embed,
    view=view,
    allowed_mentions=discord.AllowedMentions.none(),
)
```

No persistent-view registration is needed for this URL-only button because it has no callback.

## Fit to this repo

The current `create_video_embed`, `create_video_view`, and notification send path already implement nearly all of the above: linked title, creator link, red accent, large thumbnail, timestamp, footer, link button, and disabled mentions. Suggested polish:

1. Remove the redundant `Creator` field; the author line already supplies it.
2. Keep `Published` only if the relative time is useful; otherwise the embed timestamp is enough.
3. Use a thumbnail URL returned by the source when available, choosing `maxres → standard → high → medium → default`; retain a safe fallback.
4. Add the creator's channel avatar to the author row if the source exposes one.
5. Verify source files are UTF-8 so `•` and `▶️` do not render as mojibake.
6. Unit-test title truncation, malformed timestamps, missing thumbnail, and `AllowedMentions.none()`.

## GitHub skill search

A targeted GitHub search did not surface a reputable, purpose-built Codex/Agent Skill for Discord notification visual design. The closest results handled reading Discord messages rather than designing outbound notifications. Installing one would add little value and may introduce unnecessary token-handling code. The official discord.py example above is the smaller, auditable reusable pattern.
