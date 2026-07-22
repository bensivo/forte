Some feedback from using the new 'agent ingest' and 'agent process' commands:

- It's tedious to mark all the extracted entities 'y/n' one by one. It'd be better to have some bulk way to edit them, like by openning VIM when you git commit things or git rebase, then marking the lines

- Sometimes, it duplicates an entity, like extracting 'garlic cloves' from 1 doc, then 'garlic' as a separate entity in another doc. For the second one, I already know (or suspect) that garlic is in there, so I'd like some way to say, "this should already exist, please look for it". 

    - As an alternative, we could extract duplicated initially, then after the fact, do some kind of 'forte entity merge' command, which turns them into a single entity, capturing all the references of one and putting them on another, then consolidating all fields. 

- For almost all commands, I put '-h' instead of '--help' and it doesn't print help

- When I use the --yes option in 'forte agent ingest', all it prints is "committed 17 changes", but I'd still like to see what the extracted entities / links were. 

- When doing 'forte doc show', looking at 'mentions' at the bottom, all it shows is the entity ID and name. But I'd like it to show the entity schema too. Like:

    #42 (schema) Healthy Cashew Chicken
      instead of
    entity #42: Healthy Cashew Chicken

