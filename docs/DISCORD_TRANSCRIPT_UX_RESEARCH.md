# Discord transcript delivery research

Date: 2026-08-13. Sources: Discord/W3C only.

## Answer

A bot message button cannot copy arbitrary text directly to a user's clipboard, on mobile or desktop. This is an inference from Discord's complete component reference: a normal button sends an interaction to the app, a Link button navigates to a URL, and a Premium button starts a purchase. Discord exposes no clipboard action or text payload for buttons. The handler runs on the bot/server, not inside the user's Discord client. [Discord button reference](https://docs.discord.com/developers/components/reference#button)

An external HTTPS transcript page can have its own **Copy** button using the Web Clipboard API. That still requires opening the page and tapping its button; clipboard access is permission/user-activation controlled and user agents retain policy control, so it cannot honestly be promised as 100% reliable. [W3C Clipboard API](https://www.w3.org/TR/clipboard-apis/#clipboard-interface)

## Current relevant limits

| Delivery surface | Official constraint | Consequence |
|---|---|---|
| Normal message `content` | 2,000 characters | Full transcripts require multiple messages. [Discord message API](https://docs.discord.com/developers/resources/message#create-message-jsonform-params) |
| Rich embeds | 4,096-character description; 6,000 characters combined across all embeds in one message | More room, but not plain text and poor for mobile copying. [Discord embed limits](https://docs.discord.com/developers/resources/message#embed-object-embed-limits) |
| Modal Text Input | Prefilled `value` maximum 4,000 characters | Can expose an editable paragraph for manual select/copy, but not arbitrary-length in one field. [Discord Text Input reference](https://docs.discord.com/developers/components/reference#text-input) |
| Modal | 1-5 top-level components | Five prefilled Text Inputs could theoretically expose 20,000 characters, but users must copy five fields; poor UX. [Discord interaction response modal limits](https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-response-object-modal) |
| Components V2 | Up to 40 total components per message | Text Display can show Markdown but has no copy action. Discord's current reference does not document a Text Display character maximum; do not treat it as unlimited. [Discord component reference](https://docs.discord.com/developers/components/reference#text-display) |
| File upload | Default 10 MiB per file; Create Message request maximum 25 MiB | More than enough for most transcripts, but remains a file/download workflow. [Discord upload limits](https://docs.discord.com/developers/reference#uploading-files), [Create Message limitations](https://docs.discord.com/developers/resources/message#create-message-limitations) |

Discord's user help explicitly says messages over 2,000 characters are converted to text files, and non-image attachments display without an inline preview. This explains the current mobile pain; a File component only places an uploaded attachment in the message and adds no clipboard feature. [Discord Sending Messages](https://support.discord.com/hc/en-us/articles/360034632292-Sending-Messages), [Discord File Attachments FAQ](https://support.discord.com/hc/en-us/articles/25444343291031-File-Attachments-FAQ), [Discord File component](https://docs.discord.com/developers/components/reference#file)

Components V2 does not solve export: enabling `IS_COMPONENTS_V2` disables normal `content` and embeds, attachments must be explicitly exposed, and the available button styles still have no copy operation. Premium buttons are purchase-only. [Discord Components V2 behavior](https://docs.discord.com/developers/components/reference#component-reference), [Discord button styles](https://docs.discord.com/developers/components/reference#button-styles)

## Recommended mobile-first design

1. **Default: plain message chunks.** Send transcript text as normal message content, split on paragraph/word boundaries below 2,000 characters (about 1,900 leaves safety room). No embed and no code fence. Keep title/status in a separate message so copied chunks contain transcript only. Disable `allowed_mentions` so transcript text cannot ping users/roles. Discord specifically recommends sanitization and `allowed_mentions` for user-provided strings. [Create Message guidance](https://docs.discord.com/developers/resources/message#create-message)

2. **Best arbitrary-length copy UX: `Open transcript` Link button.** Link buttons navigate to a URL (maximum 512-character URL). Open a minimal, mobile-first HTTPS page containing the complete transcript, a large **Copy transcript** button calling `navigator.clipboard.writeText`, and a visible selectable textarea/manual-copy fallback. Use a short-lived signed URL if transcript access should be private. This is the only practical single-copy experience for an arbitrary-length transcript, but it takes one tap to open plus one tap to copy. [Discord Link button](https://docs.discord.com/developers/components/reference#button), [W3C `writeText`](https://www.w3.org/TR/clipboard-apis/#dom-clipboard-writetext)

3. **Optional short/medium transcript helper: `Select transcript` modal.** A button can open a modal with a prefilled paragraph Text Input. Users can manually select/copy from the editable field. Call it **Select transcript**, not **Copy**, because Discord does not copy automatically and the official API does not guarantee client selection behavior. One field handles at most 4,000 characters; paging or multiple fields makes mobile UX worse.

4. **Keep `.txt` as last-resort fallback.** Use when chunk delivery or hosted-page delivery fails, or when the user explicitly requests a file. It is the most capacity-safe option, not the preferred mobile experience.

## Reliability requirements

- Acknowledge/defer every button interaction within 3 seconds; Discord invalidates the interaction token otherwise. Finish by editing the original response or sending follow-ups within the token's 15-minute lifetime. [Discord interaction timing](https://docs.discord.com/developers/interactions/receiving-and-responding#interaction-callback)
- A user-installed app that is not installed in the server is capped at five follow-up messages for that interaction; avoid designing unlimited transcript chunking around follow-ups. [Discord follow-up messages](https://docs.discord.com/developers/interactions/receiving-and-responding#followup-messages)
- Cache a successfully fetched transcript before rendering chunk/modal/page options. A later **Open/Select transcript** click should not refetch YouTube.
- Validate chunk lengths before send; send sequentially through the library's rate-limit handling and obey Discord's returned rate-limit headers/`retry_after`. On partial failure, clearly report which parts sent and expose page/file fallback. [Discord rate limits](https://docs.discord.com/developers/topics/rate-limits)
- Preserve exact plain text and line breaks. Escape/suppress Discord mentions.
- Never promise “100%.” Discord/network/client clipboard and transcript-source failures remain possible. Promise deterministic fallbacks and explicit errors instead.

## Implementation decision

Ship plain message chunks now. Add an **Open transcript** hosted page with in-page copy for the best mobile result. Do not build a native-looking **Copy** Discord button: Discord cannot perform that action and the label would mislead users. Modal/Text Display/File components are secondary surfaces, not a full solution.
