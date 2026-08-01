import json
import sys
from pathlib import Path


def sql_text(value):
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


source = Path(sys.argv[1])
destination = Path(sys.argv[2])
payload = json.loads(source.read_text(encoding="utf-8"))

rows = []
for item in payload.get("subscriptions", []):
    rows.append(
        "(" + ", ".join(
            sql_text(item.get(key))
            for key in (
                "youtube_channel_id",
                "youtube_channel_name",
                "discord_channel_id",
                "last_video_id",
            )
        ) + ")"
    )

statement = "DELETE FROM routes;\n"
if rows:
    statement += (
        "INSERT INTO routes "
        "(youtube_channel_id, youtube_channel_name, discord_channel_id, last_video_id) "
        "VALUES\n  " + ",\n  ".join(rows) + ";\n"
    )
destination.write_text(statement, encoding="utf-8")
print(f"Prepared {len(rows)} private route rows.")
