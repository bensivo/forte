# Friction points
This doc goes through the e2e journey that exists in the app today, and lists the friction points that are in the way of the north-star value-delivery we imagined. 


## User Journeys

Doc ingest, linking, and retrieval:
1. Create a forte vault at some location with `forte vault create`
2. Run `forte vault set-default` to make that your default vault for all future work
3. You create a few schemas for things you care about, like "client", "project", "meeting", "domain", populating them with some fields you think you might want to track
4. As you work, you have meeting with a client. Your AI note-taking assistant generates a meeting transcript and meeting notes automatically, which you download.
5. You open a terminal, go to your downloads, and enter `forte doc ingest <path>` to ingest it into your vault
    - (DONE) FRICTION: It's tedious to have to find the doc on your file-system when you already have it in front of you. Woudl be better if you can just drag it into the app, or copy-paste directly into forte.
6. You then link it to the appropriate entities automatically wtih `forte doc link <doc_id> <entity_id>`
    - FRICTION: You have to remember what the doc_id was so you can link it to entities
    - FRICTION: For every entity you want to link to, you have to:
      - See if it exists already (and get the ID)
        - FRICTION: to see if an entity exists, you have to list all entities, then find the one using just the name
      - Create a new record if it doesn't exist (and get the ID)
      - Remember the entity ID AND the doc ID to run the link command
7. One day, you're doing work for this client, and you need to remember what was said in teh meeting. You use `forte doc list` to find the doc by name, then open it with `forte doc show <doc_id>`
    - FRICTION: 2 steps to get content from a doc, and you have to remember the doc_id in between. Maybe better to have some interactive experience that lets you select eh doc automatically. 
8. One day, you need a detail, btu can't remember which doc it's from, to search through all the doc contents, you have to use `grep` on the forte doc dir to find
    - FRICTION: No text search within docs exists.
