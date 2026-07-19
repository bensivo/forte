# Usage Feedback,
Date: 2026-07-19
Author: Ben Sivoravong

Some feedback / feature changes I thought of when testing an eraly version of the product:
- It's kind of strange how --name is treated separately from the rest. I get that everything needs a name, but maybe we just use --field name=asdf to set it instead of a separate thign. Or make it a positional arg.
- The way we're setting fields is fine for simple fields, but if you want a field that's a list, it's awkward (like a 'meeting' entity with 'attendees' as a field). It's also awkward for fields that are longer. Maybe something like a 'description' would be a structured fifeld, but be multiline and awkward to type into a terminal.
- It's kind of awkward having to know what the ID is for an entity. Maybe we should be able to just reference entities by name, and then enforce a unique constraint on names
- It'd be cool to have some kind of structured query interface, like 'list meetings where date > 2026-01-01'